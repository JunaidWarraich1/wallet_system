from sqlalchemy.orm import Session

from app.models.config import WalletConfiguration


class WalletConfigRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_currency(self, currency: str) -> WalletConfiguration | None:
        return self.db.get(WalletConfiguration, currency)

    def upsert(self, config: WalletConfiguration) -> WalletConfiguration:
        existing = self.get_by_currency(config.currency)
        if existing:
            existing.max_single_deposit = config.max_single_deposit
            existing.max_single_withdrawal = config.max_single_withdrawal
            existing.max_daily_withdrawal = config.max_daily_withdrawal
            existing.max_single_transfer = config.max_single_transfer
            existing.max_daily_transfer = config.max_daily_transfer
            self.db.flush()
            return existing
        self.db.add(config)
        self.db.flush()
        return config
