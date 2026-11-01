.PHONY: help install lock fmt lint test api frontend downloader extractor frontier searcher up down logs clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Sync the uv workspace
	uv sync --all-packages

lock: ## Refresh uv.lock
	uv lock

fmt: ## Format code
	uv run ruff format .
	uv run ruff check --fix .

lint: ## Lint and typecheck
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy packages services

test: ## Run the test suite
	uv run pytest

api: ## Run the HTTP API
	uv run uvicorn api.main:app --reload

frontend: ## Run the Preact frontend (http://localhost:5173)
	cd frontend && npm run dev

downloader: ## Run the downloader worker
	uv run celery -A downloader.main:app worker -Q download -l info

extractor: ## Run the extractor worker
	uv run celery -A extractor.main:app worker -Q extract -l info

frontier: ## Run the URL frontier API (http://localhost:8001)
	uv run uvicorn frontier.main:app --reload --port 8001

searcher: ## Run the search worker (index + search queues)
	uv run celery -A searcher.main:app worker -Q index,search -l info

up: ## Start the whole stack with docker compose
	docker compose up --build -d

down: ## Stop the stack
	docker compose down

logs: ## Tail the stack logs
	docker compose logs -f

clean: ## Remove caches and the venv
	rm -rf .venv .ruff_cache .mypy_cache .pytest_cache
