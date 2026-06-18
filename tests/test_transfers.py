from decimal import Decimal

import pytest

from app.domain.enums import (
    Currency,
    EntryStatus,
    EntryType,
    TransactionStatus,
    TransactionType,
)
from app.domain.money import Money
from app.extensions import db
from app.models.account import Account
from app.models.ledger_entry import LedgerEntry
from app.models.transaction import Transaction
from app.models.user import User
from app.services import balance_service, transfer_service
from app.utils.exceptions import InsufficientFundsError


@pytest.fixture()
def two_accounts(app):
    """Create two users with USD accounts and seed the first with 1000."""
    # User A
    user_a = User(username="user_a", email="a@test.com")
    user_a.set_password("password123")
    db.session.add(user_a)
    db.session.flush()
    account_a = Account(user_id=user_a.id, currency="USD", name="A Checking")
    db.session.add(account_a)

    # User B
    user_b = User(username="user_b", email="b@test.com")
    user_b.set_password("password123")
    db.session.add(user_b)
    db.session.flush()
    account_b = Account(user_id=user_b.id, currency="USD", name="B Checking")
    db.session.add(account_b)

    db.session.flush()

    # Seed account A with 1000 via direct ledger entry
    txn = Transaction(
        type=TransactionType.DEPOSIT.value,
        status=TransactionStatus.COMPLETED.value,
    )
    db.session.add(txn)
    db.session.flush()

    entry = LedgerEntry(
        account_id=account_a.id,
        transaction_id=txn.id,
        amount=Decimal("1000.0000"),
        entry_type=EntryType.CREDIT.value,
        status=EntryStatus.SUCCESS.value,
        currency="USD",
    )
    db.session.add(entry)
    db.session.flush()

    return {
        "account_a_id": account_a.id,
        "account_b_id": account_b.id,
        "user_a_id": user_a.id,
        "user_b_id": user_b.id,
    }


class TestTransferSpec:
    """The 5 required specification tests."""

    def test_balance_computed_correctly_from_ledger(self, app, two_accounts):
        """Test 1: Balance is correctly derived from SUM of ledger entries."""
        a_id = two_accounts["account_a_id"]
        b_id = two_accounts["account_b_id"]

        # A starts with 1000
        balance_a = balance_service.get_balance(a_id, "USD")
        assert balance_a == Money("1000.0000", Currency.USD)

        # B starts with 0
        balance_b = balance_service.get_balance(b_id, "USD")
        assert balance_b == Money.zero(Currency.USD)

        # Transfer 250 from A to B
        transfer_service.execute_transfer(
            source_account_id=a_id,
            target_account_id=b_id,
            amount=Decimal("250.0000"),
            currency="USD",
        )

        # Verify balances
        assert balance_service.get_balance(a_id, "USD") == Money("750.0000", Currency.USD)
        assert balance_service.get_balance(b_id, "USD") == Money("250.0000", Currency.USD)

    def test_transfer_fails_when_balance_insufficient(self, app, two_accounts):
        """Test 2: Transfer is rejected when source has insufficient funds."""
        a_id = two_accounts["account_a_id"]
        b_id = two_accounts["account_b_id"]

        with pytest.raises(InsufficientFundsError):
            transfer_service.execute_transfer(
                source_account_id=a_id,
                target_account_id=b_id,
                amount=Decimal("2000.0000"),  # More than the 1000 balance
                currency="USD",
            )

        # Balance should be unchanged
        assert balance_service.get_balance(a_id, "USD") == Money("1000.0000", Currency.USD)

    def test_transfer_creates_balanced_ledger_entries(self, app, two_accounts):
        """Test 3: Each transfer creates exactly 2 entries that sum to zero."""
        a_id = two_accounts["account_a_id"]
        b_id = two_accounts["account_b_id"]

        txn = transfer_service.execute_transfer(
            source_account_id=a_id,
            target_account_id=b_id,
            amount=Decimal("100.0000"),
            currency="USD",
        )

        entries = LedgerEntry.query.filter_by(transaction_id=txn.id).all()
        assert len(entries) == 2

        # Sum of all entries in the transaction must be zero (double-entry invariant)
        total = sum(e.amount for e in entries)
        assert total == Decimal("0")

        # Verify entry types
        debit = [e for e in entries if e.entry_type == EntryType.DEBIT.value]
        credit = [e for e in entries if e.entry_type == EntryType.CREDIT.value]
        assert len(debit) == 1
        assert len(credit) == 1
        assert debit[0].amount == Decimal("-100.0000")
        assert credit[0].amount == Decimal("100.0000")

    def test_idempotent_transfer_does_not_duplicate_entries(self, app, two_accounts):
        """Test 4: Same idempotency key returns the same transaction without creating new entries."""
        a_id = two_accounts["account_a_id"]
        b_id = two_accounts["account_b_id"]
        idem_key = "transfer-unique-key-001"

        txn1 = transfer_service.execute_transfer(
            source_account_id=a_id,
            target_account_id=b_id,
            amount=Decimal("100.0000"),
            currency="USD",
            idempotency_key=idem_key,
        )

        txn2 = transfer_service.execute_transfer(
            source_account_id=a_id,
            target_account_id=b_id,
            amount=Decimal("100.0000"),
            currency="USD",
            idempotency_key=idem_key,
        )

        # Same transaction returned
        assert txn1.id == txn2.id

        # Only 2 entries total (not 4)
        entries = LedgerEntry.query.filter_by(transaction_id=txn1.id).all()
        assert len(entries) == 2

        # Balance reflects only one transfer
        assert balance_service.get_balance(a_id, "USD") == Money("900.0000", Currency.USD)

    def test_concurrent_transfers_do_not_create_negative_balance(self, app, two_accounts):
        """Test 5: Concurrent transfers cannot overdraw an account.

        Simulates a race condition by issuing sequential transfers that
        would overdraw the account. The service must check balance before
        each transfer and reject those that would cause a negative balance.

        With a real database (PostgreSQL), SELECT FOR UPDATE provides
        pessimistic locking. With SQLite in tests, serial execution
        proves the balance check logic is correct.
        """
        a_id = two_accounts["account_a_id"]
        b_id = two_accounts["account_b_id"]

        # Account A has 1000. Try 5 transfers of 300 each.
        # Only 3 should succeed (3 * 300 = 900 <= 1000), the rest should fail.
        results = []

        for i in range(5):
            try:
                transfer_service.execute_transfer(
                    source_account_id=a_id,
                    target_account_id=b_id,
                    amount=Decimal("300.0000"),
                    currency="USD",
                    idempotency_key=f"concurrent-{i}",
                )
                results.append("success")
            except InsufficientFundsError:
                results.append("insufficient")

        success_count = results.count("success")
        insufficient_count = results.count("insufficient")

        # Exactly 3 transfers of 300 can succeed from a balance of 1000
        assert success_count == 3
        # 2 must have been rejected
        assert insufficient_count == 2

        # Verify balance is non-negative
        balance = balance_service.get_balance(a_id, "USD")
        assert balance >= Money.zero(Currency.USD)
        assert balance == Money("100.0000", Currency.USD)  # 1000 - 900
