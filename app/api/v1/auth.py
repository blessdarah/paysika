from flask import jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.api.v1 import v1_bp
from app.schemas.user import UserLogin, UserRegister, UserResponse, TokenResponse
from app.services import auth_service
from app.utils.decorators import validate_request


@v1_bp.route("/auth/register", methods=["POST"])
@validate_request(UserRegister)
def register(validated_data: UserRegister):
    user = auth_service.register_user(
        username=validated_data.username,
        email=validated_data.email,
        password=validated_data.password,
    )
    return jsonify(UserResponse.model_validate(user).model_dump(mode="json")), 201


@v1_bp.route("/auth/login", methods=["POST"])
@validate_request(UserLogin)
def login(validated_data: UserLogin):
    tokens = auth_service.login_user(
        username=validated_data.username,
        password=validated_data.password,
    )
    return jsonify(TokenResponse(**tokens).model_dump()), 200


@v1_bp.route("/auth/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    tokens = auth_service.refresh_access_token(identity)
    return jsonify({"access_token": tokens["access_token"]}), 200


@v1_bp.route("/auth/me", methods=["GET"])
@jwt_required()
def me():
    user_id = int(get_jwt_identity())
    user = auth_service.get_user_by_id(user_id)
    return jsonify(UserResponse.model_validate(user).model_dump(mode="json")), 200
