#!/usr/bin/env bash
# Validate the alerting rules as code: syntax (check rules), wiring (check config) and behaviour
# (test rules — synthetic series in alerts_test.yml). Used by CI and locally.
#
#   infra/monitoring/check_rules.sh
#
# Uses PROMTOOL, else promtool on PATH, else downloads the pinned Prometheus release (sha256-checked)
# into ${PROMTOOL_DIR:-/tmp/taleem-promtool}. Linux amd64 only for the download path.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="2.53.2"
SHA256="60c126740c9cf1206b1e72150dd17914f1c3309bb7dc78a31d4670197ed4fa69"  # linux-amd64 tarball
DIR="${PROMTOOL_DIR:-/tmp/taleem-promtool}"

if [ -z "${PROMTOOL:-}" ]; then
  if command -v promtool >/dev/null 2>&1; then
    PROMTOOL="$(command -v promtool)"
  else
    PROMTOOL="$DIR/promtool-$VERSION"
    if [ ! -x "$PROMTOOL" ]; then
      echo "== promtool: fetching Prometheus $VERSION (pinned, sha256-verified) into $DIR"
      dl="$(mktemp -d)"
      curl -fsSL -o "$dl/prom.tgz" \
        "https://github.com/prometheus/prometheus/releases/download/v$VERSION/prometheus-$VERSION.linux-amd64.tar.gz"
      echo "$SHA256  $dl/prom.tgz" | sha256sum -c - >/dev/null
      tar -xzf "$dl/prom.tgz" -C "$dl"
      mkdir -p "$DIR"
      install -m 0755 "$dl/prometheus-$VERSION.linux-amd64/promtool" "$PROMTOOL"
      rm -rf "$dl"
    fi
  fi
fi

echo "== $("$PROMTOOL" --version 2>&1 | head -n1)"
"$PROMTOOL" check rules "$HERE/alerts.yml"
"$PROMTOOL" check config --syntax-only "$HERE/prometheus.yml"
"$PROMTOOL" test rules "$HERE/alerts_test.yml"
echo "== alert rules: OK"
