from decimal import Decimal

from flask import current_app
from sqlalchemy import func

from app.domain.enums import Currency, EntryStatus
from app.domain.money import Money
from app.extensions import cache, db
from app.models.balance_snapshot import BalanceSnapshot
from app.models.ledger_entry import LedgerEntry


def _balance_cache_key(account_id: int) -> str:
    return f"balance:{account_id}"


def get_balance(
    account_id: int, currency: str, use_lock: bool = False, force: bool = False
) -> Money:
    """Compute account balance from ledger entries using snapshot optimization.

    If use_lock=True, uses SELECT FOR UPDATE on the entries to prevent
    concurrent reads during transfers (pessimistic locking).
    Cache is only used when use_lock=False and force=False.
    """
    if not use_lock and not force:
        cached = cache.get(_balance_cache_key(account_id))
        if cached is not None:
            return Money(Decimal(cached["amount"]), cached["currency"])

    # Find the latest snapshot for this account
    snapshot = (
        BalanceSnapshot.query
        .filter_by(account_id=account_id)
        .order_by(BalanceSnapshot.id.desc())
        .first()
    )

    if snapshot:
        snapshot_balance = snapshot.balance
        last_entry_id = snapshot.last_entry_id or 0
    else:
        snapshot_balance = Decimal("0")
        last_entry_id = 0

    # Sum entries after the snapshot
    query = (
        db.session.query(func.coalesce(func.sum(LedgerEntry.amount), Decimal("0")))
        .filter(
            LedgerEntry.account_id == account_id,
            LedgerEntry.status == EntryStatus.SUCCESS.value,
            LedgerEntry.id > last_entry_id,
        )
    )

    if use_lock:
        # Lock the matching rows first (FOR UPDATE not allowed on aggregate queries in PostgreSQL)
        db.session.query(LedgerEntry.id).filter(
            LedgerEntry.account_id == account_id,
            LedgerEntry.status == EntryStatus.SUCCESS.value,
            LedgerEntry.id > last_entry_id,
        ).with_for_update().all()

    delta = query.scalar() or Decimal("0")
    total = snapshot_balance + delta
    result = Money(total, currency)

    if not use_lock:
        ttl = current_app.config.get("BALANCE_CACHE_TTL", 300)
        cache.set(
            _balance_cache_key(account_id),
            {"amount": str(result.amount), "currency": currency},
            timeout=ttl,
        )
    elif force:
        # Write-through: when called via refresh_balance_cache, cache the result
        ttl = current_app.config.get("BALANCE_CACHE_TTL", 300)
        cache.set(
            _balance_cache_key(account_id),
            {"amount": str(result.amount), "currency": currency},
            timeout=ttl,
        )

    return result


def invalidate_balance_cache(account_id: int) -> None:
    """Delete the cached balance for an account."""
    cache.delete(_balance_cache_key(account_id))


def refresh_balance_cache(account_id: int, currency: str) -> None:
    """Recompute and write-through to cache (no delete, avoids thundering herd)."""
    get_balance(account_id, currency, force=True)


def _compute_and_create_snapshot(account_id: int) -> BalanceSnapshot | None:
    """Execute the full snapshot computation and creation (runs in RQ worker)."""
    threshold = current_app.config.get("LEDGER_SNAPSHOT_THRESHOLD", 100)

    latest_snapshot = (
        BalanceSnapshot.query
        .filter_by(account_id=account_id)
        .order_by(BalanceSnapshot.id.desc())
        .first()
    )

    last_entry_id = latest_snapshot.last_entry_id if latest_snapshot else 0
    last_entry_id = last_entry_id or 0

    entry_count = (
        LedgerEntry.query
        .filter(
            LedgerEntry.account_id == account_id,
            LedgerEntry.status == EntryStatus.SUCCESS.value,
            LedgerEntry.id > last_entry_id,
        )
        .count()
    )

    if entry_count < threshold:
        return None

    latest_entry = (
        LedgerEntry.query
        .filter(
            LedgerEntry.account_id == account_id,
            LedgerEntry.status == EntryStatus.SUCCESS.value,
        )
        .order_by(LedgerEntry.id.desc())
        .first()
    )

    if not latest_entry:
        return None

    total_balance = (
        db.session.query(func.coalesce(func.sum(LedgerEntry.amount), Decimal("0")))
        .filter(
            LedgerEntry.account_id == account_id,
            LedgerEntry.status == EntryStatus.SUCCESS.value,
        )
        .scalar()
    ) or Decimal("0")

    snapshot = BalanceSnapshot(
        account_id=account_id,
        balance=total_balance,
        entry_count=entry_count + (latest_snapshot.entry_count if latest_snapshot else 0),
        last_entry_id=latest_entry.id,
    )
    db.session.add(snapshot)
    return snapshot


def maybe_create_snapshot(account_id: int) -> None:
    """Lightweight check: enqueue a background snapshot job if threshold exceeded."""
    threshold = current_app.config.get("LEDGER_SNAPSHOT_THRESHOLD", 100)

    latest_snapshot = (
        BalanceSnapshot.query
        .filter_by(account_id=account_id)
        .order_by(BalanceSnapshot.id.desc())
        .first()
    )

    last_entry_id = latest_snapshot.last_entry_id if latest_snapshot else 0
    last_entry_id = last_entry_id or 0

    entry_count = (
        LedgerEntry.query
        .filter(
            LedgerEntry.account_id == account_id,
            LedgerEntry.status == EntryStatus.SUCCESS.value,
            LedgerEntry.id > last_entry_id,
        )
        .count()
    )

    if entry_count >= threshold:
        try:
            queue = current_app.extensions["deposit_queue"]
            queue.enqueue(
                "app.services.balance_jobs.create_snapshot",
                account_id,
            )
        except Exception:
            current_app.logger.exception(
                "Failed to enqueue snapshot job for account %s", account_id,
            )
