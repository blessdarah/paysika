import uuid

from flask import Flask, g, request


def register_correlation_id(app: Flask) -> None:
    @app.before_request
    def extract_correlation_id():
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = uuid.uuid4().hex
        g.correlation_id = correlation_id

    @app.after_request
    def attach_correlation_id(response):
        correlation_id = getattr(g, "correlation_id", None)
        if correlation_id:
            response.headers["X-Correlation-ID"] = correlation_id
        return response
