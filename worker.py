"""RQ worker entrypoint. Run with: python worker.py"""
from app import create_app
from app.services.balance_jobs import init as init_balance_jobs
from app.services.deposit_jobs import init as init_deposit_jobs
from app.services.email_jobs import init as init_email_jobs

app = create_app()
init_email_jobs(app)
init_deposit_jobs(app)
init_balance_jobs(app)

if __name__ == "__main__":
    with app.app_context():
        from rq.worker import Worker
        from redis import Redis

        redis_url = app.config.get("CACHE_REDIS_URL", "redis://localhost:6379/0")
        conn = Redis.from_url(redis_url)
        worker = Worker(["notifications", "deposits"], connection=conn)
        worker.work()
