from app.extensions import db
from app.models.base import LedgerBaseMixin


class IdempotencyRecord(LedgerBaseMixin, db.Model):
    __tablename__ = "idempotency_records"

    key = db.Column(db.String(255), unique=True, nullable=False, index=True)
    request_hash = db.Column(db.String(64), nullable=False)
    response_code = db.Column(db.Integer, nullable=False)
    response_body = db.Column(db.JSON, nullable=False)

    def __repr__(self) -> str:
        return f"<IdempotencyRecord key={self.key}>"
