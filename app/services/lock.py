import logging

from sqlalchemy import exc as sa_exc

from app.extensions import db
from app.models.account import Account

logger = logging.getLogger(__name__)


def lock_accounts(account_ids: list[int]) -> None:
    for aid in sorted(account_ids):
        try:
            db.session.execute(
                db.select(Account).where(Account.id == aid).with_for_update()
            )
        except sa_exc.OperationalError:
            logger.warning(
                "FOR UPDATE not supported, skipping lock for account %s", aid
            )
