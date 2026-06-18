.PHONY: help install install-dev run dev db-init db-migrate db-upgrade db-downgrade \
       test test-cov lint clean docker-up docker-down docker-build docker-logs \
       docker-services shell routes mailhog worker

VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
PIP ?= $(VENV)/bin/pip
FLASK ?= $(VENV)/bin/flask

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

install: ## Install production dependencies
	$(PIP) install -r requirements.txt

install-dev: ## Install dev/test dependencies
	$(PIP) install -r requirements-dev.txt

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

run: ## Run the Flask dev server (Docker-free, uses SQLite + SimpleCache)
	$(FLASK) --app 'app:create_app()' run --debug --port 5001

dev: ## Start Docker services, run migrations, and start Flask dev server
	@test -f .env || cp -n .env.example .env
	$(MAKE) docker-services
	@if ! [ -f migrations/env.py ]; then echo "==> Initializing migrations"; $(MAKE) db-init; fi
	@if ! ls migrations/versions/*.py >/dev/null 2>&1; then echo "==> Generating initial migration"; CACHE_TYPE=RedisCache $(MAKE) db-migrate msg="initial migration"; fi
	@echo "==> Applying migrations"
	CACHE_TYPE=RedisCache $(MAKE) db-upgrade
	CACHE_TYPE=RedisCache MAIL_SUPPRESS_SEND=false EMAIL_BACKGROUND=true \
		$(FLASK) --app 'app:create_app()' run --debug --port 5001

run-gunicorn: ## Run with gunicorn (production-like)
	gunicorn --bind 0.0.0.0:5001 --workers 4 --access-logfile - app:app

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

db-init: ## Initialize Alembic migrations directory
	$(FLASK) --app 'app:create_app()' db init

db-migrate: ## Generate a new migration (usage: make db-migrate msg="add users table")
	$(FLASK) --app 'app:create_app()' db migrate -m "$(msg)"

db-upgrade: ## Apply migrations to the database
	$(FLASK) --app 'app:create_app()' db upgrade

db-downgrade: ## Revert the last migration
	$(FLASK) --app 'app:create_app()' db downgrade

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

test: ## Run tests
	$(PYTHON) -m pytest tests/ -v

test-cov: ## Run tests with coverage report
	$(PYTHON) -m pytest tests/ -v --cov=app --cov-report=term-missing

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

docker-build: ## Build Docker images
	docker compose build

docker-up: ## Start all services (app + db + redis + mailhog) in Docker
	docker compose up -d

docker-down: ## Stop and remove Docker containers
	docker compose down

docker-logs: ## Tail Docker container logs
	docker compose logs -f

docker-services: ## Start infrastructure services (db, redis, mailhog) for local development
	docker compose up -d --wait db redis mailhog

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

shell: ## Open a Flask shell
	$(FLASK) --app 'app:create_app()' shell

mailhog: ## Open the MailHog web UI
	open http://localhost:8025

routes: ## List all registered routes
	$(FLASK) --app 'app:create_app()' routes

worker: ## Start RQ worker for background email processing
	$(PYTHON) worker.py

clean: ## Remove caches and compiled files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov
