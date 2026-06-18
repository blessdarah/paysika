import hashlib
import json

from app.extensions import db
from app.models.idempotency_record import IdempotencyRecord


def compute_request_hash(data: dict) -> str:
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def get_existing_response(key: str) -> IdempotencyRecord | None:
    return IdempotencyRecord.query.filter_by(key=key).first()


def save_response(key: str, request_hash: str, response_code: int, response_body: dict) -> IdempotencyRecord:
    record = IdempotencyRecord(
        key=key,
        request_hash=request_hash,
        response_code=response_code,
        response_body=response_body,
    )
    db.session.add(record)
    # Committed as part of the outer transaction (atomically with ledger entries)
    return record
