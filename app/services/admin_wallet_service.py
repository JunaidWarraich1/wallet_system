import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.models.auth import AuditLog
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.user import User
from app.models.wallet import Wallet, WalletStatus
from app.repositories.auth_repository import AuditLogRepository
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.wallet_repository import WalletRepository


class AdminWalletService:
    """
    Admin-only operations. Every mutating action here writes an AuditLog
    entry — balance adjustments and freezes are exactly the kind of action
    that must be traceable to a specific admin, with a reason, for later
    investigation (spec section 15).
    """

    def __init__(self, db: Session):
        self.db = db
        self.wallets = WalletRepository(db)
        self.users = UserRepository(db)
        self.transactions = TransactionRepository(db)
        self.audit_logs = AuditLogRepository(db)

    def list_users(self, page: int, page_size: int) -> tuple[list[User], int]:
        return self.users.list_all(page, page_size)

    def list_wallets(self, page: int, page_size: int) -> tuple[list[Wallet], int]:
        return self.wallets.list_all(page, page_size)

    def freeze_wallet(self, *, admin_id: uuid.UUID, wallet_id: uuid.UUID, reason: str, ip_address: str | None) -> Wallet:
        with self.db.begin_nested():
            wallet = self.wallets.get_by_id_for_update(wallet_id)
            if wallet is None:
                raise NotFoundError("Wallet not found.")
            if wallet.status == WalletStatus.FROZEN:
                raise BusinessRuleError("Wallet is already frozen.")
            wallet.status = WalletStatus.FROZEN
            self.db.flush()

            self.audit_logs.create(
                AuditLog(
                    actor_user_id=admin_id,
                    action="WALLET_FREEZE",
                    target_type="WALLET",
                    target_id=str(wallet.id),
                    details=reason,
                    ip_address=ip_address,
                )
            )
        self.db.commit()
        return wallet

    def unfreeze_wallet(self, *, admin_id: uuid.UUID, wallet_id: uuid.UUID, reason: str, ip_address: str | None) -> Wallet:
        with self.db.begin_nested():
            wallet = self.wallets.get_by_id_for_update(wallet_id)
            if wallet is None:
                raise NotFoundError("Wallet not found.")
            if wallet.status != WalletStatus.FROZEN:
                raise BusinessRuleError("Wallet is not frozen.")
            wallet.status = WalletStatus.ACTIVE
            self.db.flush()

            self.audit_logs.create(
                AuditLog(
                    actor_user_id=admin_id,
                    action="WALLET_UNFREEZE",
                    target_type="WALLET",
                    target_id=str(wallet.id),
                    details=reason,
                    ip_address=ip_address,
                )
            )
        self.db.commit()
        return wallet

    def adjust_balance(
        self, *, admin_id: uuid.UUID, wallet_id: uuid.UUID, amount: Decimal, reason: str, ip_address: str | None
    ) -> Transaction:
        """
        Controlled balance correction. Never a raw PUT/PATCH of the balance
        field — always goes through this auditable, transaction-generating
        operation (spec section 15).
        """
        with self.db.begin_nested():
            wallet = self.wallets.get_by_id_for_update(wallet_id)
            if wallet is None:
                raise NotFoundError("Wallet not found.")

            new_balance = wallet.balance + amount
            if new_balance < 0:
                raise BusinessRuleError("Adjustment would result in a negative balance.")

            self.wallets.adjust_balance(wallet, amount)

            transaction = Transaction(
                reference=self.transactions.next_reference(),
                type=TransactionType.ADJUSTMENT,
                status=TransactionStatus.COMPLETED,
                amount=abs(amount),
                currency=wallet.currency,
                source_wallet_id=wallet.id if amount < 0 else None,
                destination_wallet_id=wallet.id if amount > 0 else None,
                description=f"Admin balance adjustment: {reason}",
                initiated_by_user_id=admin_id,
            )
            self.transactions.create(transaction)

            self.audit_logs.create(
                AuditLog(
                    actor_user_id=admin_id,
                    action="BALANCE_ADJUSTMENT",
                    target_type="WALLET",
                    target_id=str(wallet.id),
                    details=f"amount={amount}, reason={reason}",
                    ip_address=ip_address,
                )
            )

        self.db.commit()
        return transaction

    def investigate_failed_transaction(self, transaction_id: uuid.UUID) -> Transaction:
        transaction = self.transactions.get_by_id(transaction_id)
        if transaction is None:
            raise NotFoundError("Transaction not found.")
        if transaction.status != TransactionStatus.FAILED:
            raise BusinessRuleError("Only FAILED transactions can be investigated.")
        return transaction
