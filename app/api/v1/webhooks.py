import hashlib
import hmac
from datetime import datetime, timezone

from flask import current_app, jsonify, request

from app.api.v1 import v1_bp
from app.extensions import limiter
from app.schemas.webhook import PaymentWebhookPayload
from app.utils.decorators import validate_request


def _verify_hmac_signature(payload_bytes: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@v1_bp.route("/payments/webhook", methods=["POST"])
@limiter.limit("30 per minute")
@validate_request(PaymentWebhookPayload)
def payment_webhook(validated_data):
    secret = current_app.config.get("WEBHOOK_SECRET", "")

    if not secret:
        current_app.logger.warning(
            "WEBHOOK_SECRET is not configured — webhook accepted without signature verification"
        )
    else:
        signature = request.headers.get("X-Webhook-Signature", "")
        if not signature:
            return jsonify({"error": "Missing X-Webhook-Signature header"}), 401
        if not _verify_hmac_signature(request.get_data(), signature, secret):
            return jsonify({"error": "Invalid webhook signature"}), 401

    # Replay protection: reject stale timestamps
    tolerance = current_app.config.get("WEBHOOK_TIMESTAMP_TOLERANCE", 300)
    try:
        ts = datetime.fromisoformat(validated_data.timestamp)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = abs((datetime.now(timezone.utc) - ts).total_seconds())
        if delta > tolerance:
            return jsonify({"error": "Webhook timestamp too old"}), 401
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid timestamp format"}), 400

    current_app.logger.info(
        "Webhook received: %s for transaction %s status=%s",
        validated_data.event_type,
        validated_data.transaction_id,
        validated_data.status,
    )

    return jsonify({"status": "received"}), 200
