from flask import Flask, jsonify

from app.api import register_blueprints
from app.extensions import cache, cors, db, jwt, mail, migrate
from app.middleware.correlation_id import register_correlation_id
from app.middleware.error_handlers import register_error_handlers
from app.middleware.request_logging import register_request_logging
from app.utils.logging_config import setup_logging
from config import config


def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app)
    cache.init_app(app)
    mail.init_app(app)

    # JWT error handlers
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({"error": "Token has expired"}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({"error": "Invalid token"}), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({"error": "Authorization token required"}), 401

    # Setup logging, error handlers, request logging, correlation IDs
    setup_logging(app)
    register_error_handlers(app)
    register_correlation_id(app)
    register_request_logging(app)

    # Register blueprints
    register_blueprints(app)

    # Import models so Alembic detects them
    from app.models import (  # noqa: F401
        User,
        Account,
        Transaction,
        LedgerEntry,
        BalanceSnapshot,
        IdempotencyRecord,
    )

    @app.route("/health")
    def health():
        return jsonify({"status": "healthy"}), 200

    # Register event handlers
    from app.services.notification_service import register_handlers

    register_handlers()

    return app
