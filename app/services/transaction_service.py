from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.ledger_entry import LedgerEntry
from app.models.transaction import Transaction
from app.utils.exceptions import NotFoundError


def get_transaction(transaction_id: int) -> Transaction:
    txn = db.session.get(Transaction, transaction_id)
    if txn is None:
        raise NotFoundError(f"Transaction {transaction_id} not found")
    return txn


def get_account_transactions(
    account_id: int, page: int = 1, per_page: int = 20
) -> dict:
    """Get paginated transactions for an account."""
    # Find all transaction IDs that have entries for this account
    subq = (
        db.session.query(LedgerEntry.transaction_id)
        .filter(LedgerEntry.account_id == account_id)
        .distinct()
        .subquery()
    )

    query = (
        Transaction.query
        .filter(Transaction.id.in_(db.select(subq.c.transaction_id)))
        .options(joinedload(Transaction.entries))
        .order_by(Transaction.created_at.desc())
    )

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return {
        "transactions": pagination.items,
        "total": pagination.total,
        "page": page,
        "per_page": per_page,
        "pages": pagination.pages,
    }
