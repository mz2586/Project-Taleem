# shellcheck shell=bash
# Shared helpers for harnesses that drive the REAL web app (`next build` + `next start`). Sourced by
# scripts/a11y/run_a11y.sh and scripts/e2e-web/run_e2e_web.sh; not executable on its own.
#
#   web_build API_URL LOG   npm ci when needed, then build apps/web against API_URL. Extra
#                           NEXT_PUBLIC_* variables in the caller's environment are inlined too.
#   web_start PORT LOG      `next start` on 127.0.0.1:PORT in its own process group; waits for "/"
#   web_stop                stop the whole process group (TERM, then KILL after five seconds)
#
# next forks worker processes, so killing only the parent would orphan a next-server that keeps the
# port. Callers own their EXIT trap and call web_stop from it.

WEB_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/apps/web"
WEB_PID=""
WEB_PGROUP=0

web_build() {
  local api_url="$1" log="$2"
  (
    cd "$WEB_ROOT"
    [ -d node_modules ] || npm ci --no-audit --no-fund
    echo "== web: building apps/web against $api_url"
    NEXT_PUBLIC_API_URL="$api_url" NEXT_TELEMETRY_DISABLED=1 npm run build >"$log" 2>&1 \
      || { tail -n 40 "$log" >&2; exit 1; }
  )
}

web_start() {
  local port="$1" log="$2" url="http://127.0.0.1:$1"
  if ! api_port_free "$port"; then
    echo "port $port is in use; choose a free web port" >&2
    return 1
  fi
  echo "== web: starting next on $url"
  local next_bin="$WEB_ROOT/node_modules/next/dist/bin/next"
  if command -v setsid >/dev/null; then
    (cd "$WEB_ROOT" && NEXT_TELEMETRY_DISABLED=1 exec setsid node "$next_bin" start -H 127.0.0.1 -p "$port") \
      >"$log" 2>&1 &
    WEB_PGROUP=1
  else
    (cd "$WEB_ROOT" && NEXT_TELEMETRY_DISABLED=1 exec node "$next_bin" start -H 127.0.0.1 -p "$port") \
      >"$log" 2>&1 &
  fi
  WEB_PID=$!
  local _
  for _ in $(seq 1 60); do
    if curl -fsS -o /dev/null "$url/" 2>/dev/null; then
      echo "== web: app is up"
      return 0
    fi
    if ! kill -0 "$WEB_PID" 2>/dev/null; then
      echo "next exited early; last log lines:" >&2
      tail -n 20 "$log" >&2 || true
      return 1
    fi
    sleep 1
  done
  echo "web app never became ready" >&2
  return 1
}

web_stop() {
  [ -n "$WEB_PID" ] || return 0
  if [ "$WEB_PGROUP" = "1" ]; then
    kill -TERM -- "-$WEB_PID" 2>/dev/null || true
  else
    kill -TERM "$WEB_PID" 2>/dev/null || true
  fi
  local _
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
  echo "== web: server stopped"
}
