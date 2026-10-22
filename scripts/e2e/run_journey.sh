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
#   E2E_STRICT=0      record known product gaps without failing (default 1: a GAP exits 2)
#   E2E_SKIP_FIXTURE=1  run only the first journey (no fixture seeding)
set -euo pipefail

# shellcheck source=scripts/e2e/api_server.sh
. "$(dirname "$0")/api_server.sh"

api_require_database
api_python_env

PORT="${E2E_PORT:-8765}"
BASE_URL="http://127.0.0.1:$PORT"
OUT_DIR="${E2E_OUT_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/taleem-e2e.XXXXXX")}"
mkdir -p "$OUT_DIR"
SERVER_LOG="$OUT_DIR/uvicorn.log"
# Strict by default: every known product gap is closed (GAP 1 in fdd181f, GAP 2 in c8ab6f3), so any
# GAP that appears is a regression and fails the run. E2E_STRICT=0 records gaps without failing.
STRICT=()
[ "${E2E_STRICT:-1}" = "1" ] && STRICT=(--strict)
echo "== e2e: output in $OUT_DIR"

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "== e2e: FAILED (exit $status); last server log lines:" >&2
    tail -n 40 "$SERVER_LOG" >&2 || true
  fi
  api_stop
  exit "$status"
}
trap cleanup EXIT INT TERM

api_migrate
api_start "$PORT" "$SERVER_LOG"

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
