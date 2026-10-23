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

# shellcheck source=scripts/e2e/web_server.sh
. "$ROOT/scripts/e2e/web_server.sh"

API_PORT="${A11Y_API_PORT:-8766}"
WEB_PORT="${A11Y_WEB_PORT:-3100}"
API_URL="http://127.0.0.1:$API_PORT"
WEB_URL="http://127.0.0.1:$WEB_PORT"
OUT="${A11Y_OUT:-$(mktemp -d "${TMPDIR:-/tmp}/taleem-a11y.XXXXXX")}"
mkdir -p "$OUT"

cleanup() {
  status=$?
  web_stop
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
[ "${A11Y_SKIP_BUILD:-0}" = "1" ] || web_build "$API_URL" "$OUT/web-build.log"
web_start "$WEB_PORT" "$OUT/web.log"

cd "$ROOT/tests/a11y"
[ -d node_modules ] || npm ci --no-audit --no-fund
[ "${A11Y_INSTALL_BROWSER:-0}" = "1" ] && npx --no-install playwright install chromium
echo "== a11y: scanning (report: $OUT/a11y-report.md)"
A11Y_WEB_URL="$WEB_URL" A11Y_API_URL="$API_URL" A11Y_OUT="$OUT" npx --no-install playwright test --config playwright.config.ts
