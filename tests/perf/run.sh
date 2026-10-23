#!/usr/bin/env bash
# Load / soak / spike run against a REAL Core API: uvicorn + PostgreSQL, synthetic data only.
#
#   tests/perf/run.sh load|soak|spike          (make perf-load | perf-soak | perf-spike)
#
# Steps: migrate -> seed the synthetic fixture lesson -> start uvicorn (scripts/e2e/api_server.sh)
# -> seed synthetic families/teachers through the public API (setup, not timed) -> sample RSS, DB
# connections and /metrics every 5 s -> k6 -> markdown summary. Every number is "dev Codespace".
#
# Environment:
#   TALEEM_DATABASE_URL / CS_DATABASE_URL   disposable PostgreSQL (required; never production)
#   PERF_PORT            API port (default 8790)
#   PERF_OUT_DIR         output directory (default /tmp/taleem-perf/<profile>-<utc timestamp>)
#   PERF_FAMILIES        synthetic families to seed (default 110; >= total VUs of the profile)
#   PERF_LOAD_VUS / PERF_SOAK_VUS / PERF_SOAK_DURATION / PERF_SPIKE_BASE_VUS   scenario sizes
#   PERF_ENFORCE=1       exit non-zero when a budget threshold is missed (default: report only)
#   K6                   k6 binary (default: k6 on PATH, else the pinned release fetched to /tmp)
#
# Security controls are NOT lowered: the KDF stays at the production minimum (600 000) and the
# sign-in limiter at 10 / 60 s per client. Each virtual user presents its own RFC 5737 address via
# X-Real-IP (TALEEM_CLIENT_IP_HEADER=x-real-ip, the same trust a Vercel deployment uses).
set -euo pipefail

PROFILE="${1:-}"
case "$PROFILE" in
  load|soak|spike) ;;
  *) echo "usage: $0 load|soak|spike" >&2; exit 2 ;;
esac

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../../scripts/e2e/api_server.sh
. "$HERE/../../scripts/e2e/api_server.sh"

PORT="${PERF_PORT:-8790}"
BASE="http://127.0.0.1:$PORT"
OUT="${PERF_OUT_DIR:-/tmp/taleem-perf/$PROFILE-$(date -u +%Y%m%dT%H%M%SZ)}"
FAMILIES="${PERF_FAMILIES:-110}"
K6_VERSION="v1.0.0"
K6_SHA256="5eb2236bc76a3c5cced12aaf0fd76c4b1ceac5ea040c70388a3d272b46595b59"  # linux-amd64 tarball
TOOLS="${PERF_TOOLS_DIR:-/tmp/taleem-perf-tools}"
STAMP="${TOOLS}/last-run-ended"
SAMPLER_PID=""

ensure_k6() {
  if [ -n "${K6:-}" ]; then return 0; fi
  if command -v k6 >/dev/null 2>&1; then K6="$(command -v k6)"; return 0; fi
  K6="$TOOLS/k6-$K6_VERSION"
  if [ -x "$K6" ]; then return 0; fi
  echo "== perf: fetching k6 $K6_VERSION (pinned, sha256-verified) into $TOOLS"
  local dl
  dl="$(mktemp -d)"
  curl -fsSL -o "$dl/k6.tgz" \
    "https://github.com/grafana/k6/releases/download/$K6_VERSION/k6-$K6_VERSION-linux-amd64.tar.gz"
  echo "$K6_SHA256  $dl/k6.tgz" | sha256sum -c - >/dev/null
  tar -xzf "$dl/k6.tgz" -C "$dl"
  mkdir -p "$TOOLS"
  install -m 0755 "$dl/k6-$K6_VERSION-linux-amd64/k6" "$K6"
  rm -rf "$dl"
}

cleanup() {
  if [ -n "$SAMPLER_PID" ]; then kill "$SAMPLER_PID" 2>/dev/null || true; fi
  api_stop
  mkdir -p "$TOOLS" && date +%s >"$STAMP"
}
trap cleanup EXIT

api_require_database
api_python_env
ensure_k6
mkdir -p "$OUT"
echo "== perf: profile $PROFILE, output $OUT (dev Codespace numbers; not production hardware)"

# The shared sign-in limiter persists in PostgreSQL (sliding 60 s window). Back-to-back runs reuse
# the same synthetic addresses, so wait out two windows after the previous run instead of
# loosening the limit.
if [ -f "$STAMP" ]; then
  wait_s=$(( $(cat "$STAMP") + 125 - $(date +%s) ))
  if [ "$wait_s" -gt 0 ]; then
    echo "== perf: waiting ${wait_s}s for the previous run's rate-limit windows to expire"
    sleep "$wait_s"
  fi
fi

api_migrate
(cd "$API_CORE" && python -m taleem_core.tools.e2e_journey --seed-fixture)
api_start "$PORT" "$OUT/api.log"
python "$HERE/seed.py" --base-url "$BASE" --families "$FAMILIES" --out "$OUT/seed.json"

python "$HERE/sampler.py" --pid "$API_PID" --base-url "$BASE" --out "$OUT/samples.csv" &
SAMPLER_PID=$!

echo "== perf: k6 $PROFILE ($("$K6" version | head -n1))"
K6_EXIT=0
PERF_PROFILE="$PROFILE" PERF_BASE_URL="$BASE" PERF_SEED="$OUT/seed.json" \
  PERF_SUMMARY="$OUT/k6-summary.json" \
  "$K6" run --quiet --no-color "$HERE/k6/taleem.js" >"$OUT/k6.log" 2>&1 || K6_EXIT=$?
tail -n 5 "$OUT/k6.log"

kill "$SAMPLER_PID" 2>/dev/null || true
wait "$SAMPLER_PID" 2>/dev/null || true
SAMPLER_PID=""

python "$HERE/summarize.py" --profile "$PROFILE" --k6 "$OUT/k6-summary.json" \
  --samples "$OUT/samples.csv" --k6-exit "$K6_EXIT" --out "$OUT/summary.md" \
  --json-out "$OUT/resources.json"
echo "== perf: artefacts in $OUT (seed.json holds synthetic credentials; delete after review)"

# 99 = thresholds crossed (a budget missed); anything else non-zero is a broken run.
if [ "$K6_EXIT" -ne 0 ] && [ "$K6_EXIT" -ne 99 ]; then exit "$K6_EXIT"; fi
if [ "${PERF_ENFORCE:-0}" = "1" ] && [ "$K6_EXIT" -ne 0 ]; then exit "$K6_EXIT"; fi
exit 0
