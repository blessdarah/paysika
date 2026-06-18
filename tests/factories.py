import factory

from app.extensions import db
from app.models import Account, User


class UserFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session = None  # Set dynamically in conftest
        sqlalchemy_session_persistence = "commit"

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    password_hash = "unused"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", "password123")
        obj = super()._create(model_class, *args, **kwargs)
        obj.set_password(password)
        db.session.commit()
        return obj


class AccountFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Account
        sqlalchemy_session = None
        sqlalchemy_session_persistence = "commit"

    user = factory.SubFactory(UserFactory)
    currency = "USD"
    name = factory.Sequence(lambda n: f"Account {n}")
    is_system = False
