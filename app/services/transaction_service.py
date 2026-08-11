import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.models.transaction import ALLOWED_TRANSITIONS, Transaction, TransactionStatus, TransactionType
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.wallet_repository import WalletRepository


class TransactionService:
    def __init__(self, db: Session):
        self.db = db
        self.transactions = TransactionRepository(db)
        self.wallets = WalletRepository(db)

    def get_transaction_for_user(self, transaction_id: uuid.UUID, user_id: uuid.UUID) -> Transaction:
        transaction = self.transactions.get_by_id(transaction_id)
        if transaction is None:
            raise NotFoundError("Transaction not found.")

        owned_wallet_ids = {w.id for w in self.wallets.list_user_wallets(user_id)}
        if transaction.source_wallet_id not in owned_wallet_ids and transaction.destination_wallet_id not in owned_wallet_ids:
            # Same principle as wallet lookups: 404 rather than 403 to avoid
            # confirming existence of transactions that aren't the caller's.
            raise NotFoundError("Transaction not found.")
        return transaction

    def list_transactions_for_user(
        self,
        user_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        type_: TransactionType | None = None,
        status_: TransactionStatus | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
        reference: str | None = None,
    ) -> tuple[list[Transaction], int]:
        wallet_ids = [w.id for w in self.wallets.list_user_wallets(user_id)]
        return self.transactions.list_filtered(
            user_wallet_ids=wallet_ids,
            page=page,
            page_size=page_size,
            type_=type_,
            status_=status_,
            date_from=date_from,
            date_to=date_to,
            min_amount=min_amount,
            max_amount=max_amount,
            reference=reference,
        )

    def list_all_transactions(
        self,
        *,
        page: int,
        page_size: int,
        type_: TransactionType | None = None,
        status_: TransactionStatus | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
        reference: str | None = None,
    ) -> tuple[list[Transaction], int]:
        """Admin-only: unfiltered by wallet ownership."""
        return self.transactions.list_filtered(
            user_wallet_ids=None,
            page=page,
            page_size=page_size,
            type_=type_,
            status_=status_,
            date_from=date_from,
            date_to=date_to,
            min_amount=min_amount,
            max_amount=max_amount,
            reference=reference,
        )

    def transition_status(self, transaction: Transaction, new_status: TransactionStatus, reason: str | None = None) -> Transaction:
        """
        Enforces the transaction state machine from spec section 18:
        PENDING -> COMPLETED | FAILED | CANCELLED, and nothing out of a
        terminal state. Used by admin investigation / system reconciliation
        flows, never exposed as an arbitrary field update to clients.
        """
        allowed = ALLOWED_TRANSITIONS.get(transaction.status, set())
        if new_status not in allowed:
            raise BusinessRuleError(
                f"Cannot transition transaction from {transaction.status.value} to {new_status.value}."
            )
        transaction.status = new_status
        if reason:
            transaction.failure_reason = reason
        self.db.flush()
        self.db.commit()
        return transaction
