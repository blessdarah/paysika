import logging

from app.domain.events import DepositCompleted, TransferCompleted, TransferFailed
from app.services import event_bus

logger = logging.getLogger(__name__)


def _handle_transfer_completed(event: TransferCompleted) -> None:
    logger.info(
        "NOTIFICATION: Transfer %s completed. %s %s from account %s to account %s",
        event.transaction_id,
        event.amount,
        event.currency,
        event.source_account_id,
        event.target_account_id,
    )


def _handle_transfer_failed(event: TransferFailed) -> None:
    logger.warning(
        "NOTIFICATION: Transfer %s failed. Reason: %s",
        event.transaction_id,
        event.reason,
    )


def _handle_deposit_completed(event: DepositCompleted) -> None:
    logger.info(
        "NOTIFICATION: Deposit %s completed. %s %s to account %s",
        event.transaction_id,
        event.amount,
        event.currency,
        event.account_id,
    )


def register_handlers() -> None:
    event_bus.subscribe(TransferCompleted, _handle_transfer_completed)
    event_bus.subscribe(TransferFailed, _handle_transfer_failed)
    event_bus.subscribe(DepositCompleted, _handle_deposit_completed)
