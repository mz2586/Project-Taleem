#!/bin/sh
# Portable container entrypoint for any PaaS that injects PORT and a DATABASE_URL (Railway, Koyeb,
# Render, Fly, …). Self-contained: normalises the DB URL to the psycopg dialect, applies migrations,
# then serves on the platform-provided port. No app changes; deployment glue only.
set -e

# 1. If the platform provides DATABASE_URL (postgres://…) and TALEEM_DATABASE_URL isn't already set,
#    derive it in the SQLAlchemy psycopg dialect the app expects.
if [ -z "${TALEEM_DATABASE_URL:-}" ] && [ -n "${DATABASE_URL:-}" ]; then
  TALEEM_DATABASE_URL=$(printf '%s' "$DATABASE_URL" | sed -E 's#^postgres(ql)?://#postgresql+psycopg://#')
  export TALEEM_DATABASE_URL
fi

# 2. Alembic uses CS_DATABASE_URL; default it to the app's URL.
if [ -z "${CS_DATABASE_URL:-}" ]; then
  CS_DATABASE_URL="${TALEEM_DATABASE_URL:-}"
  export CS_DATABASE_URL
fi

# 3. Apply migrations (idempotent — a no-op when already at head).
if [ -n "${CS_DATABASE_URL:-}" ]; then
  echo "[entrypoint] applying migrations…"
  alembic upgrade head
else
  echo "[entrypoint] WARNING: no DATABASE_URL/CS_DATABASE_URL set — skipping migrations" >&2
fi

# 4. Serve on the platform port (fallback 8000 for local/compose).
echo "[entrypoint] starting uvicorn on port ${PORT:-8000}"
exec uvicorn taleem_core.main:app --host 0.0.0.0 --port "${PORT:-8000}"
