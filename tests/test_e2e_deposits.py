from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from app.domain.enums import Currency, TransactionStatus
from app.domain.money import Money
from app.extensions import db
from app.models.account import Account
from app.models.ledger_entry import LedgerEntry
from app.models.transaction import Transaction
from app.models.user import User
from app.services import account_service, balance_service, deposit_service
from app.utils.exceptions import InvalidTransactionStateError


@pytest.fixture()
def user_account(app):
    """Create a user with a USD account."""
    user = User(username="e2edeposit", email="e2edeposit@test.com")
    user.set_password("password123")
    db.session.add(user)
    db.session.flush()
    account = account_service.create_account(user.id, "USD", "E2E Deposit Test")
    return {"user_id": user.id, "account_id": account.id}


class TestInitiateDeposit:
    def test_initiate_creates_pending_transaction(self, app, user_account):
        txn = deposit_service.initiate_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("250.0000"),
            currency="USD",
            provider="mock",
        )

        assert txn.type == "DEPOSIT"
        assert txn.status == TransactionStatus.PENDING.value
        assert txn.provider == "mock"
        assert txn.metadata_ is not None
        assert txn.metadata_["account_id"] == user_account["account_id"]
        assert txn.metadata_["amount"] == "250.0000"
        assert txn.metadata_["currency"] == "USD"

        # No ledger entries yet — money not moved
        entries = LedgerEntry.query.filter_by(transaction_id=txn.id).all()
        assert len(entries) == 0

    def test_initiate_rejects_negative_amount(self, app, user_account):
        from app.utils.exceptions import CurrencyMismatchError

        with pytest.raises(CurrencyMismatchError):
            deposit_service.initiate_deposit(
                account_id=user_account["account_id"],
                amount=Decimal("-50"),
                currency="USD",
            )

    def test_initiate_rejects_currency_mismatch(self, app, user_account):
        from app.utils.exceptions import CurrencyMismatchError

        with pytest.raises(CurrencyMismatchError):
            deposit_service.initiate_deposit(
                account_id=user_account["account_id"],
                amount=Decimal("100"),
                currency="EUR",
            )

    def test_initiate_idempotent(self, app, user_account):
        key = "initiate-idem-001"
        txn1 = deposit_service.initiate_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("100.0000"),
            currency="USD",
            idempotency_key=key,
        )
        txn2 = deposit_service.initiate_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("100.0000"),
            currency="USD",
            idempotency_key=key,
        )
        assert txn1.id == txn2.id
        assert txn1.status == TransactionStatus.PENDING.value

    # Association proxy loading for `entries` triggers a flush on query
    # inside a nested transaction; clear the session first to avoid
    # stale-object warnings.
    def test_initiate_has_no_ledger_entries(self, app, user_account):
        txn = deposit_service.initiate_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("250.0000"),
            currency="USD",
        )
        db.session.flush()
        db.session.expire_all()

        entries = LedgerEntry.query.filter_by(transaction_id=txn.id).all()
        assert len(entries) == 0


