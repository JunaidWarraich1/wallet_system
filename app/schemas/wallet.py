import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

ISO_CURRENCY_LENGTH = 3


class CreateWalletRequest(BaseModel):
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, v: str) -> str:
        v = v.strip().upper()
        if not v.isalpha():
            raise ValueError("Currency must be a 3-letter ISO 4217 code, e.g. USD.")
        return v


class WalletResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    balance: Decimal
    currency: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DepositRequest(BaseModel):
    wallet_id: uuid.UUID
    amount: Decimal = Field(gt=0, decimal_places=2)


class WithdrawRequest(BaseModel):
    wallet_id: uuid.UUID
    amount: Decimal = Field(gt=0, decimal_places=2)


class TransferRequest(BaseModel):
    sender_wallet_id: uuid.UUID
    recipient_wallet_id: uuid.UUID
    amount: Decimal = Field(gt=0, decimal_places=2)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # Strip control characters to prevent log injection / header injection
        # style attacks if this value is ever echoed into logs or headers.
        cleaned = "".join(ch for ch in v if ch.isprintable())
        return cleaned.strip() or None
