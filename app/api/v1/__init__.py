from flask import Blueprint

v1_bp = Blueprint("v1", __name__)

from app.api.v1 import accounts, auth, deposits, transfers, webhooks  # noqa: E402, F401
