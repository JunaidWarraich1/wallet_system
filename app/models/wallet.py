import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WalletStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (
        # A user can only have ONE wallet per currency (business rule from spec).
        # This is enforced at the DATABASE level, not just in application code,
        # so it can never be violated even under concurrent requests or bugs.
        UniqueConstraint("user_id", "currency", name="uq_wallet_user_currency"),
        # Balance can never go negative — enforced at the DB level as a last line
        # of defense, even if a service-layer bug ever let it through.
        CheckConstraint("balance >= 0", name="ck_wallet_balance_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    balance: Mapped[Numeric] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)  # ISO 4217, e.g. USD, PKR
    status: Mapped[WalletStatus] = mapped_column(Enum(WalletStatus), default=WalletStatus.ACTIVE, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner = relationship("User", back_populates="wallets")
