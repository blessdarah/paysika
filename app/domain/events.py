from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class TransferCompleted:
    transaction_id: int
    source_account_id: int
    target_account_id: int
    amount: Decimal
    currency: str


@dataclass(frozen=True)
class TransferFailed:
    transaction_id: int
    source_account_id: int
    target_account_id: int
    amount: Decimal
    currency: str
    reason: str


@dataclass(frozen=True)
class DepositCompleted:
    transaction_id: int
    account_id: int
    amount: Decimal
    currency: str
