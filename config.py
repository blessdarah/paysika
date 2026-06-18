import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    ITEMS_PER_PAGE = 20

    # Ledger configuration
    LEDGER_SNAPSHOT_THRESHOLD = int(os.getenv("LEDGER_SNAPSHOT_THRESHOLD", "100"))
    IDEMPOTENCY_KEY_TTL_HOURS = int(os.getenv("IDEMPOTENCY_KEY_TTL_HOURS", "24"))
    PLATFORM_CLEARING_ACCOUNT_NAME = os.getenv(
        "PLATFORM_CLEARING_ACCOUNT_NAME", "Platform Clearing"
    )
    SUPPORTED_CURRENCIES = ["USD", "EUR", "GBP", "NGN", "XAF"]
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

    # Cache configuration
    CACHE_TYPE = "RedisCache"
    CACHE_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CACHE_KEY_PREFIX = "ledger:"
    BALANCE_CACHE_TTL = int(os.getenv("BALANCE_CACHE_TTL", "300"))
    FX_RATE_CACHE_TTL = int(os.getenv("FX_RATE_CACHE_TTL", "3600"))


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///dev.db"
    )


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=60)
    CACHE_TYPE = "SimpleCache"


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")

    @classmethod
    def init_app(cls):
        assert cls.SQLALCHEMY_DATABASE_URI, "DATABASE_URL must be set"
        assert cls.SECRET_KEY != "change-me-in-production", "SECRET_KEY must be changed"


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
