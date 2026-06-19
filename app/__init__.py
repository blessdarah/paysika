from datetime import datetime, timedelta, timezone

import click
from flask import Flask, jsonify

from app.api import register_blueprints
from app.extensions import cache, cors, db, jwt, limiter, mail, migrate
from app.middleware.correlation_id import register_correlation_id
from app.middleware.error_handlers import register_error_handlers
from app.middleware.request_logging import register_request_logging
from app.utils.logging_config import setup_logging
from config import config


def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__)
    config_cls = config[config_name]
    app.config.from_object(config_cls)

    # Run config-level initialization (e.g., production assertion checks)
    if hasattr(config_cls, "init_app"):
        config_cls.init_app()

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app)
    cache.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)

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

    # Rate limit error handler
    @app.errorhandler(429)
    def ratelimit_handler(error):
        return jsonify({"error": "Rate limit exceeded. Try again later."}), 429

    # Setup logging, error handlers, request logging, correlation IDs
    setup_logging(app)
    register_error_handlers(app)
    register_correlation_id(app)
    register_request_logging(app)

    # Register blueprints
    register_blueprints(app)

    # Register documentation routes
    from app.api.v1.docs import register_docs_routes

    register_docs_routes(app)

    # Import models so Alembic detects them
    from app.models import (  # noqa: F401
        Account,
        BalanceSnapshot,
        IdempotencyRecord,
        LedgerEntry,
        Transaction,
        User,
    )

    @app.route("/health")
    def health():
        return jsonify({"status": "healthy"}), 200

    # Register event handlers
    from app.services.notification_service import register_handlers

    register_handlers()

    @app.cli.command("cleanup-idempotency")
    @click.option("--hours", default=72, help="Delete records older than N hours")
    def cleanup_idempotency(hours):
        """Delete old IdempotencyRecord rows."""

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        deleted = IdempotencyRecord.query.filter(
            IdempotencyRecord.created_at < cutoff
        ).delete()
        db.session.commit()
        click.echo(f"Deleted {deleted} idempotency records older than {hours} hours")

    @app.cli.command("recover-orphan-deposits")
    @click.option(
        "--delay-minutes", default=30, show_default=True,
        help="Age threshold (minutes) to consider a PENDING deposit orphaned",
    )
    def recover_orphan_deposits(delay_minutes):
        """Re-enqueue provider notification for PENDING deposits that were
        never acknowledged by the payment provider."""
        from app.services.deposit_jobs import init as init_deposit_jobs
        from app.services.deposit_jobs import recover_orphan_deposits as _recover

        init_deposit_jobs(app)
        count = _recover(delay_minutes=delay_minutes)
        click.echo(f"Re-enqueued {count} orphaned deposit(s)")

    return app
