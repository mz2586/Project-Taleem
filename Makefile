# Project Taleem — developer entrypoints.
# `make up` from a clean clone is the onboarding contract (04-NFR MNT-03).

.DEFAULT_GOAL := help
CORE := services/core-api

.PHONY: help
help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	 awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: test
test: ## Run the full test suite with coverage (pytest, in the venv)
	cd $(CORE) && . .venv/bin/activate && pytest --cov=taleem_core --cov-report=term-missing --cov-fail-under=85

.PHONY: test-core
test-core: ## Smoke-run the framework/domain tests with stdlib only (no installs; excludes integration)
	cd $(CORE) && PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_[!i]*.py'

.PHONY: install
install: ## Install backend runtime + dev deps into a venv (requires network)
	cd $(CORE) && python3 -m venv .venv && . .venv/bin/activate && \
	 pip install --upgrade pip && pip install -e ".[dev]"

.PHONY: lint
lint: ## Lint + type-check backend (requires dev deps)
	cd $(CORE) && . .venv/bin/activate && ruff check src tests && black --check src tests && mypy

.PHONY: run
run: ## Run the API locally (requires runtime deps)
	cd $(CORE) && . .venv/bin/activate && uvicorn taleem_core.main:app --reload

.PHONY: docker-build
docker-build: ## Build the core-api container image
	docker build -t taleem/core-api:dev $(CORE)

.PHONY: up
up: ## Bring up the local stack (Postgres, Redis, core-api) via compose
	docker compose up --build

.PHONY: down
down: ## Tear down the local stack
	docker compose down -v

.PHONY: docs-verify
docs-verify: ## Validate blueprint docs (links + markdownlint), same as docs CI
	npx --yes markdownlint-cli2@0.13.0 "**/*.md" "#node_modules"
