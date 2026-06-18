from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class DepositRequest(BaseModel):
    account_id: int
    amount: str = Field(..., description="Decimal amount as string")
    currency: str = Field(..., min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    description: str = Field(default="", max_length=500)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        try:
            d = Decimal(v)
        except Exception:
            raise ValueError("amount must be a valid decimal string")
        if d <= 0:
            raise ValueError("amount must be positive")
        return v


class DepositResponse(BaseModel):
    transaction_id: int
    status: str
    account_id: int
    amount: str
    currency: str
    created_at: datetime
