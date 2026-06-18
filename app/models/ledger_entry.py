from app.extensions import db
from app.models.base import LedgerBaseMixin


class LedgerEntry(LedgerBaseMixin, db.Model):
    __tablename__ = "ledger_entries"

    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=False, index=True)
    amount = db.Column(db.Numeric(19, 4), nullable=False)
    entry_type = db.Column(db.String(10), nullable=False)  # DEBIT or CREDIT
    status = db.Column(db.String(10), nullable=False, default="SUCCESS")
    currency = db.Column(db.String(3), nullable=False)
    metadata_ = db.Column("metadata", db.JSON, nullable=True)

    account = db.relationship("Account", back_populates="ledger_entries")
    transaction = db.relationship("Transaction", back_populates="entries")

    def __repr__(self) -> str:
        return f"<LedgerEntry {self.id} {self.entry_type} {self.amount} {self.currency}>"
