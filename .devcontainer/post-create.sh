#!/usr/bin/env bash
# Recreate the full development environment from a clean clone (Codespaces or any devcontainer).
# Uses the same commands as `make install` / `make web-install` and the CI workflows, so a cloud
# environment and a laptop converge on the same toolchain.
set -euo pipefail

echo "==> Backend: venv + runtime and dev dependencies"
cd services/core-api
python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
cd ../..

echo "==> Frontend: npm dependencies"
cd apps/web
npm ci
cd ../..

echo "==> Applying database migrations"
cd services/core-api
# shellcheck disable=SC1091
. .venv/bin/activate
alembic upgrade head || echo "WARNING: migrations did not apply (is the postgres service up?)"
cd ../..

echo
echo "Environment ready. Useful commands:"
echo "  make gates      # full local gate suite (lint, types, tests, contracts, docs)"
echo "  make test-pg    # migrations + PostgreSQL-gated tests"
echo "  make run        # backend on :8000"
echo "  cd apps/web && npm run dev   # frontend on :3000"
