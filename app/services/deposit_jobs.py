import logging
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import requests

logger = logging.getLogger(__name__)

_app = None


def init(app):
    global _app
    _app = app


def _get_deposit_queue():
    from rq import Queue
    from redis import Redis

    if _app is None:
        return None
    redis_url = _app.config.get("CACHE_REDIS_URL", "redis://localhost:6379/0")
    conn = Redis.from_url(redis_url)
    return Queue("deposits", connection=conn)


def _notify_provider(
    transaction_id: int,
    amount: str,
    currency: str,
) -> None:
    """Call the mock payment provider to register a pending deposit.

    Runs inside an RQ worker process — must create its own app context.
    Stores the provider's ``payment_id`` on the transaction so the
    recovery job can distinguish notified deposits from orphaned ones.
    """
    if _app is None:
        logger.error("Deposit worker not initialized")
        return

    with _app.app_context():
        from app.extensions import db
        from app.models.transaction import Transaction

        provider_url = _app.config.get(
            "MOCK_PROVIDER_URL",
            os.getenv("MOCK_PROVIDER_URL", "http://localhost:8090"),
        )

        try:
            resp = requests.post(
                f"{provider_url}/create-payment",
                json={
                    "reference_id": str(transaction_id),
                    "amount": amount,
                    "currency": currency,
                },
                timeout=5,
            )
        except requests.RequestException as e:
            logger.warning(
                "Provider unreachable for transaction=%s: %s",
                transaction_id, e,
            )
            raise  # Let RQ retry

        if not resp.ok:
            logger.warning(
                "Provider returned %s for transaction=%s: %s",
                resp.status_code, transaction_id, resp.text,
            )
            raise RuntimeError(f"Provider returned {resp.status_code}")

        provider_data = resp.json()
        payment_id = provider_data.get("payment_id", "")

        txn = db.session.get(Transaction, transaction_id)
        if txn is None:
            logger.error("Transaction %s disappeared", transaction_id)
            return

        txn.provider_reference = payment_id
        db.session.commit()

        logger.info(
            "Provider notified: transaction=%s payment=%s",
            transaction_id, payment_id,
        )


def notify_provider(transaction_id: int, amount: str, currency: str) -> None:
    """RQ‑visible wrapper so the import is safe outside app context."""
    _notify_provider(transaction_id, amount, currency)


def recover_orphan_deposits(delay_minutes: int = 30) -> int:
    """Find PENDING deposits older than ``delay_minutes`` that were never
    acknowledged by the provider, and re‑enqueue their notification.

    Returns the number of deposits re‑enqueued.
    """
    if _app is None:
        logger.error("Deposit worker not initialized")
        return 0

    with _app.app_context():
        from app.extensions import db
        from app.models.transaction import Transaction
        from app.domain.enums import TransactionStatus, TransactionType

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=delay_minutes)

        orphans = (
            db.session.query(Transaction)
            .filter(
                Transaction.type == TransactionType.DEPOSIT.value,
                Transaction.status == TransactionStatus.PENDING.value,
                Transaction.provider_reference.is_(None),
                Transaction.created_at < cutoff,
            )
            .all()
        )

        queue = _get_deposit_queue()
        if queue is None:
            logger.error("Cannot enqueue — no deposit queue available")
            return 0

        for txn in orphans:
            meta = txn.metadata_ or {}
            queue.enqueue(
                notify_provider,
                txn.id,
                meta.get("amount", "0"),
                meta.get("currency", ""),
            )
            logger.info(
                "Re‑enqueued orphan deposit: transaction=%s created_at=%s",
                txn.id, txn.created_at,
            )

        logger.info("Recovered %d orphan deposit(s)", len(orphans))
        return len(orphans)
