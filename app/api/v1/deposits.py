from decimal import Decimal

from flask import jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.api.v1 import v1_bp
from app.extensions import db
from app.schemas.deposit import DepositRequest, DepositResponse
from app.services import account_service, deposit_service
from app.utils.decorators import require_idempotency_key, validate_request
from app.utils.exceptions import ForbiddenError


@v1_bp.route("/deposits", methods=["POST"])
@jwt_required()
@require_idempotency_key
@validate_request(DepositRequest)
def create_deposit(validated_data):
    user_id = int(get_jwt_identity())

    # Verify the user owns the target account
    account = account_service.get_account(validated_data.account_id)
    if account.user_id != user_id:
        raise ForbiddenError("You do not own this account")

    txn = deposit_service.execute_deposit(
        account_id=validated_data.account_id,
        amount=Decimal(validated_data.amount),
        currency=validated_data.currency,
        description=validated_data.description,
    )
    db.session.commit()

    return (
        jsonify(
            DepositResponse(
                transaction_id=txn.id,
                status=txn.status,
                account_id=validated_data.account_id,
                amount=validated_data.amount,
                currency=validated_data.currency,
                created_at=txn.created_at,
            ).model_dump(mode="json")
        ),
        201,
    )
