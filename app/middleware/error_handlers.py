from flask import Flask, jsonify

from app.utils.exceptions import APIError


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def handle_api_error(error: APIError):
        app.logger.warning("API error: %s (status=%d)", error.message, error.status_code)
        return jsonify({"error": error.message}), error.status_code

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.exception("Internal server error: %s", error)
        return jsonify({"error": "Internal server error"}), 500
