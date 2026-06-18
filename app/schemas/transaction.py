from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class LedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    transaction_id: int
    amount: str
    entry_type: str
    status: str
    currency: str
    created_at: datetime


class TransactionResponse(BaseModel):
    id: int
    type: str
    status: str
    description: str | None
    correlation_id: str | None
    created_at: datetime
    entries: list[LedgerEntryResponse] = []


class TransactionListResponse(BaseModel):
    transactions: list[TransactionResponse]
    total: int
    page: int
    per_page: int
    pages: int
