from flask import Flask

from app.api.v1 import v1_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(v1_bp, url_prefix="/api/v1")
