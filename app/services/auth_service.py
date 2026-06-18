from flask_jwt_extended import create_access_token, create_refresh_token

from app.extensions import db
from app.models.user import User
from app.utils.exceptions import ConflictError, UnauthorizedError


def register_user(username: str, email: str, password: str) -> User:
    if User.query.filter_by(username=username).first():
        raise ConflictError("Username already taken")
    if User.query.filter_by(email=email).first():
        raise ConflictError("Email already registered")

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def login_user(username: str, password: str) -> dict:
    user = User.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        raise UnauthorizedError("Invalid username or password")

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    return {"access_token": access_token, "refresh_token": refresh_token}


def refresh_access_token(user_id: str) -> dict:
    access_token = create_access_token(identity=user_id)
    return {"access_token": access_token, "refresh_token": ""}


def get_user_by_id(user_id: int) -> User:
    user = db.session.get(User, user_id)
    if user is None:
        raise UnauthorizedError("User not found")
    return user
