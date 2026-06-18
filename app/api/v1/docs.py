import os

from flask import jsonify, send_from_directory


def register_docs_routes(app):
    """Register documentation routes on the Flask app."""

    @app.route("/api/v1/openapi.yaml")
    def serve_openapi_spec():
        static_dir = os.path.join(app.root_path, "static")
        return send_from_directory(static_dir, "openapi.yaml")

    @app.route("/api/v1/docs")
    def swagger_ui():
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Ledger API — Swagger UI</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
  <style>
    html { box-sizing: border-box; }
    *, *::before, *::after { box-sizing: inherit; }
    body { margin: 0; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({
      url: "/api/v1/openapi.yaml",
      dom_id: "#swagger-ui",
    });
  </script>
</body>
</html>
        """
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}
