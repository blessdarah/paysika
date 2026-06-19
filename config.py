import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-and-make-it-at-least-32-bytes")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "20")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
        "pool_pre_ping": os.getenv("DB_POOL_PRE_PING", "true").lower() == "true",
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "300")),
        "connect_args": {"options": "-c statement_timeout=30000"},
    }
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(1 * 1024 * 1024)))
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-change-me-to-32-bytes-too-mkay")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "15"))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES_DAYS", "30"))
    )
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    ITEMS_PER_PAGE = int(os.getenv("ITEMS_PER_PAGE", "20"))
    MAX_PER_PAGE = int(os.getenv("MAX_PER_PAGE", "100"))

    # Ledger configuration
    LEDGER_SNAPSHOT_THRESHOLD = int(os.getenv("LEDGER_SNAPSHOT_THRESHOLD", "100"))
    IDEMPOTENCY_KEY_TTL_HOURS = int(os.getenv("IDEMPOTENCY_KEY_TTL_HOURS", "24"))
    PLATFORM_CLEARING_ACCOUNT_NAME = os.getenv(
        "PLATFORM_CLEARING_ACCOUNT_NAME", "Platform Clearing"
    )
    SUPPORTED_CURRENCIES = os.getenv("SUPPORTED_CURRENCIES", "USD,EUR,GBP,NGN,XAF").split(",")
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
    WEBHOOK_TIMESTAMP_TOLERANCE = int(os.getenv("WEBHOOK_TIMESTAMP_TOLERANCE", "300"))

    # Mock provider configuration
    MOCK_PROVIDER_URL = os.getenv("MOCK_PROVIDER_URL", "http://localhost:8090")

    # Mail configuration
    MAIL_SERVER = os.getenv("MAIL_SERVER", "localhost")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "1025"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "false").lower() == "true"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "noreply@ledger.local")

    # FX provider configuration
    FX_PROVIDER = os.getenv("FX_PROVIDER", "frankfurter")

    # Async email configuration
    EMAIL_RETRY_MAX = int(os.getenv("EMAIL_RETRY_MAX", "3"))
    EMAIL_RETRY_INTERVALS = os.getenv("EMAIL_RETRY_INTERVALS", "60,300,3600")

    # Rate limiting configuration
    RATELIMIT_STORAGE_URL = os.getenv("RATELIMIT_STORAGE_URL", "memory://")
    RATELIMIT_STRATEGY = os.getenv("RATELIMIT_STRATEGY", "fixed-window")
    RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "200 per day; 50 per hour")
    RATELIMIT_HEADERS_ENABLED = True

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
    SQLALCHEMY_ENGINE_OPTIONS = {}  # SQLite does not support pool options
    CACHE_TYPE = os.getenv("CACHE_TYPE", "SimpleCache")
    MAIL_SUPPRESS_SEND = os.getenv("MAIL_SUPPRESS_SEND", "true").lower() == "true"


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite://")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=60)
    CACHE_TYPE = "SimpleCache"
    MAIL_SUPPRESS_SEND = True
    FX_PROVIDER = "fallback"
    RATELIMIT_ENABLED = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    RATELIMIT_STORAGE_URL = os.getenv(
        "RATELIMIT_STORAGE_URL",
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    )

    @classmethod
    def init_app(cls):
        assert cls.SQLALCHEMY_DATABASE_URI, "DATABASE_URL must be set"
        assert cls.SECRET_KEY != "change-me-in-production-and-make-it-at-least-32-bytes", "SECRET_KEY must be changed from the default"
        assert cls.JWT_SECRET_KEY != "jwt-change-me-to-32-bytes-too-mkay", "JWT_SECRET_KEY must be changed from the default"
        assert cls.WEBHOOK_SECRET, "WEBHOOK_SECRET must be set"


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