class TestConfirmDeposit:
    def test_confirm_creates_balanced_entries(self, app, user_account):
        txn = deposit_service.initiate_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("250.0000"),
            currency="USD",
        )
        db.session.flush()

        confirmed = deposit_service.confirm_deposit(
            transaction_id=txn.id,
            provider_reference="prov_e2e_test",
        )
        db.session.flush()

        assert confirmed.status == TransactionStatus.COMPLETED.value
        assert confirmed.provider_reference == "prov_e2e_test"

        entries = LedgerEntry.query.filter_by(transaction_id=txn.id).all()
        assert len(entries) == 2

        # Double-entry invariant: sum of entries is zero
        total = sum(e.amount for e in entries)
        assert total == Decimal("0")

        # One DEBIT (clearing), one CREDIT (user)
        entry_types = {e.entry_type for e in entries}
        assert entry_types == {"DEBIT", "CREDIT"}

    def test_confirm_increases_balance(self, app, user_account):
        txn = deposit_service.initiate_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("250.0000"),
            currency="USD",
        )
        db.session.flush()

        deposit_service.confirm_deposit(
            transaction_id=txn.id,
            provider_reference="prov_bal_test",
        )
        db.session.flush()

        balance = balance_service.get_balance(
            user_account["account_id"], "USD"
        )
        assert balance == Money("250.0000", Currency.USD)

    def test_confirm_raises_on_non_pending(self, app, user_account):
        # Complete immediately via execute_deposit
        txn = deposit_service.execute_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("100.0000"),
            currency="USD",
        )
        db.session.flush()

        with pytest.raises(InvalidTransactionStateError):
            deposit_service.confirm_deposit(
                transaction_id=txn.id,
                provider_reference="prov_fail",
            )

    def test_confirm_raises_on_nonexistent_transaction(self, app):
        with pytest.raises(InvalidTransactionStateError):
            deposit_service.confirm_deposit(
                transaction_id=99999,
                provider_reference="prov_missing",
            )

    def test_confirm_raises_on_missing_metadata(self, app, user_account):
        txn = deposit_service.initiate_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("50.0000"),
            currency="USD",
        )
        db.session.flush()

        # Wipe metadata to simulate corruption
        txn.metadata_ = None
        db.session.flush()

        with pytest.raises(InvalidTransactionStateError):
            deposit_service.confirm_deposit(
                transaction_id=txn.id,
                provider_reference="prov_bad_meta",
            )


class TestFailDeposit:
    def test_fail_marks_as_failed(self, app, user_account):
        txn = deposit_service.initiate_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("100.0000"),
            currency="USD",
        )
        db.session.flush()

        failed = deposit_service.fail_deposit(
            transaction_id=txn.id,
            reason="Card declined",
        )
        db.session.flush()

        assert failed.status == TransactionStatus.FAILED.value

        # No ledger entries created
        entries = LedgerEntry.query.filter_by(transaction_id=txn.id).all()
        assert len(entries) == 0

    def test_fail_raises_on_non_pending(self, app, user_account):
        txn = deposit_service.execute_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("50.0000"),
            currency="USD",
        )
        db.session.flush()

        with pytest.raises(InvalidTransactionStateError):
            deposit_service.fail_deposit(
                transaction_id=txn.id,
                reason="Already completed",
            )


def _now():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture()
def e2e_env(app, client):
    """Create a fresh user + USD account for each E2E test."""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": f"e2euser_{suffix}",
            "email": f"e2e_{suffix}@test.com",
            "password": "password123",
        },
    )
    assert resp.status_code == 201
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": f"e2euser_{suffix}", "password": "password123"},
    )
    token = resp.get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/api/v1/accounts",
        json={"currency": "USD", "name": "E2E Account"},
        headers=headers,
    )
    assert resp.status_code == 201
    account_id = resp.get_json()["id"]
    return {"headers": headers, "account_id": account_id}


