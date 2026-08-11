import uuid
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class AdjustBalanceRequest(BaseModel):
    amount: Decimal = Field(decimal_places=2, description="Positive to credit, negative to debit.")
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("amount")
    @classmethod
    def amount_not_zero(cls, v: Decimal) -> Decimal:
        if v == 0:
            raise ValueError("Adjustment amount cannot be zero.")
        return v

    @field_validator("reason")
    @classmethod
    def sanitize_reason(cls, v: str) -> str:
        cleaned = "".join(ch for ch in v if ch.isprintable()).strip()
        if len(cleaned) < 10:
            raise ValueError("Reason must be at least 10 characters and descriptive.")
        return cleaned


class FreezeWalletRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class WalletConfigUpdateRequest(BaseModel):
    currency: str = Field(min_length=3, max_length=3)
    max_single_deposit: Decimal = Field(gt=0)
    max_single_withdrawal: Decimal = Field(gt=0)
    max_daily_withdrawal: Decimal = Field(gt=0)
    max_single_transfer: Decimal = Field(gt=0)
    max_daily_transfer: Decimal = Field(gt=0)


class UserAdminResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str
    status: str

    model_config = {"from_attributes": True}
