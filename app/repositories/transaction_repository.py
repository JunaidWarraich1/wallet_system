import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.transaction import Transaction, TransactionStatus, TransactionType


class TransactionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, transaction_id: uuid.UUID) -> Transaction | None:
        return self.db.get(Transaction, transaction_id)

    def get_by_idempotency_key(self, key: str) -> Transaction | None:
        stmt = select(Transaction).where(Transaction.idempotency_key == key)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, transaction: Transaction) -> Transaction:
        self.db.add(transaction)
        self.db.flush()
        return transaction

    def next_reference(self) -> str:
        """
        Generates a unique, human-readable transaction reference such as
        TXN-20260811-000001.

        Uniqueness under concurrency: we use a Postgres sequence (per-day would
        require a separate sequence table; here we use a global sequence and
        format it into the daily-looking reference) so the DB itself guarantees
        no two requests can ever get the same number, even under heavy
        concurrent load — no read-check-write race condition in application code.
        """
        seq_value = self.db.execute(func.nextval("transaction_reference_seq")).scalar()
        today = date.today().strftime("%Y%m%d")
        return f"TXN-{today}-{seq_value:06d}"

    def list_filtered(
        self,
        *,
        user_wallet_ids: list[uuid.UUID] | None,
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
        stmt = select(Transaction)

        if user_wallet_ids is not None:
            stmt = stmt.where(
                (Transaction.source_wallet_id.in_(user_wallet_ids))
                | (Transaction.destination_wallet_id.in_(user_wallet_ids))
            )
        if type_ is not None:
            stmt = stmt.where(Transaction.type == type_)
        if status_ is not None:
            stmt = stmt.where(Transaction.status == status_)
        if date_from is not None:
            stmt = stmt.where(Transaction.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Transaction.created_at <= date_to)
        if min_amount is not None:
            stmt = stmt.where(Transaction.amount >= min_amount)
        if max_amount is not None:
            stmt = stmt.where(Transaction.amount <= max_amount)
        if reference is not None:
            stmt = stmt.where(Transaction.reference.ilike(f"%{reference}%"))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.execute(count_stmt).scalar_one()

        stmt = stmt.order_by(Transaction.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        items = list(self.db.execute(stmt).scalars().all())
        return items, total

    def sum_completed_amount_since(
        self, wallet_id: uuid.UUID, type_: TransactionType, since: datetime, as_source: bool = True
    ) -> Decimal:
        """Used for daily limit checks (e.g. total transferred/withdrawn today)."""
        wallet_col = Transaction.source_wallet_id if as_source else Transaction.destination_wallet_id
        stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            wallet_col == wallet_id,
            Transaction.type == type_,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.created_at >= since,
        )
        return self.db.execute(stmt).scalar_one()
