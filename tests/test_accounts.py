import pytest

from app.extensions import db
from app.models.account import Account
from app.models.user import User
from app.services import account_service
from app.utils.exceptions import ConflictError, NotFoundError


@pytest.fixture()
def user(app):
    u = User(username="accuser", email="acc@test.com")
    u.set_password("password123")
    db.session.add(u)
    db.session.flush()
    return u


class TestCreateAccount:
    def test_create_account(self, app, user):
        account = account_service.create_account(user.id, "USD", "My Checking")
        assert account.currency == "USD"
        assert account.name == "My Checking"
        assert account.user_id == user.id
        assert account.is_system is False

    def test_create_duplicate_raises(self, app, user):
        account_service.create_account(user.id, "USD")
        with pytest.raises(ConflictError, match="already has a USD account"):
            account_service.create_account(user.id, "USD")

    def test_create_different_currencies(self, app, user):
        a1 = account_service.create_account(user.id, "USD")
        a2 = account_service.create_account(user.id, "EUR")
        assert a1.id != a2.id

    def test_create_for_nonexistent_user(self, app):
        with pytest.raises(NotFoundError):
            account_service.create_account(9999, "USD")

    def test_create_invalid_currency(self, app, user):
        with pytest.raises(ValueError):
            account_service.create_account(user.id, "INVALID")


class TestGetAccount:
    def test_get_existing(self, app, user):
        created = account_service.create_account(user.id, "USD")
        found = account_service.get_account(created.id)
        assert found.id == created.id

    def test_get_nonexistent(self, app):
        from app.utils.exceptions import AccountNotFoundError
        with pytest.raises(AccountNotFoundError):
            account_service.get_account(9999)


class TestGetUserAccounts:
    def test_list_accounts(self, app, user):
        account_service.create_account(user.id, "USD")
        account_service.create_account(user.id, "EUR")
        accounts = account_service.get_user_accounts(user.id)
        assert len(accounts) == 2

    def test_empty_list(self, app, user):
        accounts = account_service.get_user_accounts(user.id)
        assert accounts == []


class TestPlatformClearingAccount:
    def test_creates_system_user_and_account(self, app):
        clearing = account_service.get_or_create_platform_clearing_account("USD")
        assert clearing.is_system is True
        assert clearing.currency == "USD"
        assert clearing.user.username == "__system__"

    def test_reuses_existing(self, app):
        a1 = account_service.get_or_create_platform_clearing_account("USD")
        a2 = account_service.get_or_create_platform_clearing_account("USD")
        assert a1.id == a2.id
