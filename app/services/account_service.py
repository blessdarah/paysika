from app.domain.enums import Currency
from app.extensions import db
from app.models.account import Account
from app.models.user import User
from app.utils.exceptions import AccountNotFoundError, ConflictError, NotFoundError


def create_account(user_id: int, currency: str, name: str = "") -> Account:
    """Create a new account for a user."""
    # Validate currency
    Currency(currency)

    user = db.session.get(User, user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found")

    # Check for duplicate
    existing = Account.query.filter_by(user_id=user_id, currency=currency).first()
    if existing:
        raise ConflictError(f"User already has a {currency} account")

    account = Account(user_id=user_id, currency=currency, name=name)
    db.session.add(account)
    db.session.flush()
    return account


def get_account(account_id: int) -> Account:
    account = db.session.get(Account, account_id)
    if account is None:
        raise AccountNotFoundError(f"Account {account_id} not found")
    return account


def get_user_accounts(user_id: int) -> list[Account]:
    return Account.query.filter_by(user_id=user_id).all()


def get_or_create_platform_clearing_account(currency: str) -> Account:
    """Get or create the system clearing account for deposits/withdrawals."""
    from flask import current_app

    clearing_name = current_app.config.get(
        "PLATFORM_CLEARING_ACCOUNT_NAME", "Platform Clearing"
    )

    # Find or create the __system__ user
    system_user = User.query.filter_by(username="__system__").first()
    if system_user is None:
        system_user = User(username="__system__", email="system@internal")
        system_user.set_password("not-a-real-password-never-authenticates")
        db.session.add(system_user)
        db.session.flush()

    # Find or create the clearing account for this currency
    clearing_account = Account.query.filter_by(
        user_id=system_user.id, currency=currency, is_system=True
    ).first()

    if clearing_account is None:
        clearing_account = Account(
            user_id=system_user.id,
            currency=currency,
            name=clearing_name,
            is_system=True,
        )
        db.session.add(clearing_account)
        db.session.flush()

    return clearing_account
