.PHONY: help install install-dev run db-init db-migrate db-upgrade db-downgrade \
       test test-cov lint clean docker-up docker-down docker-build docker-logs \
       shell routes

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

install: ## Install production dependencies
	pip install -r requirements.txt

install-dev: ## Install dev/test dependencies
	pip install -r requirements-dev.txt

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

run: ## Run the Flask dev server
	flask --app app:app run --debug

run-gunicorn: ## Run with gunicorn (production-like)
	gunicorn --bind 0.0.0.0:5000 --workers 4 --access-logfile - app:app

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

db-init: ## Initialize Alembic migrations directory
	flask --app app:app db init

db-migrate: ## Generate a new migration (usage: make db-migrate msg="add users table")
	flask --app app:app db migrate -m "$(msg)"

db-upgrade: ## Apply migrations to the database
	flask --app app:app db upgrade

db-downgrade: ## Revert the last migration
	flask --app app:app db downgrade

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

test: ## Run tests
	python -m pytest tests/ -v

test-cov: ## Run tests with coverage report
	python -m pytest tests/ -v --cov=app --cov-report=term-missing

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

docker-build: ## Build Docker images
	docker compose build

docker-up: ## Start app + PostgreSQL in Docker
	docker compose up -d

docker-down: ## Stop and remove Docker containers
	docker compose down

docker-logs: ## Tail Docker container logs
	docker compose logs -f

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

shell: ## Open a Flask shell
	flask --app app:app shell

routes: ## List all registered routes
	flask --app app:app routes

clean: ## Remove caches and compiled files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov
