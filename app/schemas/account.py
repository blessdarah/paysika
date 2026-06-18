from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AccountCreate(BaseModel):
    currency: str = Field(..., min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    name: str = Field(default="", max_length=120)


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    currency: str
    name: str
    is_system: bool
    created_at: datetime


class BalanceResponse(BaseModel):
    account_id: int
    currency: str
    balance: str  # String to avoid float precision issues in JSON
