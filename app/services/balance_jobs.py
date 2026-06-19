import logging

logger = logging.getLogger(__name__)

_app = None


def init(app):
    global _app
    _app = app


def create_snapshot(account_id: int) -> None:
    if _app is None:
        logger.error("Snapshot worker not initialized")
        return
    with _app.app_context():
        from app.extensions import db
        from app.services.balance_service import _compute_and_create_snapshot

        _compute_and_create_snapshot(account_id)
        db.session.commit()
