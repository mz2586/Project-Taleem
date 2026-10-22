# shellcheck shell=bash
# Shared helpers for harnesses that need a REAL Core API: uvicorn over HTTP with PostgreSQL behind
# it. Sourced by scripts/e2e/run_journey.sh and scripts/a11y/run_a11y.sh; not executable on its own.
#
#   api_require_database   validate TALEEM_DATABASE_URL / CS_DATABASE_URL (PostgreSQL, not prod)
#   api_python_env         activate the project venv when present; put the worktree src first
#   api_port_free PORT     exit 0 if PORT is free on 127.0.0.1
#   api_migrate            alembic upgrade head
#   api_start PORT LOG     launch uvicorn in the background (sets API_PID), wait for /health
#   api_stop               stop uvicorn if running (idempotent; call it from your EXIT trap)
#
# Callers own their EXIT trap so they can stop every process they started.

API_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
API_CORE="$API_ROOT/services/core-api"
API_PID=""

api_require_database() {
  if [ "${TALEEM_ENV:-}" = "production" ]; then
    echo "refusing: TALEEM_ENV=production (these harnesses write synthetic data)" >&2
    return 1
  fi
  export TALEEM_DATABASE_URL="${TALEEM_DATABASE_URL:-${CS_DATABASE_URL:-}}"
  export CS_DATABASE_URL="${CS_DATABASE_URL:-$TALEEM_DATABASE_URL}"
  if [ -z "$TALEEM_DATABASE_URL" ]; then
    echo "TALEEM_DATABASE_URL (or CS_DATABASE_URL) must name a disposable PostgreSQL database" >&2
    return 1
  fi
  case "$TALEEM_DATABASE_URL" in
    postgresql*|postgres*) ;;
    *) echo "must run against PostgreSQL, not '${TALEEM_DATABASE_URL%%:*}'" >&2; return 1 ;;
  esac
  local host="${TALEEM_DATABASE_URL##*@}"
  echo "== api: database ${host%%\?*} (credentials not shown)"
}

api_python_env() {
  # Use the project venv when present (local / Codespace); CI installs into the runner's Python.
  if [ -f "$API_CORE/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    . "$API_CORE/.venv/bin/activate"
  fi
  export PYTHONPATH="$API_CORE/src${PYTHONPATH:+:$PYTHONPATH}"
}

api_port_free() {
  python3 - "$1" <<'PY'
import socket, sys
s = socket.socket()
try:
    s.bind(("127.0.0.1", int(sys.argv[1])))
except OSError:
    sys.exit(1)  # in use
finally:
    s.close()
sys.exit(0)
PY
}

api_migrate() {
  echo "== api: alembic upgrade head"
  (cd "$API_CORE" && alembic upgrade head)
}

api_start() {
  local port="$1" log="$2" base="http://127.0.0.1:$1"
  if ! api_port_free "$port"; then
    echo "port $port is already in use; choose a free port" >&2
    return 1
  fi
  # Trust X-Real-IP for the client address, exactly as a Vercel deployment does, so each harness run
  # can present its own synthetic RFC 5737 address and get its own sign-in budget. The shared
  # (PostgreSQL) limiter persists across runs, so without this, repeated runs throttle each other.
  export TALEEM_CLIENT_IP_HEADER="${TALEEM_CLIENT_IP_HEADER:-x-real-ip}"
  echo "== api: starting uvicorn on $base"
  (cd "$API_CORE" && exec python -m uvicorn taleem_core.main:app --host 127.0.0.1 --port "$port" \
    --workers 1 --log-level warning) >"$log" 2>&1 &
  API_PID=$!
  local _
  for _ in $(seq 1 60); do
    if curl -fsS "$base/health" >/dev/null 2>&1; then
      echo "== api: /health is up"
      return 0
    fi
    if ! kill -0 "$API_PID" 2>/dev/null; then
      echo "uvicorn exited before becoming healthy; last log lines:" >&2
      tail -n 40 "$log" >&2 || true
      return 1
    fi
    sleep 1
  done
  echo "uvicorn never became healthy" >&2
  return 1
}

api_stop() {
  if [ -n "$API_PID" ] && kill -0 "$API_PID" 2>/dev/null; then
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
    echo "== api: uvicorn stopped"
  fi
  API_PID=""
}
