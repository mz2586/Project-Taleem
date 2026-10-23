#!/usr/bin/env bash
# Browser-level end-to-end journey through the REAL UI (`make e2e-web`): Playwright drives a
# production `next build` of apps/web against a real uvicorn + PostgreSQL.
#
#   1. migrate the database and publish the clearly labelled SYNTHETIC TEST FIXTURE lesson
#   2. start uvicorn (CORS allowing the web origin) and wait for /health
#   3. build apps/web against that API with NEXT_PUBLIC_OFFLINE_SIGNING_KEYS pinned to the API's
#      offline-package public key (so the pinned verification path runs, not trust-on-first-use)
#   4. `next start`, then tests/a11y/web.journey.spec.ts (playwright.e2e.config.ts)
#   5. stop both servers (always)
#
# Evidence in $E2E_WEB_OUT: e2e-web-findings.md (every UI defect: step, route, screenshot), the
# Playwright trace and HTML report, and a numbered screenshot per step.
#
# Requires TALEEM_DATABASE_URL (or CS_DATABASE_URL) naming a disposable PostgreSQL database, Node 20,
# and Playwright Chromium (`npx playwright install --with-deps chromium` in tests/a11y once).
#
#   E2E_WEB_API_PORT (8767)  E2E_WEB_PORT (3200)  E2E_WEB_OUT (default: a temp dir)
#   E2E_WEB_SKIP_BUILD=1     reuse an existing apps/web/.next (must match this API URL and key)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=scripts/e2e/api_server.sh
. "$ROOT/scripts/e2e/api_server.sh"
# shellcheck source=scripts/e2e/web_server.sh
. "$ROOT/scripts/e2e/web_server.sh"

api_require_database
api_python_env

API_PORT="${E2E_WEB_API_PORT:-8767}"
WEB_PORT="${E2E_WEB_PORT:-3200}"
API_URL="http://127.0.0.1:$API_PORT"
WEB_URL="http://127.0.0.1:$WEB_PORT"
OUT="${E2E_WEB_OUT:-$(mktemp -d "${TMPDIR:-/tmp}/taleem-e2e-web.XXXXXX")}"
mkdir -p "$OUT"

cleanup() {
  status=$?
  web_stop
  api_stop
  if [ "$status" -ne 0 ] && [ -f "$OUT/web.log" ]; then
    echo "== e2e-web: exit $status; last web log lines:" >&2
    tail -n 20 "$OUT/web.log" >&2 || true
  fi
  echo "== e2e-web: evidence in $OUT"
  exit "$status"
}
trap cleanup EXIT INT TERM

api_port_free "$WEB_PORT" || { echo "port $WEB_PORT is in use; set E2E_WEB_PORT" >&2; exit 1; }
api_migrate
echo "== e2e-web: seeding the SYNTHETIC TEST FIXTURE lesson (not curriculum)"
python -m taleem_core.tools.e2e_journey --seed-fixture

# The public half of the key the API signs offline packages with, as {key_id: public_key_hex}.
# Public keys are not secret; the private seed never leaves the API process.
PINNED_KEYS="$(python - <<'PY'
import json
from taleem_core.contexts.learning.adapters.package_signer import Ed25519PackageSigner
from taleem_core.platform.config import load_settings

s = load_settings()
signer = Ed25519PackageSigner(s.offline_signing_seed_hex, s.offline_signing_key_id)
print(json.dumps({signer.key_id: signer.public_key_hex}))
PY
)"
echo "== e2e-web: pinning offline signing key(s) $PINNED_KEYS"

TALEEM_CORS_ALLOWED_ORIGINS="$WEB_URL" api_start "$API_PORT" "$OUT/uvicorn.log"
if [ "${E2E_WEB_SKIP_BUILD:-0}" != "1" ]; then
  NEXT_PUBLIC_OFFLINE_SIGNING_KEYS="$PINNED_KEYS" web_build "$API_URL" "$OUT/web-build.log"
fi
web_start "$WEB_PORT" "$OUT/web.log"

cd "$ROOT/tests/a11y"
[ -d node_modules ] || npm ci --no-audit --no-fund
echo "== e2e-web: running the browser journey"
E2E_WEB_URL="$WEB_URL" E2E_WEB_API_URL="$API_URL" E2E_WEB_OUT="$OUT" E2E_WEB_PINNED_KEYS="$PINNED_KEYS" \
  npx --no-install playwright test --config playwright.e2e.config.ts
