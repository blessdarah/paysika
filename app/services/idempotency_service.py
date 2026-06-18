import hashlib
import json
import types

from flask import current_app

from app.extensions import cache, db
from app.models.idempotency_record import IdempotencyRecord


def _idempotency_cache_key(key: str) -> str:
    return f"idempotency:{key}"


def compute_request_hash(data: dict) -> str:
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def get_existing_response(key: str) -> IdempotencyRecord | types.SimpleNamespace | None:
    cached = cache.get(_idempotency_cache_key(key))
    if cached is not None:
        return types.SimpleNamespace(**cached)

    record = IdempotencyRecord.query.filter_by(key=key).first()
    if record is None:
        return None

    ttl = current_app.config.get("IDEMPOTENCY_KEY_TTL_HOURS", 24) * 3600
    cache.set(
        _idempotency_cache_key(key),
        {
            "key": record.key,
            "request_hash": record.request_hash,
            "response_code": record.response_code,
            "response_body": record.response_body,
        },
        timeout=ttl,
    )
    return record


def save_response(key: str, request_hash: str, response_code: int, response_body: dict) -> IdempotencyRecord:
    record = IdempotencyRecord(
        key=key,
        request_hash=request_hash,
        response_code=response_code,
        response_body=response_body,
    )
    db.session.add(record)
    # Committed as part of the outer transaction (atomically with ledger entries)

    ttl = current_app.config.get("IDEMPOTENCY_KEY_TTL_HOURS", 24) * 3600
    cache.set(
        _idempotency_cache_key(key),
        {
            "key": key,
            "request_hash": request_hash,
            "response_code": response_code,
            "response_body": response_body,
        },
        timeout=ttl,
    )

    return record
