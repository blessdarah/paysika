from decimal import Decimal

from flask import jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.api.v1 import v1_bp
from app.extensions import db
from app.schemas.transfer import TransferRequest, TransferResponse
from app.services import account_service, transfer_service
from app.utils.decorators import require_idempotency_key, validate_request
from app.utils.exceptions import ForbiddenError


@v1_bp.route("/transfers", methods=["POST"])
@jwt_required()
@require_idempotency_key
@validate_request(TransferRequest)
def create_transfer(validated_data):
    user_id = int(get_jwt_identity())

    # Verify the user owns the source account
    source_account = account_service.get_account(validated_data.source_account_id)
    if source_account.user_id != user_id:
        raise ForbiddenError("You do not own the source account")

    txn = transfer_service.execute_transfer(
        source_account_id=validated_data.source_account_id,
        target_account_id=validated_data.target_account_id,
        amount=Decimal(validated_data.amount),
        currency=validated_data.currency,
        description=validated_data.description,
    )
    db.session.commit()

    return jsonify(TransferResponse(
        transaction_id=txn.id,
        status=txn.status,
        source_account_id=validated_data.source_account_id,
        target_account_id=validated_data.target_account_id,
        amount=validated_data.amount,
        currency=validated_data.currency,
        created_at=txn.created_at,
    ).model_dump(mode="json")), 201
