from app.extensions import db
from app.models.base import BaseMixin


class Account(BaseMixin, db.Model):
    __tablename__ = "accounts"
    __table_args__ = (
        db.UniqueConstraint("user_id", "currency", name="uq_account_user_currency"),
    )

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    name = db.Column(db.String(120), nullable=False, default="")
    is_system = db.Column(db.Boolean, nullable=False, default=False)

    user = db.relationship("User", back_populates="accounts")
    ledger_entries = db.relationship(
        "LedgerEntry", back_populates="account", lazy="dynamic"
    )
    balance_snapshots = db.relationship(
        "BalanceSnapshot", back_populates="account", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<Account {self.id} {self.currency} user={self.user_id}>"
