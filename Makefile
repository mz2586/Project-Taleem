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

.PHONY: test-pg
test-pg: ## Run migrations + PostgreSQL-gated tests (requires a Postgres at CS_DATABASE_URL)
	cd $(CORE) && . .venv/bin/activate && alembic upgrade head && \
	 alembic downgrade base && alembic upgrade head && pytest -q

.PHONY: migrate
migrate: ## Apply Alembic migrations (both context schemas) to CS_DATABASE_URL
	cd $(CORE) && . .venv/bin/activate && alembic upgrade head

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

.PHONY: simulate
simulate: ## Run the Pilot 0 synthetic-user simulator (drives the real app; exits non-zero on failure)
	cd $(CORE) && . .venv/bin/activate && \
	 python -m taleem_core.tools.pilot_simulator --students 20 --offline --fail-inject --quiet

.PHONY: e2e
e2e: ## Recorded end-to-end journey: real uvicorn + PostgreSQL at TALEEM_DATABASE_URL (both curriculum branches)
	./scripts/e2e/run_journey.sh

.PHONY: backup-drill
backup-drill: ## Backup + restore drill (pg_dump -> scratch DB -> verify counts + alembic head); prints RTO
	./scripts/db_backup_restore_drill.sh

.PHONY: audit
audit: ## Dependency vulnerability scan: pip-audit (core-api lock) + npm audit (web, prod deps, high+)
	python3 -m pip_audit --strict -r $(CORE)/requirements.lock
	cd $(WEB) && npm audit --omit=dev --audit-level=high

.PHONY: a11y
a11y: ## Automated WCAG 2.2 A/AA scan (axe + Playwright) of every web route, ur + en, real API sign-in
	./scripts/a11y/run_a11y.sh

.PHONY: e2e-web
e2e-web: ## Browser journey through the REAL UI (Playwright): join, consent, lesson, offline + sync, withdrawal
	./scripts/e2e-web/run_e2e_web.sh

.PHONY: release-evidence
release-evidence: ## Reproducible pre-audit evidence report (gates, e2e, drill, audits, a11y) as markdown
	./scripts/release_evidence.sh

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

WEB := apps/web

.PHONY: web-install
web-install: ## Install web deps
	cd $(WEB) && (npm ci || npm install)

.PHONY: web-test
web-test: ## Typecheck + lint (next/core-web-vitals + jsx-a11y strict) + run the web unit suite (vitest)
	cd $(WEB) && npm run typecheck && npm run lint && npm test

.PHONY: web-lint
web-lint: ## ESLint the web app only (also part of web-test)
	cd $(WEB) && npm run lint

.PHONY: web-build
web-build: ## Production build of the web app
	cd $(WEB) && npm run build

.PHONY: contracts
contracts: ## Lint every OpenAPI contract (same pin as CI)
	npx --yes @redocly/cli@1.25.11 lint packages/contracts/*.yaml

.PHONY: gates
gates: lint test web-test contracts docs-verify ## Run the full local gate suite (backend + web + contracts + docs)
	@echo "All gates passed."

.PHONY: release
release: ## Verify tree is release-ready and print the tag command (VERSION required)
	./scripts/release.sh
