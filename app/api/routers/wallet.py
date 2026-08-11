import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, rate_limit_default, rate_limit_transfer, require_customer
from app.core.security import normalize_idempotency_key
from app.database import get_db
from app.models.transaction import TransactionStatus, TransactionType
from app.models.user import User
from app.schemas.transaction import PaginatedTransactions, TransactionResponse
from app.schemas.wallet import (
    CreateWalletRequest,
    DepositRequest,
    TransferRequest,
    WalletResponse,
    WithdrawRequest,
)
from app.services.transaction_service import TransactionService
from app.services.transfer_service import TransferService
from app.services.wallet_service import WalletService

router = APIRouter(prefix="/api/wallet", tags=["Wallet"])


@router.post("/", response_model=WalletResponse, status_code=status.HTTP_201_CREATED)
def create_wallet(
    payload: CreateWalletRequest,
    current_user: User = Depends(require_customer),
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit_default),
):
    service = WalletService(db)
    wallet = service.create_wallet(current_user.id, payload.currency)
    return wallet


@router.get("/", response_model=list[WalletResponse])
def list_my_wallets(
    current_user: User = Depends(require_customer),
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit_default),
):
    service = WalletService(db)
    return service.list_wallets_for_user(current_user.id)


@router.get("/{wallet_id}", response_model=WalletResponse)
def get_wallet(
    wallet_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit_default),
):
    service = WalletService(db)
    return service.get_wallet_for_user(wallet_id, current_user.id)


@router.post("/deposit/", response_model=TransactionResponse)
def deposit(
    payload: DepositRequest,
    current_user: User = Depends(require_customer),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _rl=Depends(rate_limit_default),
):
    service = WalletService(db)
    key = normalize_idempotency_key(idempotency_key) if idempotency_key else None
    transaction = service.deposit(
        user_id=current_user.id, wallet_id=payload.wallet_id, amount=payload.amount, idempotency_key=key
    )
    return transaction


@router.post("/withdraw/", response_model=TransactionResponse)
def withdraw(
    payload: WithdrawRequest,
    current_user: User = Depends(require_customer),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _rl=Depends(rate_limit_default),
):
    service = WalletService(db)
    key = normalize_idempotency_key(idempotency_key) if idempotency_key else None
    transaction = service.withdraw(
        user_id=current_user.id, wallet_id=payload.wallet_id, amount=payload.amount, idempotency_key=key
    )
    return transaction


@router.post("/transfer/", response_model=TransactionResponse)
def transfer(
    payload: TransferRequest,
    current_user: User = Depends(require_customer),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _rl=Depends(rate_limit_transfer),
):
    service = TransferService(db)
    key = normalize_idempotency_key(idempotency_key) if idempotency_key else None
    transaction = service.transfer(
        sender_user_id=current_user.id,
        sender_wallet_id=payload.sender_wallet_id,
        recipient_wallet_id=payload.recipient_wallet_id,
        amount=payload.amount,
        description=payload.description,
        idempotency_key=key,
    )
    return transaction


@router.get("/transactions/", response_model=PaginatedTransactions)
def list_transactions(
    current_user: User = Depends(require_customer),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    type: TransactionType | None = None,
    status_: TransactionStatus | None = Query(default=None, alias="status"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_amount: Decimal | None = Query(default=None, ge=0),
    max_amount: Decimal | None = Query(default=None, ge=0),
    reference: str | None = Query(default=None, max_length=40),
    _rl=Depends(rate_limit_default),
):
    service = TransactionService(db)
    items, total = service.list_transactions_for_user(
        current_user.id,
        page=page,
        page_size=page_size,
        type_=type,
        status_=status_,
        date_from=date_from,
        date_to=date_to,
        min_amount=min_amount,
        max_amount=max_amount,
        reference=reference,
    )
    return PaginatedTransactions(items=items, total=total, page=page, page_size=page_size)


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
def get_transaction(
    transaction_id: uuid.UUID,
    current_user: User = Depends(require_customer),
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit_default),
):
    service = TransactionService(db)
    return service.get_transaction_for_user(transaction_id, current_user.id)
