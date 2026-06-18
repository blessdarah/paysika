from decimal import Decimal

from flask import current_app, g

from app.domain.enums import (
    EntryStatus,
    EntryType,
    TransactionStatus,
    TransactionType,
)
from app.extensions import cache, db
from app.models.account import Account
from app.models.ledger_entry import LedgerEntry
from app.models.transaction import Transaction
from app.services import account_service, balance_service
from app.domain.money import Money
from app.utils.exceptions import (
    AccountNotFoundError,
    CurrencyMismatchError,
    InsufficientFundsError,
)

# Static exchange rates (in production, use a real FX provider)
_RATES = {
    ("USD", "EUR"): Decimal("0.92"),
    ("EUR", "USD"): Decimal("1.09"),
    ("USD", "GBP"): Decimal("0.79"),
    ("GBP", "USD"): Decimal("1.27"),
    ("EUR", "GBP"): Decimal("0.86"),
    ("GBP", "EUR"): Decimal("1.16"),
    ("USD", "NGN"): Decimal("1550.00"),
    ("NGN", "USD"): Decimal("0.000645"),
    ("USD", "XAF"): Decimal("605.00"),
    ("XAF", "USD"): Decimal("0.001653"),
}


def _fx_cache_key(source: str, target: str) -> str:
    return f"fx:{source}:{target}"


def get_exchange_rate(source_currency: str, target_currency: str) -> Decimal:
    if source_currency == target_currency:
        return Decimal("1")

    cached = cache.get(_fx_cache_key(source_currency, target_currency))
    if cached is not None:
        return Decimal(cached)

    key = (source_currency, target_currency)
    rate = _RATES.get(key)
    if rate is None:
        raise CurrencyMismatchError(
            f"No exchange rate available for {source_currency} -> {target_currency}"
        )

    ttl = current_app.config.get("FX_RATE_CACHE_TTL", 3600)
    cache.set(_fx_cache_key(source_currency, target_currency), str(rate), timeout=ttl)

    return rate


def execute_fx_transfer(
    source_account_id: int,
    target_account_id: int,
    amount: Decimal,
    source_currency: str,
    target_currency: str,
    description: str = "",
    idempotency_key: str | None = None,
) -> Transaction:
    """Execute a cross-currency transfer with 4 ledger entries.

    1. Debit sender in source currency
    2. Credit FX pool in source currency
    3. Debit FX pool in target currency
    4. Credit receiver in target currency
    """
    if source_currency == target_currency:
        raise CurrencyMismatchError("Use regular transfer for same-currency")

    if amount <= 0:
        raise CurrencyMismatchError("Transfer amount must be positive")

    if idempotency_key:
        existing = Transaction.query.filter_by(idempotency_key=idempotency_key).first()
        if existing:
            return existing

    rate = get_exchange_rate(source_currency, target_currency)
    target_amount = (amount * rate).quantize(Decimal("0.0001"))

    source_account = db.session.get(Account, source_account_id)
    if source_account is None:
        raise AccountNotFoundError(f"Source account {source_account_id} not found")
    if source_account.currency != source_currency:
        raise CurrencyMismatchError("Source account currency mismatch")

    target_account = db.session.get(Account, target_account_id)
    if target_account is None:
        raise AccountNotFoundError(f"Target account {target_account_id} not found")
    if target_account.currency != target_currency:
        raise CurrencyMismatchError("Target account currency mismatch")

    # Check balance
    balance = balance_service.get_balance(source_account_id, source_currency)
    if balance < Money(amount, source_currency):
        raise InsufficientFundsError(
            f"Insufficient funds: balance={balance.amount}, required={amount}"
        )

    # Get FX pool accounts
    fx_source = account_service.get_or_create_platform_clearing_account(source_currency)
    fx_target = account_service.get_or_create_platform_clearing_account(target_currency)

    correlation_id = getattr(g, "correlation_id", None) or Transaction.generate_correlation_id()
    txn = Transaction(
        type=TransactionType.FX_EXCHANGE.value,
        status=TransactionStatus.COMPLETED.value,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        description=description or f"FX {amount} {source_currency} -> {target_amount} {target_currency}",
        metadata_={"exchange_rate": str(rate)},
    )
    db.session.add(txn)
    db.session.flush()

    # Entry 1: Debit sender in source currency
    db.session.add(LedgerEntry(
        account_id=source_account_id,
        transaction_id=txn.id,
        amount=-amount,
        entry_type=EntryType.DEBIT.value,
        status=EntryStatus.SUCCESS.value,
        currency=source_currency,
    ))

    # Entry 2: Credit FX pool in source currency
    db.session.add(LedgerEntry(
        account_id=fx_source.id,
        transaction_id=txn.id,
        amount=amount,
        entry_type=EntryType.CREDIT.value,
        status=EntryStatus.SUCCESS.value,
        currency=source_currency,
    ))

    # Entry 3: Debit FX pool in target currency
    db.session.add(LedgerEntry(
        account_id=fx_target.id,
        transaction_id=txn.id,
        amount=-target_amount,
        entry_type=EntryType.DEBIT.value,
        status=EntryStatus.SUCCESS.value,
        currency=target_currency,
    ))

    # Entry 4: Credit receiver in target currency
    db.session.add(LedgerEntry(
        account_id=target_account_id,
        transaction_id=txn.id,
        amount=target_amount,
        entry_type=EntryType.CREDIT.value,
        status=EntryStatus.SUCCESS.value,
        currency=target_currency,
    ))

    db.session.flush()

    balance_service.invalidate_balance_cache(source_account_id)
    balance_service.invalidate_balance_cache(target_account_id)
    balance_service.invalidate_balance_cache(fx_source.id)
    balance_service.invalidate_balance_cache(fx_target.id)

    return txn
