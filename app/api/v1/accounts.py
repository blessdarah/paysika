from flask import current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.api.v1 import v1_bp
from app.extensions import db, limiter
from app.schemas.account import AccountCreate, AccountResponse, BalanceResponse
from app.schemas.transaction import TransactionListResponse, TransactionResponse, LedgerEntryResponse
from app.services import account_service, balance_service, transaction_service
from app.utils.decorators import validate_request


@v1_bp.route("/accounts", methods=["POST"])
@limiter.limit("20 per minute")
@jwt_required()
@validate_request(AccountCreate)
def create_account(validated_data):
    user_id = int(get_jwt_identity())
    account = account_service.create_account(
        user_id=user_id,
        currency=validated_data.currency,
        name=validated_data.name,
    )
    db.session.commit()
    return jsonify(AccountResponse.model_validate(account).model_dump(mode="json")), 201


@v1_bp.route("/accounts", methods=["GET"])
@limiter.limit("30 per minute")
@jwt_required()
def list_accounts():
    user_id = int(get_jwt_identity())
    accounts = account_service.get_user_accounts(user_id)
    return jsonify([
        AccountResponse.model_validate(a).model_dump(mode="json")
        for a in accounts
    ]), 200


@v1_bp.route("/accounts/<int:account_id>/balance", methods=["GET"])
@limiter.limit("60 per minute")
@jwt_required()
def get_balance(account_id):
    user_id = int(get_jwt_identity())
    account = account_service.get_account(account_id)
    if account.user_id != user_id:
        return jsonify({"error": "Forbidden"}), 403

    balance = balance_service.get_balance(account_id, account.currency)
    return jsonify(BalanceResponse(
        account_id=account_id,
        currency=account.currency,
        balance=str(balance.amount),
    ).model_dump()), 200


@v1_bp.route("/accounts/<int:account_id>/transactions", methods=["GET"])
@limiter.limit("30 per minute")
@jwt_required()
def get_account_transactions(account_id):
    user_id = int(get_jwt_identity())
    account = account_service.get_account(account_id)
    if account.user_id != user_id:
        return jsonify({"error": "Forbidden"}), 403

    page = request.args.get("page", 1, type=int)
    per_page = min(
        request.args.get("per_page", current_app.config["ITEMS_PER_PAGE"], type=int),
        current_app.config["MAX_PER_PAGE"],
    )

    result = transaction_service.get_account_transactions(account_id, page, per_page)

    transactions = []
    for txn in result["transactions"]:
        entries = [
            LedgerEntryResponse(
                id=e.id,
                account_id=e.account_id,
                transaction_id=e.transaction_id,
                amount=str(e.amount),
                entry_type=e.entry_type,
                status=e.status,
                currency=e.currency,
                created_at=e.created_at,
            ).model_dump(mode="json")
            for e in txn.entries
        ]
        transactions.append(TransactionResponse(
            id=txn.id,
            type=txn.type,
            status=txn.status,
            description=txn.description,
            correlation_id=txn.correlation_id,
            created_at=txn.created_at,
            entries=entries,
        ).model_dump(mode="json"))

    return jsonify(TransactionListResponse(
        transactions=transactions,
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
        pages=result["pages"],
    ).model_dump(mode="json")), 200
