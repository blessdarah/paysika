from functools import wraps

from flask import jsonify, request
from pydantic import ValidationError as PydanticValidationError

from app.utils.exceptions import ValidationError


def validate_request(schema_cls):
    """Validate request JSON body against a Pydantic schema."""

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            json_data = request.get_json(silent=True)
            if json_data is None:
                raise ValidationError("Request body must be valid JSON")
            try:
                validated = schema_cls.model_validate(json_data)
            except PydanticValidationError as e:
                errors = e.errors()
                messages = []
                for err in errors:
                    loc = ".".join(str(l) for l in err["loc"])
                    messages.append(f"{loc}: {err['msg']}")
                raise ValidationError("; ".join(messages))
            kwargs["validated_data"] = validated
            return f(*args, **kwargs)

        return wrapper

    return decorator


def require_idempotency_key(f):
    """Decorator that enforces Idempotency-Key header and caches responses."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        from app.services import idempotency_service

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return jsonify({"error": "Idempotency-Key header is required"}), 400

        request_data = request.get_json(silent=True) or {}
        request_hash = idempotency_service.compute_request_hash(request_data)

        existing = idempotency_service.get_existing_response(idempotency_key)
        if existing:
            if existing.request_hash != request_hash:
                return jsonify({"error": "Idempotency-Key reused with different request body"}), 422
            return jsonify(existing.response_body), existing.response_code

        # Execute the actual handler
        response = f(*args, **kwargs)

        # Extract response data for caching
        if isinstance(response, tuple):
            response_obj, status_code = response
        else:
            response_obj = response
            status_code = 200

        response_body = response_obj.get_json()
        idempotency_service.save_response(idempotency_key, request_hash, status_code, response_body)

        return response

    return wrapper
