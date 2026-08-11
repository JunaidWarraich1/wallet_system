from sqlalchemy import Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WalletConfiguration(Base):
    """
    Configurable business limits, per currency, stored in the DB instead of
    hardcoded in the codebase (per spec section 13). Falls back to the
    defaults in app.core.config.settings if no row exists for a currency.
    """
    __tablename__ = "wallet_configurations"

    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    max_single_deposit: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
    max_single_withdrawal: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
    max_daily_withdrawal: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
    max_single_transfer: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
    max_daily_transfer: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
