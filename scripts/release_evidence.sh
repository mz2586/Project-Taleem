#!/usr/bin/env bash
# Reproducible pre-audit evidence report (`make release-evidence`).
#
#   scripts/release_evidence.sh [OUTPUT_DIR]   (default: $TMPDIR/taleem-release-evidence/<UTC stamp>)
#
# Runs the automated checks an external auditor would otherwise ask for, then writes ONE markdown
# report (OUTPUT_DIR/release-evidence.md) with the commit, tool versions, and a summary of each:
#
#   gates       make lint / test / web-test / contracts / docs-verify
#   e2e         make e2e   — recorded journey against a real uvicorn + PostgreSQL
#   drill       make backup-drill — dump, restore into scratch DB, verify, RTO
#   pip-audit   core-api runtime lock
#   npm audit   apps/web production dependencies, high and above
#   a11y        make a11y  — axe WCAG 2.2 A/AA, every route, ur + en
#
# Full logs sit next to the report (OUTPUT_DIR/logs/). The report holds summary lines only; the
# harnesses never print tokens, passphrases, PINs, or connection strings, and this script never
# prints the database URL. Data is synthetic only.
#
# This is self-generated evidence. It is NOT an external audit, penetration test, or accessibility
# audit, and the report says so.
#
# Needs: the core-api venv (or deps on PATH), Node 20, a disposable PostgreSQL at
# TALEEM_DATABASE_URL / CS_DATABASE_URL for e2e, drill and a11y, the PostgreSQL 16 client tools,
# pip-audit (`pip install pip-audit`), and Playwright Chromium for a11y.
#
#   EVIDENCE_ENV="dev Codespace"   environment label printed in the report (default: "local")
#   EVIDENCE_SKIP="a11y drill"     space-separated sections to skip (recorded as SKIPPED)
#
# Exit status: 0 when every section that ran passed, 1 otherwise. The report is written either way.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Default output is outside the repository: generated markdown must never be linted as a blueprint
# doc or committed by accident. Attach the report to the audit record instead.
OUT="${1:-${TMPDIR:-/tmp}/taleem-release-evidence/$(date -u +%Y%m%dT%H%M%SZ)}"
LOGS="$OUT/logs"
mkdir -p "$LOGS"
REPORT="$OUT/release-evidence.md"
SKIP=" ${EVIDENCE_SKIP:-} "
ENV_LABEL="${EVIDENCE_ENV:-local}"
OVERALL=0
SECTIONS=()

if [ -f services/core-api/.venv/bin/activate ]; then
  # shellcheck disable=SC1091
  . services/core-api/.venv/bin/activate
fi

# run NAME LOGFILE COMMAND... -> sets STATUS (PASS/FAIL/SKIPPED) and SECONDS_TAKEN
run() {
  local name="$1" log="$2"
  shift 2
  if [[ "$SKIP" == *" $name "* ]]; then
    STATUS="SKIPPED"
    SECONDS_TAKEN=0
    echo "skipped by EVIDENCE_SKIP" >"$log"
    return
  fi
  echo "== evidence: $name"
  local start=$SECONDS
  if "$@" >"$log" 2>&1; then STATUS="PASS"; else STATUS="FAIL"; OVERALL=1; fi
  SECONDS_TAKEN=$((SECONDS - start))
  echo "   $STATUS (${SECONDS_TAKEN}s)"
}

# Lines from a log matching a pattern, fenced for the report (never the whole log).
excerpt() {
  local log="$1" pattern="$2"
  echo '```text'
  # Strip ANSI colour codes (vitest, npm) so the report renders cleanly.
  sed $'s/\x1b\\[[0-9;]*m//g' "$log" | grep -E "$pattern" | grep -v '^{' | tail -n "${3:-20}" \
    || echo "(no summary lines found; see the log)"
  echo '```'
}

section() { SECTIONS+=("$1"); }

# ---------------------------------------------------------------------------------------- gates
GATE_ROWS=""
for gate in lint test web-test contracts docs-verify; do
  run "gates" "$LOGS/gate-$gate.log" make "$gate"
  GATE_ROWS+="| \`make $gate\` | $STATUS | ${SECONDS_TAKEN}s | [log](logs/gate-$gate.log) |"$'\n'
done
section "## 1. Quality gates

| Gate | Result | Time | Log |
| --- | --- | --- | --- |
${GATE_ROWS}
Backend test summary and coverage:

$(excerpt "$LOGS/gate-test.log" '^TOTAL|passed|failed' 5)

Web test summary:

$(excerpt "$LOGS/gate-web-test.log" 'Test Files|Tests ' 4)"

