import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class TransactionResponse(BaseModel):
    id: uuid.UUID
    reference: str
    type: str
    status: str
    amount: Decimal
    currency: str
    source_wallet_id: uuid.UUID | None
    destination_wallet_id: uuid.UUID | None
    description: str | None
    failure_reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedTransactions(BaseModel):
    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int


class TransactionFilterParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    type: str | None = None
    status: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    min_amount: Decimal | None = Field(default=None, ge=0)
    max_amount: Decimal | None = Field(default=None, ge=0)
    reference: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be before date_to.")
        if self.min_amount is not None and self.max_amount is not None and self.min_amount > self.max_amount:
            raise ValueError("min_amount must be less than or equal to max_amount.")
        return self
