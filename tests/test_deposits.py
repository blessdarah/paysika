from decimal import Decimal

import pytest

from app.domain.enums import Currency, EntryType
from app.domain.money import Money
from app.extensions import db
from app.models.account import Account
from app.models.ledger_entry import LedgerEntry
from app.models.user import User
from app.services import account_service, balance_service, deposit_service


@pytest.fixture()
def user_account(app):
    """Create a user with a USD account."""
    user = User(username="deposituser", email="deposit@test.com")
    user.set_password("password123")
    db.session.add(user)
    db.session.flush()

    account = account_service.create_account(user.id, "USD", "Deposit Test")
    return {"user_id": user.id, "account_id": account.id}


class TestDeposit:
    def test_deposit_creates_balanced_entries(self, app, user_account):
        txn = deposit_service.execute_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("500.0000"),
            currency="USD",
        )

        entries = LedgerEntry.query.filter_by(transaction_id=txn.id).all()
        assert len(entries) == 2

        # Double-entry invariant: sum of entries is zero
        total = sum(e.amount for e in entries)
        assert total == Decimal("0")

    def test_deposit_increases_balance(self, app, user_account):
        deposit_service.execute_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("500.0000"),
            currency="USD",
        )

        balance = balance_service.get_balance(user_account["account_id"], "USD")
        assert balance == Money("500.0000", Currency.USD)

    def test_multiple_deposits(self, app, user_account):
        deposit_service.execute_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("100.0000"),
            currency="USD",
        )
        deposit_service.execute_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("200.0000"),
            currency="USD",
        )

        balance = balance_service.get_balance(user_account["account_id"], "USD")
        assert balance == Money("300.0000", Currency.USD)

    def test_idempotent_deposit(self, app, user_account):
        key = "deposit-idem-001"
        txn1 = deposit_service.execute_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("500.0000"),
            currency="USD",
            idempotency_key=key,
        )
        txn2 = deposit_service.execute_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("500.0000"),
            currency="USD",
            idempotency_key=key,
        )
        assert txn1.id == txn2.id

        balance = balance_service.get_balance(user_account["account_id"], "USD")
        assert balance == Money("500.0000", Currency.USD)

    def test_currency_mismatch_raises(self, app, user_account):
        from app.utils.exceptions import CurrencyMismatchError
        with pytest.raises(CurrencyMismatchError):
            deposit_service.execute_deposit(
                account_id=user_account["account_id"],
                amount=Decimal("500.0000"),
                currency="EUR",
            )
