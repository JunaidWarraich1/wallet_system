import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, rate_limit_default, require_admin
from app.database import get_db
from app.models.transaction import TransactionStatus, TransactionType
from app.models.user import User
from app.schemas.admin import AdjustBalanceRequest, FreezeWalletRequest, UserAdminResponse
from app.schemas.transaction import PaginatedTransactions, TransactionResponse
from app.schemas.wallet import WalletResponse
from app.services.admin_wallet_service import AdminWalletService
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/users", response_model=list[UserAdminResponse])
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit_default),
):
    service = AdminWalletService(db)
    items, _total = service.list_users(page, page_size)
    return items


@router.get("/wallets", response_model=list[WalletResponse])
def list_wallets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit_default),
):
    service = AdminWalletService(db)
    items, _total = service.list_wallets(page, page_size)
    return items


@router.post("/wallets/{wallet_id}/freeze/", response_model=WalletResponse)
def freeze_wallet(
    wallet_id: uuid.UUID,
    payload: FreezeWalletRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit_default),
):
    service = AdminWalletService(db)
    return service.freeze_wallet(
        admin_id=current_admin.id, wallet_id=wallet_id, reason=payload.reason, ip_address=get_client_ip(request)
    )


@router.post("/wallets/{wallet_id}/unfreeze/", response_model=WalletResponse)
def unfreeze_wallet(
    wallet_id: uuid.UUID,
    payload: FreezeWalletRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit_default),
):
    service = AdminWalletService(db)
    return service.unfreeze_wallet(
        admin_id=current_admin.id, wallet_id=wallet_id, reason=payload.reason, ip_address=get_client_ip(request)
    )


@router.post("/wallets/{wallet_id}/adjust-balance/", response_model=TransactionResponse)
def adjust_balance(
    wallet_id: uuid.UUID,
    payload: AdjustBalanceRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit_default),
):
    service = AdminWalletService(db)
    return service.adjust_balance(
        admin_id=current_admin.id,
        wallet_id=wallet_id,
        amount=payload.amount,
        reason=payload.reason,
        ip_address=get_client_ip(request),
    )


@router.get("/transactions", response_model=PaginatedTransactions)
def list_all_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    type: TransactionType | None = None,
    status_: TransactionStatus | None = Query(default=None, alias="status"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_amount: Decimal | None = Query(default=None, ge=0),
    max_amount: Decimal | None = Query(default=None, ge=0),
    reference: str | None = Query(default=None, max_length=40),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit_default),
):
    service = TransactionService(db)
    items, total = service.list_all_transactions(
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


@router.get("/transactions/{transaction_id}/investigate", response_model=TransactionResponse)
def investigate_transaction(
    transaction_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit_default),
):
    service = AdminWalletService(db)
    return service.investigate_failed_transaction(transaction_id)
