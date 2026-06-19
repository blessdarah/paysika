from decimal import Decimal

from flask import g
from sqlalchemy import exc as sa_exc

from app.domain.enums import (
    EntryStatus,
    EntryType,
    TransactionStatus,
    TransactionType,
)
from app.domain.events import DepositCompleted, DepositFailed, DepositInitiated
from app.extensions import db
from app.models.ledger_entry import LedgerEntry
from app.models.transaction import Transaction
from app.services import account_service, balance_service, event_bus
from app.services.lock import lock_accounts
from app.utils.exceptions import CurrencyMismatchError, InvalidTransactionStateError


def _build_correlation_id() -> str:
    try:
        return g.correlation_id
    except Exception:
        return Transaction.generate_correlation_id()


def initiate_deposit(
    account_id: int,
    amount: Decimal,
    currency: str,
    description: str = "",
    idempotency_key: str | None = None,
    provider: str = "mock",
) -> Transaction:
    """Create a PENDING deposit transaction to be confirmed later by a provider webhook."""
    if amount <= 0:
        raise CurrencyMismatchError("Deposit amount must be positive")

    if idempotency_key:
        existing = Transaction.query.filter_by(idempotency_key=idempotency_key).first()
        if existing:
            return existing

    account = account_service.get_account(account_id)
    if account.currency != currency:
        raise CurrencyMismatchError(
            f"Account currency {account.currency} does not match deposit currency {currency}"
        )

    correlation_id = _build_correlation_id()
    txn = Transaction(
        type=TransactionType.DEPOSIT.value,
        status=TransactionStatus.PENDING.value,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        description=description or f"Deposit {amount} {currency}",
        provider=provider,
        metadata_={
            "account_id": account_id,
            "amount": str(amount),
            "currency": currency,
        },
    )
    db.session.add(txn)

    if idempotency_key:
        try:
            with db.session.begin_nested():
                db.session.flush()
        except sa_exc.IntegrityError:
            return Transaction.query.filter_by(
                idempotency_key=idempotency_key
            ).one()
    else:
        db.session.flush()

    event_bus.publish(DepositInitiated(
        transaction_id=txn.id,
        account_id=account_id,
        amount=amount,
        currency=currency,
    ))

    return txn


def confirm_deposit(
    transaction_id: int,
    provider_reference: str,
) -> Transaction:
    """Confirm a pending deposit — create ledger entries, complete the transaction."""
    txn = db.session.get(Transaction, transaction_id)
    if txn is None:
        raise InvalidTransactionStateError(f"Transaction {transaction_id} not found")
    if txn.status != TransactionStatus.PENDING.value:
        raise InvalidTransactionStateError(
            f"Transaction {transaction_id} is {txn.status}, expected PENDING"
        )

    meta = txn.metadata_ or {}
    account_id = meta.get("account_id")
    amount = Decimal(meta.get("amount", "0"))
    currency = meta.get("currency", "")

    if not account_id or amount <= 0 or not currency:
        raise InvalidTransactionStateError(
            f"Transaction {transaction_id} has incomplete metadata"
        )

    account = account_service.get_account(account_id)
    clearing_account = account_service.get_or_create_platform_clearing_account(currency)

    lock_accounts([account.id, clearing_account.id])

    debit_entry = LedgerEntry(
        account_id=clearing_account.id,
        transaction_id=txn.id,
        amount=-amount,
        entry_type=EntryType.DEBIT.value,
        status=EntryStatus.SUCCESS.value,
        currency=currency,
    )

    credit_entry = LedgerEntry(
        account_id=account.id,
        transaction_id=txn.id,
        amount=amount,
        entry_type=EntryType.CREDIT.value,
        status=EntryStatus.SUCCESS.value,
        currency=currency,
    )

    db.session.add(debit_entry)
    db.session.add(credit_entry)

    txn.status = TransactionStatus.COMPLETED.value
    txn.provider_reference = provider_reference

    db.session.flush()

    balance_service.refresh_balance_cache(account.id, currency)
    balance_service.refresh_balance_cache(clearing_account.id, currency)

    balance_service.maybe_create_snapshot(account.id)
    balance_service.maybe_create_snapshot(clearing_account.id)

    event_bus.publish(DepositCompleted(
        transaction_id=txn.id,
        account_id=account.id,
        amount=amount,
        currency=currency,
    ))

    return txn


def fail_deposit(
    transaction_id: int,
    reason: str = "",
) -> Transaction:
    """Mark a pending deposit as failed."""
    txn = db.session.get(Transaction, transaction_id)
    if txn is None:
        raise InvalidTransactionStateError(f"Transaction {transaction_id} not found")
    if txn.status != TransactionStatus.PENDING.value:
        raise InvalidTransactionStateError(
            f"Transaction {transaction_id} is {txn.status}, expected PENDING"
        )

    txn.status = TransactionStatus.FAILED.value
    db.session.flush()

    meta = txn.metadata_ or {}

    event_bus.publish(DepositFailed(
        transaction_id=txn.id,
        account_id=meta.get("account_id", 0),
        amount=Decimal(meta.get("amount", "0")),
        currency=meta.get("currency", ""),
        reason=reason,
    ))

    return txn


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

    if idempotency_key:
        existing = Transaction.query.filter_by(idempotency_key=idempotency_key).first()
        if existing:
            return existing

    account = account_service.get_account(account_id)
    if account.currency != currency:
        raise CurrencyMismatchError(
            f"Account currency {account.currency} does not match deposit currency {currency}"
        )

    clearing_account = account_service.get_or_create_platform_clearing_account(currency)

    lock_accounts([account.id, clearing_account.id])

    correlation_id = _build_correlation_id()
    txn = Transaction(
        type=TransactionType.DEPOSIT.value,
        status=TransactionStatus.COMPLETED.value,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        description=description or f"Deposit {amount} {currency}",
    )
    db.session.add(txn)

    if idempotency_key:
        try:
            with db.session.begin_nested():
                db.session.flush()
        except sa_exc.IntegrityError:
            return Transaction.query.filter_by(
                idempotency_key=idempotency_key
            ).one()
    else:
        db.session.flush()

    debit_entry = LedgerEntry(
        account_id=clearing_account.id,
        transaction_id=txn.id,
        amount=-amount,
        entry_type=EntryType.DEBIT.value,
        status=EntryStatus.SUCCESS.value,
        currency=currency,
    )

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

    balance_service.refresh_balance_cache(account_id, currency)
    balance_service.refresh_balance_cache(clearing_account.id, currency)

    balance_service.maybe_create_snapshot(account_id)
    balance_service.maybe_create_snapshot(clearing_account.id)

    event_bus.publish(DepositCompleted(
        transaction_id=txn.id,
        account_id=account_id,
        amount=amount,
        currency=currency,
    ))

    return txn
