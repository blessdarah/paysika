import time

from flask import Flask, g, request


def register_request_logging(app: Flask) -> None:
    @app.before_request
    def start_timer():
        g.start_time = time.time()

    @app.after_request
    def log_request(response):
        duration = time.time() - g.get("start_time", time.time())
        correlation_id = getattr(g, "correlation_id", "-")
        app.logger.info(
            "[%s] %s %s %s %.3fs",
            correlation_id,
            request.method,
            request.path,
            response.status_code,
            duration,
        )
        return response
