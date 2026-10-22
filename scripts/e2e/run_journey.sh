#!/usr/bin/env bash
# Recorded end-to-end journey against a REAL running Core API backed by PostgreSQL (`make e2e`).
#
#   1. apply the Alembic migrations to the target database
#   2. launch uvicorn in the background on a free local port (default 8765) and wait for /health
#   3. run the journey once with the database as found (CI: a fresh database -> the honest
#      "nothing to learn" branch)
#   4. publish the clearly labelled SYNTHETIC TEST FIXTURE lesson into that database
#   5. run the journey again, which must now complete the fixture lesson
#   6. stop uvicorn (always — also on failure or Ctrl-C)
#
# Requires TALEEM_DATABASE_URL (or CS_DATABASE_URL) to point at a disposable PostgreSQL database. It
# refuses TALEEM_ENV=production: the fixture lesson must never reach a real deployment.
#
# Environment knobs:
#   E2E_PORT          port for uvicorn (default 8765)
#   E2E_FIRST_EXPECT  expectation for the first run: auto | empty | content (default auto)
#   E2E_OUT_DIR       where transcripts + the server log are written (default: a temp dir)
#   E2E_STRICT=1      known product gaps fail the run (exit 2)
#   E2E_SKIP_FIXTURE=1  run only the first journey (no fixture seeding)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CORE="$ROOT/services/core-api"

if [ "${TALEEM_ENV:-}" = "production" ]; then
  echo "refusing: TALEEM_ENV=production (the e2e journey seeds a synthetic fixture)" >&2
  exit 1
fi
export TALEEM_DATABASE_URL="${TALEEM_DATABASE_URL:-${CS_DATABASE_URL:-}}"
export CS_DATABASE_URL="${CS_DATABASE_URL:-$TALEEM_DATABASE_URL}"
if [ -z "$TALEEM_DATABASE_URL" ]; then
  echo "TALEEM_DATABASE_URL (or CS_DATABASE_URL) must name a disposable PostgreSQL database" >&2
  exit 1
fi
case "$TALEEM_DATABASE_URL" in
  postgresql*|postgres*) ;;
  *) echo "the e2e journey must run against PostgreSQL, not '${TALEEM_DATABASE_URL%%:*}'" >&2; exit 1 ;;
esac

# Use the project venv when present (local / Codespace); CI installs into the runner's Python.
if [ -f "$CORE/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  . "$CORE/.venv/bin/activate"
fi
export PYTHONPATH="$CORE/src${PYTHONPATH:+:$PYTHONPATH}"

PORT="${E2E_PORT:-8765}"
BASE_URL="http://127.0.0.1:$PORT"
OUT_DIR="${E2E_OUT_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/taleem-e2e.XXXXXX")}"
mkdir -p "$OUT_DIR"
SERVER_LOG="$OUT_DIR/uvicorn.log"
STRICT=()
[ "${E2E_STRICT:-0}" = "1" ] && STRICT=(--strict)

if python - "$PORT" <<'PY'
import socket, sys
s = socket.socket()
try:
    s.bind(("127.0.0.1", int(sys.argv[1])))
except OSError:
    sys.exit(0)  # in use
finally:
    s.close()
sys.exit(1)
PY
then
  echo "port $PORT is already in use; set E2E_PORT to a free port" >&2
  exit 1
fi

host="${TALEEM_DATABASE_URL##*@}"
echo "== e2e: database ${host%%\?*} (credentials not shown); output in $OUT_DIR"

echo "== e2e: alembic upgrade head"
(cd "$CORE" && alembic upgrade head)

# Trust X-Real-IP for the client address, exactly as a Vercel deployment does, so each journey run
# can present its own synthetic RFC 5737 address and get its own sign-in budget. The shared
# (PostgreSQL) limiter persists across runs, so without this, repeated runs would throttle each
# other.
export TALEEM_CLIENT_IP_HEADER="${TALEEM_CLIENT_IP_HEADER:-x-real-ip}"

echo "== e2e: starting uvicorn on $BASE_URL"
(cd "$CORE" && exec python -m uvicorn taleem_core.main:app --host 127.0.0.1 --port "$PORT" \
  --workers 1 --log-level warning) >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

cleanup() {
  status=$?
  if kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  if [ "$status" -ne 0 ]; then
    echo "== e2e: FAILED (exit $status); last server log lines:" >&2
    tail -n 40 "$SERVER_LOG" >&2 || true
  fi
  echo "== e2e: uvicorn stopped"
  exit "$status"
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 60); do
  if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "uvicorn exited before becoming healthy" >&2
    exit 1
  fi
  sleep 1
done
curl -fsS "$BASE_URL/health" >/dev/null || { echo "uvicorn never became healthy" >&2; exit 1; }
echo "== e2e: /health is up"

journey() {
  local label="$1" expect="$2"
  echo
  echo "== e2e: journey $label (expect: $expect)"
  python -m taleem_core.tools.e2e_journey --base-url "$BASE_URL" --expect "$expect" \
    --client-ip auto --json "$OUT_DIR/journey-$label.json" ${STRICT[@]+"${STRICT[@]}"} | tee "$OUT_DIR/journey-$label.txt"
}

journey 1-as-found "${E2E_FIRST_EXPECT:-auto}"

if [ "${E2E_SKIP_FIXTURE:-0}" != "1" ]; then
  echo
  echo "== e2e: seeding the SYNTHETIC TEST FIXTURE lesson (not curriculum)"
  python -m taleem_core.tools.e2e_journey --seed-fixture
  journey 2-synthetic-fixture content
fi

echo
echo "== e2e: PASS — transcripts in $OUT_DIR"
