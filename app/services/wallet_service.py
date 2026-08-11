import uuid
from datetime import datetime, time, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthorizationError, BusinessRuleError, ConflictError, NotFoundError, ValidationError
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.wallet import Wallet, WalletStatus
from app.repositories.config_repository import WalletConfigRepository
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.wallet_repository import WalletRepository

VALID_CURRENCIES = {"USD", "PKR", "EUR", "GBP", "AED", "SAR"}


def _start_of_today_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime.combine(now.date(), time.min, tzinfo=timezone.utc)


class WalletService:
    """
    All business decisions about wallets live here. The API layer never
    touches balances, statuses, or limits directly — it only calls into
    this service.
    """

    def __init__(self, db: Session):
        self.db = db
        self.wallets = WalletRepository(db)
        self.transactions = TransactionRepository(db)
        self.configs = WalletConfigRepository(db)

    # ------------------------------------------------------------------
    # Wallet creation
    # ------------------------------------------------------------------
    def create_wallet(self, user_id: uuid.UUID, currency: str) -> Wallet:
        if currency not in VALID_CURRENCIES:
            raise ValidationError(f"Unsupported currency '{currency}'.")

        existing = self.wallets.get_user_wallet_by_currency(user_id, currency)
        if existing is not None:
            raise ConflictError(f"You already have an active {currency} wallet.")

        wallet = Wallet(user_id=user_id, currency=currency, balance=Decimal("0.00"), status=WalletStatus.ACTIVE)
        try:
            self.wallets.create(wallet)
            self.db.commit()
        except IntegrityError:
            # Guards against a race where two concurrent requests both pass
            # the check above and try to create the same (user, currency)
            # wallet — the DB-level UniqueConstraint is the real guarantee.
            self.db.rollback()
            raise ConflictError(f"You already have an active {currency} wallet.")
        return wallet

    def get_wallet_for_user(self, wallet_id: uuid.UUID, user_id: uuid.UUID) -> Wallet:
        wallet = self.wallets.get_by_id(wallet_id)
        if wallet is None:
            raise NotFoundError("Wallet not found.")
        if wallet.user_id != user_id:
            # Return NotFound rather than Forbidden so we don't confirm to an
            # attacker that a given wallet_id belongs to *someone*.
            raise NotFoundError("Wallet not found.")
        return wallet

    def list_wallets_for_user(self, user_id: uuid.UUID) -> list[Wallet]:
        return self.wallets.list_user_wallets(user_id)

    # ------------------------------------------------------------------
    # Config lookup (falls back to global defaults if not configured)
    # ------------------------------------------------------------------
    def _get_limits(self, currency: str):
        config = self.configs.get_by_currency(currency)
        if config:
            return config
        # Fallback: simple namespace-like object using settings defaults
        class _Defaults:
            max_single_deposit = Decimal(settings.DEFAULT_MAX_SINGLE_DEPOSIT)
            max_single_withdrawal = Decimal(settings.DEFAULT_MAX_SINGLE_WITHDRAWAL)
            max_daily_withdrawal = Decimal(settings.DEFAULT_MAX_DAILY_WITHDRAWAL)
            max_single_transfer = Decimal(settings.DEFAULT_MAX_SINGLE_TRANSFER)
            max_daily_transfer = Decimal(settings.DEFAULT_MAX_DAILY_TRANSFER)
        return _Defaults()

    # ------------------------------------------------------------------
    # Deposit
    # ------------------------------------------------------------------
    def deposit(
        self, *, user_id: uuid.UUID, wallet_id: uuid.UUID, amount: Decimal, idempotency_key: str | None
    ) -> Transaction:
        if idempotency_key:
            existing = self.transactions.get_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        if amount <= 0:
            raise ValidationError("Deposit amount must be greater than zero.")

        with self.db.begin_nested():
            wallet = self.wallets.get_by_id_for_update(wallet_id)
            if wallet is None:
                raise NotFoundError("Wallet not found.")
            if wallet.user_id != user_id:
                raise NotFoundError("Wallet not found.")
            if wallet.status != WalletStatus.ACTIVE:
                raise BusinessRuleError(f"Wallet is {wallet.status.value.lower()} and cannot accept deposits.")

            limits = self._get_limits(wallet.currency)
            if amount > limits.max_single_deposit:
                raise BusinessRuleError(f"Deposit exceeds the maximum allowed amount of {limits.max_single_deposit}.")

            self.wallets.adjust_balance(wallet, amount)

            transaction = Transaction(
                reference=self.transactions.next_reference(),
                idempotency_key=idempotency_key,
                type=TransactionType.DEPOSIT,
                status=TransactionStatus.COMPLETED,
                amount=amount,
                currency=wallet.currency,
                destination_wallet_id=wallet.id,
                initiated_by_user_id=user_id,
            )
            self.transactions.create(transaction)

        self.db.commit()
        return transaction

    # ------------------------------------------------------------------
    # Withdrawal
    # ------------------------------------------------------------------
    def withdraw(
        self, *, user_id: uuid.UUID, wallet_id: uuid.UUID, amount: Decimal, idempotency_key: str | None
    ) -> Transaction:
        if idempotency_key:
            existing = self.transactions.get_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        if amount <= 0:
            raise ValidationError("Withdrawal amount must be greater than zero.")

        with self.db.begin_nested():
            wallet = self.wallets.get_by_id_for_update(wallet_id)
            if wallet is None:
                raise NotFoundError("Wallet not found.")
            if wallet.user_id != user_id:
                raise NotFoundError("Wallet not found.")
            if wallet.status != WalletStatus.ACTIVE:
                raise BusinessRuleError(f"Wallet is {wallet.status.value.lower()} and cannot process withdrawals.")

            limits = self._get_limits(wallet.currency)
            if amount > limits.max_single_withdrawal:
                raise BusinessRuleError(
                    f"Withdrawal exceeds the maximum single withdrawal of {limits.max_single_withdrawal}."
                )

            already_withdrawn_today = self.transactions.sum_completed_amount_since(
                wallet.id, TransactionType.WITHDRAWAL, _start_of_today_utc(), as_source=True
            )
            if already_withdrawn_today + amount > limits.max_daily_withdrawal:
                raise BusinessRuleError(
                    f"This withdrawal would exceed your daily withdrawal limit of {limits.max_daily_withdrawal}."
                )

            if wallet.balance < amount:
                raise BusinessRuleError("Insufficient balance.")

            self.wallets.adjust_balance(wallet, -amount)

            transaction = Transaction(
                reference=self.transactions.next_reference(),
                idempotency_key=idempotency_key,
                type=TransactionType.WITHDRAWAL,
                status=TransactionStatus.COMPLETED,
                amount=amount,
                currency=wallet.currency,
                source_wallet_id=wallet.id,
                initiated_by_user_id=user_id,
            )
            self.transactions.create(transaction)

        self.db.commit()
        return transaction
