#!/usr/bin/env bash
# Automated accessibility scan of apps/web (`make a11y`): axe-core in Playwright, WCAG 2.2 A/AA,
# every route in ur (RTL) and en, signed in through the REAL identity API.
#
#   1. migrate the PostgreSQL database and publish the SYNTHETIC TEST FIXTURE lesson (so learner
#      pages have content to render)
#   2. start uvicorn (CORS allowing the web origin) and wait for /health
#   3. build apps/web against that API and serve it with `next start`
#   4. run tests/a11y (Playwright + @axe-core/playwright); fails on serious/critical violations
#   5. stop both servers (always)
#
# Report: $A11Y_OUT/a11y-report.md and .json (every violation: route, locale, rule, selectors).
#
# Requires TALEEM_DATABASE_URL (or CS_DATABASE_URL) naming a disposable PostgreSQL database, Node 20,
# and a Playwright Chromium (`npx playwright install --with-deps chromium` in tests/a11y once).
#
# Environment knobs:
#   A11Y_API_PORT (8766)  A11Y_WEB_PORT (3100)  A11Y_OUT (default: a temp dir)
#   A11Y_SKIP_BUILD=1     reuse an existing apps/web/.next build (must target the same API URL)
#   A11Y_INSTALL_BROWSER=1  run `playwright install chromium` before the scan
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=scripts/e2e/api_server.sh
. "$ROOT/scripts/e2e/api_server.sh"

api_require_database
api_python_env

API_PORT="${A11Y_API_PORT:-8766}"
WEB_PORT="${A11Y_WEB_PORT:-3100}"
API_URL="http://127.0.0.1:$API_PORT"
WEB_URL="http://127.0.0.1:$WEB_PORT"
OUT="${A11Y_OUT:-$(mktemp -d "${TMPDIR:-/tmp}/taleem-a11y.XXXXXX")}"
mkdir -p "$OUT"
WEB_PID=""
WEB_PGROUP=0

# next forks worker processes, so the web server runs in its own process group (setsid) and the
# whole group is stopped: TERM, then KILL after five seconds. Killing only the parent would orphan
# a next-server that keeps the port.
stop_web() {
  [ -n "$WEB_PID" ] || return 0
  if [ "$WEB_PGROUP" = "1" ]; then
    kill -TERM -- "-$WEB_PID" 2>/dev/null || true
  else
    kill -TERM "$WEB_PID" 2>/dev/null || true
  fi
  for _ in 1 2 3 4 5; do
    kill -0 "$WEB_PID" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$WEB_PID" 2>/dev/null; then
    if [ "$WEB_PGROUP" = "1" ]; then kill -KILL -- "-$WEB_PID" 2>/dev/null || true; fi
    kill -KILL "$WEB_PID" 2>/dev/null || true
  fi
  wait "$WEB_PID" 2>/dev/null || true
  WEB_PID=""
  echo "== a11y: web server stopped"
}

cleanup() {
  status=$?
  stop_web
  api_stop
  if [ "$status" -ne 0 ] && [ -f "$OUT/web.log" ]; then
    echo "== a11y: exit $status; last web log lines:" >&2
    tail -n 20 "$OUT/web.log" >&2 || true
  fi
  exit "$status"
}
trap cleanup EXIT INT TERM

api_port_free "$WEB_PORT" || { echo "port $WEB_PORT is in use; set A11Y_WEB_PORT" >&2; exit 1; }
api_migrate
echo "== a11y: seeding the SYNTHETIC TEST FIXTURE lesson (not curriculum)"
python -m taleem_core.tools.e2e_journey --seed-fixture
TALEEM_CORS_ALLOWED_ORIGINS="$WEB_URL" api_start "$API_PORT" "$OUT/uvicorn.log"

cd "$ROOT/apps/web"
if [ "${A11Y_SKIP_BUILD:-0}" != "1" ]; then
  [ -d node_modules ] || npm ci --no-audit --no-fund
  echo "== a11y: building apps/web against $API_URL"
  NEXT_PUBLIC_API_URL="$API_URL" NEXT_TELEMETRY_DISABLED=1 npm run build >"$OUT/web-build.log" 2>&1 \
    || { tail -n 40 "$OUT/web-build.log" >&2; exit 1; }
fi
echo "== a11y: starting next on $WEB_URL"
NEXT_BIN="$ROOT/apps/web/node_modules/next/dist/bin/next"
if command -v setsid >/dev/null; then
  NEXT_TELEMETRY_DISABLED=1 setsid node "$NEXT_BIN" start -H 127.0.0.1 -p "$WEB_PORT" \
    >"$OUT/web.log" 2>&1 &
  WEB_PGROUP=1
else
  NEXT_TELEMETRY_DISABLED=1 node "$NEXT_BIN" start -H 127.0.0.1 -p "$WEB_PORT" >"$OUT/web.log" 2>&1 &
fi
WEB_PID=$!
for _ in $(seq 1 60); do
  curl -fsS -o /dev/null "$WEB_URL/" 2>/dev/null && break
  kill -0 "$WEB_PID" 2>/dev/null || { echo "next exited early" >&2; exit 1; }
  sleep 1
done
curl -fsS -o /dev/null "$WEB_URL/" || { echo "web app never became ready" >&2; exit 1; }
echo "== a11y: web app is up"

cd "$ROOT/tests/a11y"
[ -d node_modules ] || npm ci --no-audit --no-fund
[ "${A11Y_INSTALL_BROWSER:-0}" = "1" ] && npx --no-install playwright install chromium
echo "== a11y: scanning (report: $OUT/a11y-report.md)"
A11Y_WEB_URL="$WEB_URL" A11Y_API_URL="$API_URL" A11Y_OUT="$OUT" npx --no-install playwright test
