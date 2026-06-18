import os
import random
import threading
import uuid
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

PORT = int(os.getenv("PORT", "8090"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://host.docker.internal:5001/api/v1/payments/webhook")
DELAY_SECONDS = int(os.getenv("MOCK_DELAY_SECONDS", "3"))
FAILURE_RATE = float(os.getenv("MOCK_FAILURE_RATE", "0"))

payments: dict[str, dict] = {}
_lock = threading.Lock()


def _generate_event_id():
    return "evt_" + uuid.uuid4().hex[:16]


def _generate_provider_reference():
    return "prov_" + uuid.uuid4().hex[:16]


def _callback(payment_id: str) -> None:
    with _lock:
        payment = payments.get(payment_id)
        if payment is None:
            return
        amount = payment["amount"]
        currency = payment["currency"]
        reference_id = payment["reference_id"]

    is_failure = random.random() < FAILURE_RATE

    event_type = "deposit.failed" if is_failure else "deposit.completed"
    status = "failed" if is_failure else "completed"

    payload = {
        "event_id": _generate_event_id(),
        "event_type": event_type,
        "reference_id": reference_id,
        "provider_reference": _generate_provider_reference(),
        "amount": amount,
        "currency": currency,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {},
    }

    try:
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        app.logger.info(
            "Callback for payment=%s event=%s -> %s %s",
            payment_id,
            event_type,
            resp.status_code,
            resp.text[:200],
        )
    except requests.RequestException as e:
        app.logger.error("Callback failed for payment=%s: %s", payment_id, e)

    with _lock:
        if payment.get("status") == "pending":
            payment["status"] = status


@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200


@app.route("/create-payment", methods=["POST"])
def create_payment():
    data = request.get_json(silent=True) or {}
    reference_id = data.get("reference_id")
    amount = data.get("amount")
    currency = data.get("currency")

    if not all([reference_id, amount, currency]):
        return jsonify({"error": "reference_id, amount, and currency are required"}), 400

    payment_id = "mck_" + uuid.uuid4().hex[:12]
    payment = {
        "payment_id": payment_id,
        "reference_id": reference_id,
        "amount": str(amount),
        "currency": currency,
        "status": "pending",
    }

    with _lock:
        payments[payment_id] = payment

    timer = threading.Timer(DELAY_SECONDS, _callback, args=[payment_id])
    timer.daemon = True
    timer.start()

    app.logger.info(
        "Payment created: %s reference=%s %s %s (callback in %ss)",
        payment_id, reference_id, amount, currency, DELAY_SECONDS,
    )

    return jsonify({
        "payment_id": payment_id,
        "status": "pending",
        "reference_id": reference_id,
    }), 201


@app.route("/payments/<payment_id>", methods=["GET"])
def get_payment(payment_id: str):
    with _lock:
        payment = payments.get(payment_id)
    if payment is None:
        return jsonify({"error": "Payment not found"}), 404
    return jsonify(payment), 200


@app.route("/trigger/<payment_id>", methods=["POST"])
def trigger_payment(payment_id: str):
    outcome = request.args.get("outcome", "completed")
    if outcome not in ("completed", "failed"):
        return jsonify({"error": "outcome must be 'completed' or 'failed'"}), 400

    with _lock:
        payment = payments.get(payment_id)
        if payment is None:
            return jsonify({"error": "Payment not found"}), 404
        payment["status"] = outcome

    event_type = "deposit.completed" if outcome == "completed" else "deposit.failed"
    payload = {
        "event_id": _generate_event_id(),
        "event_type": event_type,
        "reference_id": payment["reference_id"],
        "provider_reference": _generate_provider_reference(),
        "amount": payment["amount"],
        "currency": payment["currency"],
        "status": outcome,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {},
    }

    try:
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        app.logger.info(
            "Trigger payment=%s event=%s -> %s %s",
            payment_id, event_type, resp.status_code, resp.text[:200],
        )
    except requests.RequestException as e:
        app.logger.error("Trigger callback failed for payment=%s: %s", payment_id, e)
        return jsonify({"error": str(e)}), 502

    return jsonify(payload), 200


@app.route("/configure", methods=["POST"])
def configure():
    data = request.get_json(silent=True) or {}
    global DELAY_SECONDS, FAILURE_RATE
    if "delay_seconds" in data:
        DELAY_SECONDS = int(data["delay_seconds"])
    if "failure_rate" in data:
        FAILURE_RATE = float(data["failure_rate"])
    app.logger.info("Configured: delay=%ss failure_rate=%.2f", DELAY_SECONDS, FAILURE_RATE)
    return jsonify({"delay_seconds": DELAY_SECONDS, "failure_rate": FAILURE_RATE}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
