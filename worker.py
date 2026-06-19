"""RQ worker entrypoint.

Run a worker for specific queues:

    python worker.py                            # all queues
    python worker.py --queue deposits           # deposits only
    python worker.py --queue notifications      # notifications only
    python worker.py --queue balance            # balance snapshots only
"""
import argparse

from app import create_app
from app.services.balance_jobs import init as init_balance_jobs
from app.services.deposit_jobs import init as init_deposit_jobs
from app.services.email_jobs import init as init_email_jobs

app = create_app()
init_email_jobs(app)
init_deposit_jobs(app)
init_balance_jobs(app)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RQ worker")
    parser.add_argument(
        "--queue",
        default="deposits,notifications,balance",
        help="Comma-separated queue names to process",
    )
    args = parser.parse_args()
    queues = [q.strip() for q in args.queue.split(",")]

    with app.app_context():
        from redis import Redis
        from rq.worker import Worker

        redis_url = app.config.get("CACHE_REDIS_URL", "redis://localhost:6379/0")
        conn = Redis.from_url(redis_url)
        worker = Worker(queues, connection=conn)
        worker.work()
