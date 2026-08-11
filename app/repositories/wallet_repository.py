import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.wallet import Wallet


class WalletRepository:
    """Pure data access for wallets."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, wallet_id: uuid.UUID) -> Wallet | None:
        return self.db.get(Wallet, wallet_id)

    def get_by_id_for_update(self, wallet_id: uuid.UUID) -> Wallet | None:
        """
        SELECT ... FOR UPDATE — takes a row-level lock on the wallet.

        This is THE mechanism that makes concurrent transfers safe. Without it,
        two simultaneous requests against the same wallet could both read the
        same starting balance and both "successfully" debit it, leaving the
        wallet over-drawn (a classic race condition / TOCTOU bug in financial
        systems). With FOR UPDATE, the second transaction blocks until the
        first commits or rolls back, so balance checks are always against the
        true current value.

        Always lock wallets in a consistent order (see TransferService) to
        avoid deadlocks when two transfers happen between the same pair of
        wallets in opposite directions at the same time.
        """
        stmt = select(Wallet).where(Wallet.id == wallet_id).with_for_update()
        return self.db.execute(stmt).scalar_one_or_none()

    def get_user_wallet_by_currency(self, user_id: uuid.UUID, currency: str) -> Wallet | None:
        stmt = select(Wallet).where(Wallet.user_id == user_id, Wallet.currency == currency)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_user_wallets(self, user_id: uuid.UUID) -> list[Wallet]:
        stmt = select(Wallet).where(Wallet.user_id == user_id)
        return list(self.db.execute(stmt).scalars().all())

    def create(self, wallet: Wallet) -> Wallet:
        self.db.add(wallet)
        self.db.flush()
        return wallet

    def adjust_balance(self, wallet: Wallet, delta: Decimal) -> Wallet:
        """Applies delta to an already-locked wallet instance. Caller MUST have
        obtained the wallet via get_by_id_for_update within an active transaction."""
        wallet.balance = wallet.balance + delta
        self.db.flush()
        return wallet

    def list_all(self, page: int = 1, page_size: int = 20) -> tuple[list[Wallet], int]:
        total = self.db.execute(select(Wallet)).scalars().all()
        stmt = select(Wallet).order_by(Wallet.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        items = self.db.execute(stmt).scalars().all()
        return list(items), len(total)
