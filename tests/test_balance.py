from decimal import Decimal

import pytest

from app.domain.enums import Currency, EntryStatus, EntryType, TransactionStatus, TransactionType
from app.domain.money import Money
from app.extensions import db
from app.models.account import Account
from app.models.balance_snapshot import BalanceSnapshot
from app.models.ledger_entry import LedgerEntry
from app.models.transaction import Transaction
from app.models.user import User
from app.services import balance_service


@pytest.fixture()
def user_with_account(app):
    """Create a user with a USD account."""
    user = User(username="balanceuser", email="balance@test.com")
    user.set_password("password123")
    db.session.add(user)
    db.session.flush()

    account = Account(user_id=user.id, currency="USD", name="Test Account")
    db.session.add(account)
    db.session.flush()
    return {"user_id": user.id, "account_id": account.id}


def _create_entry(account_id, amount, entry_type, status=EntryStatus.SUCCESS.value):
    """Helper to create a ledger entry with a parent transaction."""
    txn = Transaction(
        type=TransactionType.DEPOSIT.value,
        status=TransactionStatus.COMPLETED.value,
    )
    db.session.add(txn)
    db.session.flush()

    entry = LedgerEntry(
        account_id=account_id,
        transaction_id=txn.id,
        amount=Decimal(str(amount)),
        entry_type=entry_type,
        status=status,
        currency="USD",
    )
    db.session.add(entry)
    db.session.flush()
    return entry


class TestGetBalance:
    def test_zero_balance_empty_account(self, app, user_with_account):
        balance = balance_service.get_balance(user_with_account["account_id"], "USD")
        assert balance == Money.zero(Currency.USD)

    def test_balance_computed_from_entries(self, app, user_with_account):
        account_id = user_with_account["account_id"]
        # Credit 100
        _create_entry(account_id, "100.0000", EntryType.CREDIT.value)
        # Debit -30
        _create_entry(account_id, "-30.0000", EntryType.DEBIT.value)

        balance = balance_service.get_balance(account_id, "USD")
        assert balance == Money("70.0000", Currency.USD)

    def test_only_success_entries_counted(self, app, user_with_account):
        account_id = user_with_account["account_id"]
        _create_entry(account_id, "100.0000", EntryType.CREDIT.value, EntryStatus.SUCCESS.value)
        _create_entry(account_id, "50.0000", EntryType.CREDIT.value, EntryStatus.FAILED.value)
        _create_entry(account_id, "25.0000", EntryType.CREDIT.value, EntryStatus.PENDING.value)

        balance = balance_service.get_balance(account_id, "USD")
        assert balance == Money("100.0000", Currency.USD)


class TestSnapshotOptimization:
    def test_snapshot_used_for_balance(self, app, user_with_account):
        account_id = user_with_account["account_id"]
        # Create an entry and snapshot
        entry = _create_entry(account_id, "200.0000", EntryType.CREDIT.value)
        snapshot = BalanceSnapshot(
            account_id=account_id,
            balance=Decimal("200.0000"),
            entry_count=1,
            last_entry_id=entry.id,
        )
        db.session.add(snapshot)
        db.session.flush()

        # Create another entry after the snapshot
        _create_entry(account_id, "-50.0000", EntryType.DEBIT.value)

        balance = balance_service.get_balance(account_id, "USD")
        assert balance == Money("150.0000", Currency.USD)

    def test_maybe_create_snapshot_below_threshold(self, app, user_with_account):
        app.config["LEDGER_SNAPSHOT_THRESHOLD"] = 5
        account_id = user_with_account["account_id"]
        # Create 3 entries (below threshold of 5)
        for i in range(3):
            _create_entry(account_id, "10.0000", EntryType.CREDIT.value)

        result = balance_service.maybe_create_snapshot(account_id)
        assert result is None

    def test_maybe_create_snapshot_at_threshold(self, app, user_with_account):
        app.config["LEDGER_SNAPSHOT_THRESHOLD"] = 3
        account_id = user_with_account["account_id"]
        for i in range(3):
            _create_entry(account_id, "10.0000", EntryType.CREDIT.value)

        result = balance_service.maybe_create_snapshot(account_id)
        assert result is not None
        assert result.balance == Decimal("30.0000")
        assert result.account_id == account_id
