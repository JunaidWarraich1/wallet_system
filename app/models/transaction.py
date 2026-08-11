import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TransactionType(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRANSFER = "TRANSFER"
    ADJUSTMENT = "ADJUSTMENT"  # admin balance correction


class TransactionStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Allowed state transitions — enforced in the service layer (see
# services/transaction_service.py: TransactionService.transition_status).
# PENDING -> COMPLETED | FAILED | CANCELLED. No transitions out of a terminal state.
ALLOWED_TRANSITIONS: dict[TransactionStatus, set[TransactionStatus]] = {
    TransactionStatus.PENDING: {
        TransactionStatus.COMPLETED,
        TransactionStatus.FAILED,
        TransactionStatus.CANCELLED,
    },
    TransactionStatus.COMPLETED: set(),
    TransactionStatus.FAILED: set(),
    TransactionStatus.CANCELLED: set(),
}


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_source_created", "source_wallet_id", "created_at"),
        Index("ix_transactions_destination_created", "destination_wallet_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)

    # Idempotency key is unique-indexed so the DB itself prevents duplicate
    # processing even under a race between two concurrent identical requests
    # (see services/transfer_service.py for how this is used with a DB-level
    # unique constraint + catch-on-conflict pattern).
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)

    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False
    )
    amount: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    source_wallet_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("wallets.id"), nullable=True, index=True
    )
    destination_wallet_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("wallets.id"), nullable=True, index=True
    )

    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Who initiated it — important for admin adjustments / audit trail.
    initiated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source_wallet = relationship("Wallet", foreign_keys=[source_wallet_id])
    destination_wallet = relationship("Wallet", foreign_keys=[destination_wallet_id])