class TestE2EWebhookFlow:
    """Full end-to-end: HTTP initiate → webhook confirm → balance check."""

    def test_e2e_deposit_flow(self, app, client, e2e_env):
        acct = e2e_env

        # 1. Initiate deposit
        resp = client.post(
            "/api/v1/deposits",
            json={
                "account_id": acct["account_id"],
                "amount": "500.00",
                "currency": "USD",
            },
            headers={**acct["headers"], "Idempotency-Key": "e2e-flow-001"},
        )
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["status"] == "PENDING"
        txn_id = data["transaction_id"]

        # 2. Confirm via webhook
        webhook_payload = {
            "event_id": "evt_e2e_test",
            "event_type": "deposit.completed",
            "reference_id": str(txn_id),
            "provider_reference": "prov_e2e_webhook",
            "amount": "500.00",
            "currency": "USD",
            "status": "completed",
            "timestamp": _now(),
            "metadata": {},
        }
        resp = client.post(
            "/api/v1/payments/webhook",
            json=webhook_payload,
        )
        assert resp.status_code == 200

        # 3. Verify balance
        resp = client.get(
            f"/api/v1/accounts/{acct['account_id']}/balance",
            headers=acct["headers"],
        )
        assert resp.status_code == 200
        balance_data = resp.get_json()
        assert balance_data["balance"] == "500.0000"
        assert balance_data["currency"] == "USD"

    def test_e2e_deposit_flow_via_actual_service(self, app, user_account):
        """Same flow as above but through the service layer directly."""
        account_id = user_account["account_id"]

        txn = deposit_service.initiate_deposit(
            account_id=account_id,
            amount=Decimal("300.0000"),
            currency="USD",
        )
        db.session.flush()
        assert txn.status == "PENDING"

        confirmed = deposit_service.confirm_deposit(
            transaction_id=txn.id,
            provider_reference="prov_svc_test",
        )
        db.session.flush()
        assert confirmed.status == "COMPLETED"

        balance = balance_service.get_balance(account_id, "USD")
        assert balance == Money("300.0000", Currency.USD)

    def test_e2e_deposit_fail_flow(self, app, client, e2e_env):
        acct = e2e_env

        resp = client.post(
            "/api/v1/deposits",
            json={
                "account_id": acct["account_id"],
                "amount": "200.00",
                "currency": "USD",
            },
            headers={**acct["headers"], "Idempotency-Key": "e2e-fail-001"},
        )
        assert resp.status_code == 202
        txn_id = resp.get_json()["transaction_id"]

        webhook_payload = {
            "event_id": "evt_e2e_fail",
            "event_type": "deposit.failed",
            "reference_id": str(txn_id),
            "provider_reference": "prov_fail_webhook",
            "amount": "200.00",
            "currency": "USD",
            "status": "failed",
            "timestamp": _now(),
            "metadata": {"reason": "Insufficient funds at provider"},
        }
        resp = client.post(
            "/api/v1/payments/webhook",
            json=webhook_payload,
        )
        assert resp.status_code == 200

        resp = client.get(
            f"/api/v1/accounts/{acct['account_id']}/balance",
            headers=acct["headers"],
        )
        data = resp.get_json()
        assert data["balance"] == "0"

    def test_unknown_event_type(self, app, client):
        payload = {
            "event_id": "evt_unknown",
            "event_type": "deposit.refunded",
            "reference_id": "1",
            "provider_reference": "prov_ref",
            "amount": "100.00",
            "currency": "USD",
            "status": "completed",
            "timestamp": _now(),
            "metadata": {},
        }
        resp = client.post("/api/v1/payments/webhook", json=payload)
        assert resp.status_code == 400
        assert "Unknown" in resp.get_json()["error"]

    def test_stale_timestamp_rejected(self, app, client):
        payload = {
            "event_id": "evt_stale",
            "event_type": "deposit.completed",
            "reference_id": "1",
            "provider_reference": "prov_stale",
            "amount": "100.00",
            "currency": "USD",
            "status": "completed",
            "timestamp": "2020-01-01T00:00:00+00:00",
            "metadata": {},
        }
        resp = client.post("/api/v1/payments/webhook", json=payload)
        assert resp.status_code == 401
        assert "timestamp too old" in resp.get_json()["error"]

    def test_invalid_reference_id(self, app, client):
        payload = {
            "event_id": "evt_bad_ref",
            "event_type": "deposit.completed",
            "reference_id": "not-an-int",
            "provider_reference": "prov_bad",
            "amount": "100.00",
            "currency": "USD",
            "status": "completed",
            "timestamp": _now(),
            "metadata": {},
        }
        resp = client.post("/api/v1/payments/webhook", json=payload)
        assert resp.status_code == 400
        assert "reference_id" in resp.get_json()["error"]


class TestDoubleConfirmFails:
    def test_double_confirm_returns_422(self, app, user_account):
        txn = deposit_service.initiate_deposit(
            account_id=user_account["account_id"],
            amount=Decimal("100.0000"),
            currency="USD",
        )
        db.session.flush()

        deposit_service.confirm_deposit(
            transaction_id=txn.id,
            provider_reference="prov_first",
        )
        db.session.commit()

        with pytest.raises(InvalidTransactionStateError):
            deposit_service.confirm_deposit(
                transaction_id=txn.id,
                provider_reference="prov_second",
            )
