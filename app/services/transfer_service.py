import uuid
from datetime import datetime, time, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError, ValidationError
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.wallet import Wallet, WalletStatus
from app.repositories.config_repository import WalletConfigRepository
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.wallet_repository import WalletRepository


def _start_of_today_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime.combine(now.date(), time.min, tzinfo=timezone.utc)


class TransferService:
    """
    Implements Section 7/8/9/10 of the spec — the core of the assignment.

    Key guarantees:
    1. ATOMICITY — the debit, credit, and transaction record are all written
       in a single database transaction. If anything fails partway through,
       everything rolls back. There is no code path that can leave Alice
       debited without Bob credited (or vice versa).
    2. NO RACE CONDITIONS — both wallets are locked with SELECT ... FOR UPDATE
       before any balance is read or modified, so two concurrent transfers
       touching the same wallet can never both read a stale balance.
    3. NO DEADLOCKS — wallets are always locked in a fixed, consistent order
       (sorted by UUID) regardless of who is sender/receiver, so two transfers
       between the same pair of wallets in opposite directions can never
       deadlock on each other's locks.
    4. IDEMPOTENCY — a transfer with a given Idempotency-Key is only ever
       applied once. A retried request with the same key returns the original
       result instead of moving money again.
    """

    def __init__(self, db: Session):
        self.db = db
        self.wallets = WalletRepository(db)
        self.transactions = TransactionRepository(db)
        self.configs = WalletConfigRepository(db)

    def _get_transfer_limits(self, currency: str):
        config = self.configs.get_by_currency(currency)
        if config:
            return config.max_single_transfer, config.max_daily_transfer
        from app.core.config import settings

        return Decimal(settings.DEFAULT_MAX_SINGLE_TRANSFER), Decimal(settings.DEFAULT_MAX_DAILY_TRANSFER)

    def transfer(
        self,
        *,
        sender_user_id: uuid.UUID,
        sender_wallet_id: uuid.UUID,
        recipient_wallet_id: uuid.UUID,
        amount: Decimal,
        description: str | None,
        idempotency_key: str | None,
    ) -> Transaction:
        # --- Idempotency check (fast path, before taking any locks) ---
        if idempotency_key:
            existing = self.transactions.get_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        # --- Rule 5: amount must be positive ---
        if amount <= 0:
            raise ValidationError("Transfer amount must be greater than zero.")

        # --- Rule 3: cannot transfer to self ---
        if sender_wallet_id == recipient_wallet_id:
            raise BusinessRuleError("Cannot transfer money to the same wallet.")

        try:
            with self.db.begin_nested():
                # Lock both wallets in a FIXED order (by UUID) to prevent deadlocks
                # between two opposite-direction concurrent transfers.
                first_id, second_id = sorted([sender_wallet_id, recipient_wallet_id])
                first_locked = self.wallets.get_by_id_for_update(first_id)
                second_locked = self.wallets.get_by_id_for_update(second_id)

                sender = first_locked if first_locked and first_locked.id == sender_wallet_id else second_locked
                receiver = first_locked if first_locked and first_locked.id == recipient_wallet_id else second_locked

                # --- Rule 1: sender wallet exists ---
                if sender is None:
                    raise NotFoundError("Sender wallet not found.")
                # --- Rule 2: receiver wallet exists ---
                if receiver is None:
                    raise NotFoundError("Recipient wallet not found.")

                if sender.user_id != sender_user_id:
                    # Not the authenticated user's wallet.
                    raise NotFoundError("Sender wallet not found.")

                # --- Rule 4: both wallets must be active ---
                if sender.status != WalletStatus.ACTIVE:
                    raise BusinessRuleError(f"Sender wallet is {sender.status.value.lower()}.")
                if receiver.status != WalletStatus.ACTIVE:
                    raise BusinessRuleError(f"Recipient wallet is {receiver.status.value.lower()}.")

                if sender.currency != receiver.currency:
                    raise BusinessRuleError("Cannot transfer between wallets of different currencies.")

                max_single, max_daily = self._get_transfer_limits(sender.currency)

                if amount > max_single:
                    raise BusinessRuleError(f"Transfer exceeds the maximum single transfer of {max_single}.")

                # --- Rule 7: daily transfer limit ---
                already_transferred_today = self.transactions.sum_completed_amount_since(
                    sender.id, TransactionType.TRANSFER, _start_of_today_utc(), as_source=True
                )
                if already_transferred_today + amount > max_daily:
                    raise BusinessRuleError(
                        f"This transfer would exceed your daily transfer limit of {max_daily}."
                    )

                # --- Rule 6: sufficient balance ---
                if sender.balance < amount:
                    raise BusinessRuleError("Insufficient balance.")

                # --- Rule 8/9: atomic debit + credit + record, single DB transaction ---
                self.wallets.adjust_balance(sender, -amount)
                self.wallets.adjust_balance(receiver, amount)

                transaction = Transaction(
                    reference=self.transactions.next_reference(),
                    idempotency_key=idempotency_key,
                    type=TransactionType.TRANSFER,
                    status=TransactionStatus.COMPLETED,
                    amount=amount,
                    currency=sender.currency,
                    source_wallet_id=sender.id,
                    destination_wallet_id=receiver.id,
                    description=description,
                    initiated_by_user_id=sender_user_id,
                )
                self.transactions.create(transaction)

            self.db.commit()
            return transaction

        except IntegrityError:
            # Extremely unlikely race: two concurrent requests with the same
            # idempotency key both passed the initial check. The DB-level
            # UNIQUE constraint on idempotency_key is the real guarantee here.
            self.db.rollback()
            if idempotency_key:
                existing = self.transactions.get_by_idempotency_key(idempotency_key)
                if existing:
                    return existing
            raise ConflictError("This transaction could not be processed due to a conflict. Please retry.")
