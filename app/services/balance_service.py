from decimal import Decimal

from flask import current_app
from sqlalchemy import func

from app.domain.enums import Currency, EntryStatus
from app.domain.money import Money
from app.extensions import db
from app.models.balance_snapshot import BalanceSnapshot
from app.models.ledger_entry import LedgerEntry


def get_balance(account_id: int, currency: str, use_lock: bool = False) -> Money:
    """Compute account balance from ledger entries using snapshot optimization.

    If use_lock=True, uses SELECT FOR UPDATE on the entries to prevent
    concurrent reads during transfers (pessimistic locking).
    """
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
        # Lock the entries to prevent concurrent modifications
        query = query.with_for_update()

    delta = query.scalar() or Decimal("0")
    total = snapshot_balance + delta
    return Money(total, currency)


def maybe_create_snapshot(account_id: int) -> BalanceSnapshot | None:
    """Create a balance snapshot if the number of entries since last snapshot exceeds threshold."""
    threshold = current_app.config.get("LEDGER_SNAPSHOT_THRESHOLD", 100)

    latest_snapshot = (
        BalanceSnapshot.query
        .filter_by(account_id=account_id)
        .order_by(BalanceSnapshot.id.desc())
        .first()
    )

    last_entry_id = latest_snapshot.last_entry_id if latest_snapshot else 0
    last_entry_id = last_entry_id or 0

    # Count entries since last snapshot
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

    # Get the latest entry id
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

    # Compute full balance
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
