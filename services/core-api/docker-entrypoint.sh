#!/bin/sh
# Portable container entrypoint for any PaaS that injects PORT and a DATABASE_URL (Railway, Koyeb,
# Render, Fly, …). Self-contained: normalises the DB URL to the psycopg dialect, waits for the
# database to accept connections (private networking on some PaaS is only ready a few seconds after
# the container starts), applies migrations, then serves on the platform-provided port over a
# dual-stack socket. No app changes; deployment glue only.
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

# 3. Wait for the database to be reachable before migrating. On Railway/Fly the private network
#    (`*.railway.internal`, IPv6) is not resolvable/connectable for the first few seconds after the
#    container boots, so an immediate `alembic upgrade head` would fail DNS/connect and exit. Retry
#    for up to ~60s. psycopg is already in the image; reuse the app's own URL.
if [ -n "${CS_DATABASE_URL:-}" ]; then
  echo "[entrypoint] waiting for database…"
  python - <<'PY'
import os, sys, time
import psycopg
# psycopg wants a libpq URL (postgresql://…), not the SQLAlchemy dialect (postgresql+psycopg://…).
url = os.environ.get("CS_DATABASE_URL", "")
libpq = url.replace("postgresql+psycopg://", "postgresql://", 1)
deadline = 60
start = None
for attempt in range(1, deadline + 1):
    try:
        with psycopg.connect(libpq, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        print(f"[entrypoint] database reachable after {attempt}s")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 — any connect error means "not ready yet"
        if attempt == 1 or attempt % 5 == 0:
            print(f"[entrypoint] db not ready ({attempt}s): {type(exc).__name__}: {exc}")
        time.sleep(1)
print("[entrypoint] ERROR: database not reachable after 60s", file=sys.stderr)
sys.exit(1)
PY

  echo "[entrypoint] applying migrations…"
  alembic upgrade head
else
  echo "[entrypoint] WARNING: no DATABASE_URL/CS_DATABASE_URL set — skipping migrations" >&2
fi

# 4. Serve on the platform port, bound to 0.0.0.0 (Railway/Koyeb/Render all route their HTTP health
#    check to the IPv4 wildcard — this is the documented requirement). Fallback 8000 for local/compose.
echo "[entrypoint] starting uvicorn on port ${PORT:-8000}"
exec uvicorn taleem_core.main:app --host 0.0.0.0 --port "${PORT:-8000}"
