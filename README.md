# Ledger API

Multi-currency ledger with deposits, transfers, balance tracking, and live FX rates.

## Quick Start

```bash
make install      # Create venv and install dependencies
make db-upgrade   # Run database migrations
make run          # Start on http://localhost:5001
```

Or with full Docker services (PostgreSQL, Redis, Mailpit, Mock Provider):

```bash
make dev
```

## API Documentation

Start the server, then open **http://localhost:5001/api/v1/docs** in a browser for the Swagger UI.

The raw OpenAPI spec is at `/api/v1/openapi.yaml`.

## Architecture

### Layered Structure

```
app/api/v1/       → HTTP layer (route definitions, request validation, response serialization)
app/services/     → Business logic (orchestration, no Flask awareness beyond `g`)
app/domain/       → Pure domain primitives (enums, events, Money value object)
app/models/       → SQLAlchemy ORM models (data access)
app/schemas/      → Pydantic request/response schemas (validation + serialization)
app/middleware/    → Cross-cutting: error handlers, correlation IDs, request logging
app/utils/        → Shared utilities (decorators, logging config, exceptions)
```

Dependencies point inward: HTTP → Services → Domain (never the reverse).

### Service Layer

Services are plain Python classes/functions — no Flask request context required. They receive primitives and return domain objects. Transactions are committed by the HTTP layer, never by services (except for idempotency records).

### Event Bus

Domain events (`TransferCompleted`, `DepositFailed`, etc.) are published synchronously after successful operations. The notification service subscribes to events and sends emails asynchronously via RQ.

### Background Jobs

The RQ worker (`python worker.py`) listens on two queues:

| Queue | Jobs |
|---|---|
| `notifications` | Email delivery (TransferCompleted, DepositFailed, etc.) |
| `deposits` | Payment provider notification and orphaned-deposit recovery |

## Domain Model

### Double-Entry Ledger

Every financial operation creates a **Transaction** with at least two **LedgerEntry** rows (one DEBIT, one CREDIT). Entries are never mutated — only appended. Balance is computed as `SUM(amount) WHERE status = 'SUCCESS'`.

| Concept | Representation |
|---|---|
| Transaction | `type` (DEPOSIT/TRANSFER), `status` (PENDING/COMPLETED/FAILED), `correlation_id` |
| LedgerEntry | `entry_type` (DEBIT/CREDIT), `amount`, `status`, `currency`, FK to Transaction |
| Account | `currency`, `user_id`, `is_system` (platform clearing accounts) |
| BalanceSnapshot | Cached `balance` + `entry_count` + `last_entry_id` at a point in time |

### Two-Phase Deposit

1. `POST /api/v1/deposits` → creates PENDING transaction, enqueues RQ job, returns 202
2. RQ worker calls the payment provider's `/create-payment` endpoint asynchronously
3. Provider sends webhook to `POST /api/v1/payments/webhook`
4. `deposit.completed` → `confirm_deposit()` creates ledger entries, marks COMPLETED
5. `deposit.failed` → marks FAILED without entries

Initiator metadata (`account_id`, `amount`, `currency`) is stored in `Transaction.metadata_` JSON so the webhook never trusts external amount/currency values.

The provider notification runs in a background RQ worker, keeping the HTTP request fast and avoiding worker starvation under load. If the provider is unreachable, the job retries automatically (configurable via RQ's `Retry`).

### Orphaned Deposit Recovery

A CLI command scans for PENDING deposits older than a threshold that were never acknowledged by the provider and re-enqueues their notification:

```bash
flask recover-orphan-deposits --delay-minutes 30
```

This can be run as a cron job or scheduled task (e.g., every 15 minutes). Only deposits without a `provider_reference` are considered orphaned — deposits that were successfully notified but not yet webhooked are left alone.

## Performance

### Pessimistic Locking

All money-mutating operations lock accounts with `SELECT ... FOR UPDATE` (sorted by account ID to prevent deadlocks). Ledger entries are additionally locked to prevent phantom reads during balance computation.

### Snapshot-Based Balance

Instead of scanning the full entry table on every request, `BalanceSnapshot` caches the running total. Reads only scan entries inserted *after* the latest snapshot. Snapshots are created automatically when a configurable threshold of new entries is reached.

### Indexing

A composite index on `(account_id, status, id)` covers all balance query WHERE clauses (`account_id = ? AND status = 'SUCCESS' AND id > ?`), avoiding table scans.

### Caching

Balance results are cached (using Redis) with a short TTL. The cache is invalidated on any write to the account.

## Tradeoffs

| Decision | Rationale | Downside |
|---|---|---|
| **Pydantic over Marshmallow** | Type hints, `model_validate`, native FastAPI compatibility | No auto OpenAPI generation (spec is hand-written) |
| **SQLite default, PostgreSQL in prod** | Zero-config for local dev | Behaviour differs under concurrent writes (`FOR UPDATE` is a no-op on SQLite) |
| **Async email via RQ** | Email never blocks the HTTP request | Requires Redis and a running worker |
| **Pessimistic over optimistic locking** | Simple, predictable, no retry loops | Lower throughput under contention; acceptable for a ledger |
| **Two-phase deposit** | Provider owns the payment lifecycle; platform never creates entries without confirmation | More complex state machine; orphaned deposits possible without recovery job |
| **Async provider notification** | HTTP request returns immediately; no worker starvation under load | Adds RQ dependency for deposit flow; webhook race if job completes after manual recovery |
| **RQ over Celery** | Minimal dependencies (just Redis), no message broker config | No scheduled tasks, no result backend |
| **Mock provider** | Self-contained, restart clears state, no third-party deps | Not a real payment provider — swap URL and webhook mapping for production |

## Testing

```bash
pytest                                    # SQLite (default)
TEST_DATABASE_URL=postgresql://... pytest # PostgreSQL
```

The race-condition test (`test_race_without_for_update`) proves `FOR UPDATE` is necessary for correctness. It skips on SQLite (FOR UPDATE is a no-op) and on PostgreSQL (MVCC prevents the race from materialising).

## Configuration

All configuration is env-based (see `.env.example`). Key settings:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///dev.db` | Database connection string |
| `TEST_DATABASE_URL` | `sqlite://` | Test database (set to PostgreSQL for CI) |
| `MAIL_SUPPRESS_SEND` | `1` | Suppress email sending (0 to actually send) |
| `FX_PROVIDER` | `frankfurter` | Exchange rate provider (frankfurter/fallback) |
| `MOCK_PROVIDER_URL` | `http://localhost:8090` | Mock payment provider URL |
| `WEBHOOK_SECRET` | *(empty)* | HMAC secret for webhook verification |
| `WEBHOOK_TIMESTAMP_TOLERANCE` | 300 | Max age (seconds) for webhook timestamps |
