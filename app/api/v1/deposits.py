import os
from decimal import Decimal

import requests
from flask import current_app, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.api.v1 import v1_bp
from app.extensions import db
from app.schemas.deposit import DepositInitiateRequest, DepositInitiateResponse
from app.services import account_service, deposit_service
from app.utils.decorators import require_idempotency_key, validate_request
from app.utils.exceptions import ForbiddenError


@v1_bp.route("/deposits", methods=["POST"])
@jwt_required()
@require_idempotency_key
@validate_request(DepositInitiateRequest)
def create_deposit(validated_data):
    user_id = int(get_jwt_identity())

    account = account_service.get_account(validated_data.account_id)
    if account.user_id != user_id:
        raise ForbiddenError("You do not own this account")

    txn = deposit_service.initiate_deposit(
        account_id=validated_data.account_id,
        amount=Decimal(validated_data.amount),
        currency=validated_data.currency,
        description=validated_data.description,
        provider="mock",
    )
    db.session.flush()

    provider_payment_url = ""
    try:
        provider_url = current_app.config.get(
            "MOCK_PROVIDER_URL",
            os.getenv("MOCK_PROVIDER_URL", "http://localhost:8090"),
        )
        resp = requests.post(
            f"{provider_url}/create-payment",
            json={
                "reference_id": str(txn.id),
                "amount": str(validated_data.amount),
                "currency": validated_data.currency,
            },
            timeout=5,
        )
        if resp.ok:
            provider_data = resp.json()
            provider_payment_url = provider_data.get("payment_id", "")
            current_app.logger.info(
                "Mock provider initiated: transaction=%s payment=%s",
                txn.id, provider_payment_url,
            )
        else:
            current_app.logger.warning(
                "Mock provider returned %s: %s", resp.status_code, resp.text,
            )
    except requests.RequestException as e:
        current_app.logger.warning("Mock provider unreachable: %s", e)

    db.session.commit()

    return (
        jsonify(
            DepositInitiateResponse(
                transaction_id=txn.id,
                status=txn.status,
                account_id=validated_data.account_id,
                amount=validated_data.amount,
                currency=validated_data.currency,
                provider_payment_id=provider_payment_url,
            ).model_dump(mode="json")
        ),
        202,
    )
