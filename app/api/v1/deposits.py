from decimal import Decimal

from flask import current_app, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.api.v1 import v1_bp
from app.extensions import db
from app.schemas.deposit import DepositInitiateRequest, DepositInitiateResponse
from app.services import account_service, deposit_service
from app.utils.decorators import require_idempotency_key, validate_request
from app.utils.exceptions import ForbiddenError


def _get_deposit_queue():
    return current_app.extensions["deposit_queue"]


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
    db.session.commit()

    # Notify the payment provider asynchronously — the request returns
    # immediately and the RQ worker posts to the provider outside the
    # HTTP request/response cycle.
    try:
        queue = _get_deposit_queue()
        from app.services.deposit_jobs import notify_provider

        queue.enqueue(
            notify_provider,
            txn.id,
            str(validated_data.amount),
            validated_data.currency,
        )
    except Exception:
        current_app.logger.exception(
            "Failed to enqueue provider notification for transaction=%s", txn.id,
        )

    return (
        jsonify(
            DepositInitiateResponse(
                transaction_id=txn.id,
                status=txn.status,
                account_id=validated_data.account_id,
                amount=validated_data.amount,
                currency=validated_data.currency,
                provider_payment_id="",
            ).model_dump(mode="json")
        ),
        202,
    )
