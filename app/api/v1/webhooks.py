import hashlib
import hmac

from flask import current_app, jsonify, request

from app.api.v1 import v1_bp
from app.schemas.webhook import PaymentWebhookPayload
from app.utils.decorators import validate_request


def _verify_hmac_signature(payload_bytes: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@v1_bp.route("/payments/webhook", methods=["POST"])
@validate_request(PaymentWebhookPayload)
def payment_webhook(validated_data):
    secret = current_app.config.get("WEBHOOK_SECRET", "")
    signature = request.headers.get("X-Webhook-Signature", "")

    if secret and signature:
        if not _verify_hmac_signature(request.get_data(), signature, secret):
            return jsonify({"error": "Invalid webhook signature"}), 401

    current_app.logger.info(
        "Webhook received: %s for transaction %s status=%s",
        validated_data.event_type,
        validated_data.transaction_id,
        validated_data.status,
    )

    return jsonify({"status": "received"}), 200
