import logging

from flask_mail import Message

logger = logging.getLogger(__name__)


_app = None


def init(app):
    global _app
    _app = app


def send_email(subject: str, recipients: list[str], body: str) -> None:
    if _app is None:
        logger.error("Email worker not initialized")
        return
    with _app.app_context():
        from app.extensions import mail

        msg = Message(subject=subject, recipients=recipients, body=body)
        try:
            mail.send(msg)
            logger.info("Email sent: subject=%r recipients=%s", subject, recipients)
        except Exception:
            logger.exception(
                "Failed to send email: subject=%r recipients=%s", subject, recipients
            )