# ------------------------------------------------------------------------------------------ e2e
run "e2e" "$LOGS/e2e.log" env E2E_OUT_DIR="$OUT/e2e" make e2e
section "## 2. Recorded end-to-end journey (real uvicorn + PostgreSQL)

Result: **$STATUS** (${SECONDS_TAKEN}s). Transcripts: \`e2e/journey-*.txt\` and \`.json\`.
Run 1 uses the database as found; run 2 uses the clearly labelled synthetic fixture lesson.

$(excerpt "$LOGS/e2e.log" '^verdict|^curriculum branch|^   - step|FAIL ' 20)"

# ---------------------------------------------------------------------------------------- drill
run "drill" "$LOGS/backup-drill.log" make backup-drill
section "## 3. Backup and restore drill

Result: **$STATUS**. Procedure and measured history: \`BACKUP_RESTORE_RUNBOOK.md\` in the repository.

$(excerpt "$LOGS/backup-drill.log" 'source:|server:|row counts|alembic|_seconds|dump_bytes|verdict' 12)"

# ------------------------------------------------------------------------------------ pip-audit
# A standalone pip-audit on PATH (e.g. pipx) is preferred; else the module in the active Python.
PIP_AUDIT=()
if command -v pip-audit >/dev/null 2>&1; then
  PIP_AUDIT=(pip-audit)
elif python3 -m pip_audit --version >/dev/null 2>&1; then
  PIP_AUDIT=(python3 -m pip_audit)
fi
if [ "${#PIP_AUDIT[@]}" -gt 0 ]; then
  run "pip-audit" "$LOGS/pip-audit.log" "${PIP_AUDIT[@]}" --strict -r services/core-api/requirements.lock
else
  STATUS="NOT RUN"
  echo "pip-audit is not installed (pip install pip-audit)" >"$LOGS/pip-audit.log"
  OVERALL=1
fi
PIP_STATUS="$STATUS"
run "npm-audit" "$LOGS/npm-audit.log" bash -c "cd apps/web && npm audit --omit=dev --audit-level=high"
section "## 4. Dependency vulnerability scans

| Scan | Scope | Result |
| --- | --- | --- |
| pip-audit | \`services/core-api/requirements.lock\` (runtime closure) | $PIP_STATUS |
| npm audit | \`apps/web\` production dependencies, severity high and above | $STATUS |

$(excerpt "$LOGS/pip-audit.log" 'vulnerab|Found|No known' 5)

$(excerpt "$LOGS/npm-audit.log" 'vulnerabilit|Severity|found 0' 10)"

# ----------------------------------------------------------------------------------------- a11y
run "a11y" "$LOGS/a11y.log" env A11Y_OUT="$OUT/a11y" make a11y
A11Y_SUMMARY="(no report produced)"
[ -f "$OUT/a11y/a11y-report.md" ] && A11Y_SUMMARY="$(sed -n '3,3p' "$OUT/a11y/a11y-report.md")"
section "## 5. Automated accessibility scan (axe-core, WCAG 2.2 A/AA)

Result: **$STATUS**. $A11Y_SUMMARY
Full report with every route, locale, rule and selector: \`a11y/a11y-report.md\`; screenshots in
\`a11y/screenshots/\`. Automated checks find a subset of WCAG failures."

# --------------------------------------------------------------------------------------- report
VERDICT="PASS"
[ "$OVERALL" -eq 0 ] || VERDICT="FAIL"
{
  echo "# Release evidence report"
  echo
  echo "> **Self-generated, automated evidence.** This is not an external audit. No external penetration"
  echo "> test (EV-04) or accessibility audit (EV-05) has been performed; see"
  echo "> EXTERNAL_VALIDATION_CHECKLIST.md. All data is synthetic."
  echo
  echo "| | |"
  echo "| --- | --- |"
  echo "| Commit | \`$(git rev-parse HEAD 2>/dev/null || echo unknown)\`$(git diff --quiet 2>/dev/null || echo ' (working tree has uncommitted changes)') |"
  echo "| Generated (UTC) | $(date -u +%Y-%m-%dT%H:%M:%SZ) |"
  echo "| Environment | $ENV_LABEL (not production) |"
  echo "| Python | $(python3 --version 2>&1) |"
  echo "| Node / npm | $(node --version 2>/dev/null) / $(npm --version 2>/dev/null) |"
  echo "| PostgreSQL client | $(pg_dump --version 2>/dev/null || echo 'not installed') |"
  echo "| Overall | **$VERDICT** |"
  echo
  echo "Reproduce: \`EVIDENCE_ENV=\"<label>\" make release-evidence\` at the same commit."
  echo
  for s in "${SECTIONS[@]}"; do
    echo "$s"
    echo
  done
} >"$REPORT"

echo "== evidence: $VERDICT — report at $REPORT"
exit "$OVERALL"
