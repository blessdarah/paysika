import pytest

from app import create_app
from app.extensions import db as _db
from app.services import event_bus


@pytest.fixture(scope="session")
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture(autouse=True)
def db_session(app):
    """Roll back after each test to keep a clean state."""
    with app.app_context():
        _db.session.begin_nested()
        yield _db
        _db.session.rollback()
        _db.session.remove()


@pytest.fixture(autouse=True)
def reset_event_bus():
    """Clear event bus handlers between tests."""
    event_bus.clear_handlers()
    yield
    event_bus.clear_handlers()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_headers(client):
    """Register a user and return auth headers."""
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "password123"},
    )
    token = resp.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _register_and_login(client, username, email):
    """Helper to register and login a user, returning auth headers and user_id."""
    client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": email,
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "password123"},
    )
    data = resp.get_json()
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.fixture()
def user_with_account(client, auth_headers):
    """Register a user, create a USD account, return headers + account_id."""
    resp = client.post(
        "/api/v1/accounts",
        json={"currency": "USD", "name": "Main Account"},
        headers=auth_headers,
    )
    account_data = resp.get_json()
    return {
        "headers": auth_headers,
        "account_id": account_data["id"],
        "user_id": account_data["user_id"],
    }


@pytest.fixture()
def second_user_with_account(client):
    """Register a second user with a USD account."""
    headers = _register_and_login(client, "seconduser", "second@example.com")
    resp = client.post(
        "/api/v1/accounts",
        json={"currency": "USD", "name": "Second Account"},
        headers=headers,
    )
    account_data = resp.get_json()
    return {
        "headers": headers,
        "account_id": account_data["id"],
        "user_id": account_data["user_id"],
    }
