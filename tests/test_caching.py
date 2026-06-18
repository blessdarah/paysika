from decimal import Decimal
from unittest.mock import patch

from app.extensions import cache
from app.models.account import Account
from app.models.user import User
from app.services import balance_service, deposit_service, fx_service, idempotency_service


def _create_user(db):
    user = User(username="cacheuser", email="cache@test.com")
    user.set_password("password123")
    db.session.add(user)
    db.session.flush()
    return user


def _create_account(db, user_id, currency="USD", name="Test"):
    account = Account(user_id=user_id, currency=currency, name=name)
    db.session.add(account)
    db.session.flush()
    return account


class TestBalanceCaching:
    def test_balance_cache_hit(self, app, db_session):
        """Second call to get_balance should return cached value."""
        user = _create_user(db_session)
        account = _create_account(db_session, user.id)

        # First call computes from DB and populates cache
        balance1 = balance_service.get_balance(account.id, "USD")
        assert balance1.amount == Decimal("0")

        # Verify cache was populated
        cached = cache.get(f"balance:{account.id}")
        assert cached is not None
        assert cached["amount"] == "0"
        assert cached["currency"] == "USD"

        # Second call should hit cache (we patch the DB query to verify)
        with patch.object(db_session.session, "query", wraps=db_session.session.query) as mock_query:
            balance2 = balance_service.get_balance(account.id, "USD")
            assert balance2.amount == Decimal("0")
            mock_query.assert_not_called()

    def test_use_lock_bypasses_cache(self, app, db_session):
        """get_balance with use_lock=True should always query DB, not cache."""
        user = _create_user(db_session)
        account = _create_account(db_session, user.id)

        # Pre-populate cache with a stale value
        cache.set(f"balance:{account.id}", {"amount": "999.99", "currency": "USD"})

        # use_lock=True should bypass cache and return real DB balance
        balance = balance_service.get_balance(account.id, "USD", use_lock=True)
        assert balance.amount == Decimal("0")

    def test_use_lock_does_not_write_cache(self, app, db_session):
        """get_balance with use_lock=True should not populate cache."""
        user = _create_user(db_session)
        account = _create_account(db_session, user.id)

        balance_service.get_balance(account.id, "USD", use_lock=True)

        cached = cache.get(f"balance:{account.id}")
        assert cached is None

    def test_invalidation_clears_cache(self, app, db_session):
        """invalidate_balance_cache should remove cached balance."""
        user = _create_user(db_session)
        account = _create_account(db_session, user.id)

        # Populate cache
        balance_service.get_balance(account.id, "USD")
        assert cache.get(f"balance:{account.id}") is not None

        # Invalidate
        balance_service.invalidate_balance_cache(account.id)
        assert cache.get(f"balance:{account.id}") is None

    def test_balance_correct_after_deposit_and_invalidation(self, app, db_session):
        """After a deposit (which invalidates cache), balance should reflect new amount."""
        user = _create_user(db_session)
        account = _create_account(db_session, user.id)

        # Cache initial balance
        balance1 = balance_service.get_balance(account.id, "USD")
        assert balance1.amount == Decimal("0")

        # Deposit invalidates cache
        deposit_service.execute_deposit(account.id, Decimal("100"), "USD")

        # Cache was invalidated, so next call recomputes from DB
        balance2 = balance_service.get_balance(account.id, "USD")
        assert balance2.amount == Decimal("100")


class TestFxRateCaching:
    def test_fx_rate_cached(self, app, db_session):
        """FX rate should be cached after first lookup."""
        rate = fx_service.get_exchange_rate("USD", "EUR")
        assert rate == Decimal("0.92")

        cached = cache.get("fx:USD:EUR")
        assert cached == "0.92"

    def test_fx_rate_same_currency_not_cached(self, app, db_session):
        """Same-currency rate (1) should not be cached."""
        rate = fx_service.get_exchange_rate("USD", "USD")
        assert rate == Decimal("1")

        cached = cache.get("fx:USD:USD")
        assert cached is None


class TestIdempotencyCaching:
    def test_idempotency_cached_on_save(self, app, db_session):
        """save_response should write to both DB and cache."""
        idempotency_service.save_response(
            key="test-key-1",
            request_hash="abc123",
            response_code=201,
            response_body={"id": 1},
        )

        cached = cache.get("idempotency:test-key-1")
        assert cached is not None
        assert cached["key"] == "test-key-1"
        assert cached["response_code"] == 201

    def test_idempotency_cache_hit(self, app, db_session):
        """get_existing_response should return from cache on second call."""
        idempotency_service.save_response(
            key="test-key-2",
            request_hash="def456",
            response_code=200,
            response_body={"status": "ok"},
        )

        # Second call should hit cache and return SimpleNamespace
        result = idempotency_service.get_existing_response("test-key-2")
        assert result is not None
        assert result.response_code == 200
        assert result.response_body == {"status": "ok"}

    def test_idempotency_db_miss_returns_none(self, app, db_session):
        """get_existing_response returns None for unknown keys."""
        result = idempotency_service.get_existing_response("nonexistent")
        assert result is None
