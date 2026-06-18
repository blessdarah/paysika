from decimal import Decimal

from flask import g

from app.domain.enums import (
    EntryStatus,
    EntryType,
    TransactionStatus,
    TransactionType,
)
from app.domain.events import DepositCompleted
from app.extensions import db
from app.models.ledger_entry import LedgerEntry
from app.models.transaction import Transaction
from app.services import account_service, balance_service, event_bus
from app.utils.exceptions import AccountNotFoundError, CurrencyMismatchError


def execute_deposit(
    account_id: int,
    amount: Decimal,
    currency: str,
    description: str = "",
    idempotency_key: str | None = None,
) -> Transaction:
    """Execute a deposit into a user account using double-entry bookkeeping.

    DEBIT clearing account (negative), CREDIT user account (positive).
    """
    if amount <= 0:
        raise CurrencyMismatchError("Deposit amount must be positive")

    # Check idempotency
    if idempotency_key:
        existing = Transaction.query.filter_by(idempotency_key=idempotency_key).first()
        if existing:
            return existing

    # Get the target account
    account = account_service.get_account(account_id)
    if account.currency != currency:
        raise CurrencyMismatchError(
            f"Account currency {account.currency} does not match deposit currency {currency}"
        )

    # Get or create the platform clearing account
    clearing_account = account_service.get_or_create_platform_clearing_account(currency)

    # Create the transaction
    correlation_id = getattr(g, "correlation_id", None) or Transaction.generate_correlation_id()
    txn = Transaction(
        type=TransactionType.DEPOSIT.value,
        status=TransactionStatus.COMPLETED.value,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        description=description or f"Deposit {amount} {currency}",
    )
    db.session.add(txn)
    db.session.flush()

    # Debit clearing account (source of funds)
    debit_entry = LedgerEntry(
        account_id=clearing_account.id,
        transaction_id=txn.id,
        amount=-amount,
        entry_type=EntryType.DEBIT.value,
        status=EntryStatus.SUCCESS.value,
        currency=currency,
    )

    # Credit user account (destination of funds)
    credit_entry = LedgerEntry(
        account_id=account_id,
        transaction_id=txn.id,
        amount=amount,
        entry_type=EntryType.CREDIT.value,
        status=EntryStatus.SUCCESS.value,
        currency=currency,
    )

    db.session.add(debit_entry)
    db.session.add(credit_entry)
    db.session.flush()

    balance_service.invalidate_balance_cache(account_id)
    balance_service.invalidate_balance_cache(clearing_account.id)

    # Emit event
    event_bus.publish(DepositCompleted(
        transaction_id=txn.id,
        account_id=account_id,
        amount=amount,
        currency=currency,
    ))

    return txn
