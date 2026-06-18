import uuid

from app.extensions import db
from app.models.base import LedgerBaseMixin


class Transaction(LedgerBaseMixin, db.Model):
    __tablename__ = "transactions"

    type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="COMPLETED")
    idempotency_key = db.Column(db.String(255), unique=True, nullable=True, index=True)
    correlation_id = db.Column(db.String(64), nullable=True)
    description = db.Column(db.String(500), nullable=True)
    metadata_ = db.Column("metadata", db.JSON, nullable=True)

    entries = db.relationship("LedgerEntry", back_populates="transaction", lazy="select")

    def __repr__(self) -> str:
        return f"<Transaction {self.id} {self.type} {self.status}>"

    @staticmethod
    def generate_correlation_id() -> str:
        return uuid.uuid4().hex
