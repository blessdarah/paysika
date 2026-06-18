import logging

from flask import current_app
from flask_mail import Message
from rq import Queue, Retry
from redis import Redis

from app.domain.events import DepositCompleted, TransferCompleted, TransferFailed
from app.extensions import mail
from app.models.account import Account
from app.services import event_bus

logger = logging.getLogger(__name__)


def _get_user_email(account_id: int) -> str | None:
    account = Account.query.get(account_id)
    if account is None or account.user is None:
        return None
    return account.user.email


def _get_notification_queue() -> Queue:
    redis_url = current_app.config.get("CACHE_REDIS_URL", "redis://localhost:6379/0")
    conn = Redis.from_url(redis_url)
    return Queue("notifications", connection=conn)


def _send_email(subject: str, recipients: list[str], body: str) -> None:
    if not recipients:
        return
    if current_app.config.get("EMAIL_BACKGROUND", False):
        queue = _get_notification_queue()
        retry_max = current_app.config.get("EMAIL_RETRY_MAX", 3)
        retry_intervals = [
            int(s) for s in current_app.config.get("EMAIL_RETRY_INTERVALS", "60,300,3600").split(",")
        ]
        queue.enqueue(
            "app.services.email_jobs.send_email",
            subject,
            recipients,
            body,
            retry=Retry(max=retry_max, interval=retry_intervals),
        )
        logger.info("Email enqueued: subject=%r recipients=%s", subject, recipients)
        return
    msg = Message(subject=subject, recipients=recipients, body=body)
    try:
        mail.send(msg)
        logger.info("Email sent: subject=%r recipients=%s", subject, recipients)
    except Exception:
        logger.exception("Failed to send email: subject=%r recipients=%s", subject, recipients)


def _handle_transfer_completed(event: TransferCompleted) -> None:
    logger.info(
        "NOTIFICATION: Transfer %s completed. %s %s from account %s to account %s",
        event.transaction_id,
        event.amount,
        event.currency,
        event.source_account_id,
        event.target_account_id,
    )
    source_email = _get_user_email(event.source_account_id)
    target_email = _get_user_email(event.target_account_id)
    recipients = [e for e in [source_email, target_email] if e is not None]
    _send_email(
        subject=f"Transfer {event.transaction_id} completed",
        recipients=recipients,
        body=(
            f"Transfer {event.transaction_id} has been completed.\n\n"
            f"Amount: {event.amount} {event.currency}\n"
            f"From account: {event.source_account_id}\n"
            f"To account: {event.target_account_id}\n"
        ),
    )


def _handle_transfer_failed(event: TransferFailed) -> None:
    logger.warning(
        "NOTIFICATION: Transfer %s failed. Reason: %s",
        event.transaction_id,
        event.reason,
    )
    source_email = _get_user_email(event.source_account_id)
    if source_email:
        _send_email(
            subject=f"Transfer {event.transaction_id} failed",
            recipients=[source_email],
            body=(
                f"Transfer {event.transaction_id} has failed.\n\n"
                f"Amount: {event.amount} {event.currency}\n"
                f"From account: {event.source_account_id}\n"
                f"To account: {event.target_account_id}\n"
                f"Reason: {event.reason}\n"
            ),
        )


def _handle_deposit_completed(event: DepositCompleted) -> None:
    logger.info(
        "NOTIFICATION: Deposit %s completed. %s %s to account %s",
        event.transaction_id,
        event.amount,
        event.currency,
        event.account_id,
    )
    email = _get_user_email(event.account_id)
    if email:
        _send_email(
            subject=f"Deposit {event.transaction_id} completed",
            recipients=[email],
            body=(
                f"Deposit {event.transaction_id} has been completed.\n\n"
                f"Amount: {event.amount} {event.currency}\n"
                f"Account: {event.account_id}\n"
            ),
        )


def register_handlers() -> None:
    event_bus.subscribe(TransferCompleted, _handle_transfer_completed)
    event_bus.subscribe(TransferFailed, _handle_transfer_failed)
    event_bus.subscribe(DepositCompleted, _handle_deposit_completed)
