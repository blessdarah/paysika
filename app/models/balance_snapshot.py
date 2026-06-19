from app.extensions import db
from app.models.base import LedgerBaseMixin


class BalanceSnapshot(LedgerBaseMixin, db.Model):
    __tablename__ = "balance_snapshots"

    __table_args__ = (
        db.Index("ix_balance_snapshot_account_id_desc", "account_id", db.text("id DESC")),
    )

    account_id = db.Column(
        db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True
    )
    balance = db.Column(db.Numeric(19, 4), nullable=False)
    entry_count = db.Column(db.Integer, nullable=False, default=0)
    last_entry_id = db.Column(
        db.Integer, db.ForeignKey("ledger_entries.id"), nullable=True
    )

    account = db.relationship("Account", back_populates="balance_snapshots")

    def __repr__(self) -> str:
        return f"<BalanceSnapshot account={self.account_id} balance={self.balance}>"
