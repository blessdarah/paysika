from decimal import Decimal

from flask import g

from app.domain.enums import (
    EntryStatus,
    EntryType,
    TransactionStatus,
    TransactionType,
)
from app.domain.events import TransferCompleted, TransferFailed
from app.domain.money import Money
from app.extensions import db
from app.models.account import Account
from app.models.ledger_entry import LedgerEntry
from app.models.transaction import Transaction
from app.services import balance_service, event_bus
from app.utils.exceptions import AccountNotFoundError, CurrencyMismatchError, InsufficientFundsError


def execute_transfer(
    source_account_id: int,
    target_account_id: int,
    amount: Decimal,
    currency: str,
    description: str = "",
    idempotency_key: str | None = None,
) -> Transaction:
    """Execute a double-entry transfer between two accounts.

    Locks accounts in sorted ID order to prevent deadlocks.
    Creates balanced debit + credit entries atomically.
    """
    if source_account_id == target_account_id:
        raise CurrencyMismatchError("Cannot transfer to the same account")

    if amount <= 0:
        raise CurrencyMismatchError("Transfer amount must be positive")

    # Check for existing transaction with this idempotency key
    if idempotency_key:
        existing = Transaction.query.filter_by(idempotency_key=idempotency_key).first()
        if existing:
            return existing

    # Lock accounts in sorted order to prevent deadlocks
    sorted_ids = sorted([source_account_id, target_account_id])
    accounts = {}
    for aid in sorted_ids:
        account = db.session.get(Account, aid)
        if account is None:
            raise AccountNotFoundError(f"Account {aid} not found")
        # SELECT FOR UPDATE for real databases (no-op on SQLite)
        try:
            db.session.execute(
                db.select(Account).where(Account.id == aid).with_for_update()
            )
        except Exception:
            pass  # SQLite doesn't support FOR UPDATE
        accounts[aid] = account

    source = accounts[source_account_id]
    target = accounts[target_account_id]

    # Validate currencies
    if source.currency != currency:
        raise CurrencyMismatchError(
            f"Source account currency {source.currency} does not match transfer currency {currency}"
        )
    if target.currency != currency:
        raise CurrencyMismatchError(
            f"Target account currency {target.currency} does not match transfer currency {currency}"
        )

    # Check sufficient funds (with lock on entries)
    balance = balance_service.get_balance(source_account_id, currency, use_lock=True)
    required = Money(amount, currency)
    if balance < required:
        raise InsufficientFundsError(
            f"Insufficient funds: balance={balance.amount}, required={amount}"
        )

    # Create transaction
    try:
        correlation_id = g.correlation_id
    except Exception:
        correlation_id = Transaction.generate_correlation_id()
    txn = Transaction(
        type=TransactionType.TRANSFER.value,
        status=TransactionStatus.COMPLETED.value,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        description=description,
    )
    db.session.add(txn)
    db.session.flush()

    # Debit source (negative amount)
    debit_entry = LedgerEntry(
        account_id=source_account_id,
        transaction_id=txn.id,
        amount=-amount,
        entry_type=EntryType.DEBIT.value,
        status=EntryStatus.SUCCESS.value,
        currency=currency,
    )

    # Credit target (positive amount)
    credit_entry = LedgerEntry(
        account_id=target_account_id,
        transaction_id=txn.id,
        amount=amount,
        entry_type=EntryType.CREDIT.value,
        status=EntryStatus.SUCCESS.value,
        currency=currency,
    )

    db.session.add(debit_entry)
    db.session.add(credit_entry)
    db.session.flush()

    balance_service.refresh_balance_cache(source_account_id, currency)
    balance_service.refresh_balance_cache(target_account_id, currency)

    balance_service.maybe_create_snapshot(source_account_id)
    balance_service.maybe_create_snapshot(target_account_id)

    # Emit domain event
    event_bus.publish(TransferCompleted(
        transaction_id=txn.id,
        source_account_id=source_account_id,
        target_account_id=target_account_id,
        amount=amount,
        currency=currency,
    ))

    return txn
