#!/usr/bin/env bash
# Backup + restore drill for the Project Taleem PostgreSQL database (BACKUP_RESTORE_RUNBOOK.md).
#
#   scripts/db_backup_restore_drill.sh [DATABASE_URL]
#
# 1. pg_dump the source database (custom format, -Fc)
# 2. create a scratch database on the same server and pg_restore the dump into it, timing the
#    restore (the RTO measurement for this database size)
# 3. verify: the same set of tables exists, every table's row count matches, and the restored
#    alembic_version equals the source's (and the repository's Alembic head when the CLI is present)
# 4. drop the scratch database and delete the dump (unless asked to keep them)
#
# The URL comes from the argument, else DRILL_DATABASE_URL, else CS_DATABASE_URL. SQLAlchemy URLs
# (postgresql+psycopg://) are accepted. The URL is NEVER printed — only host and database name.
# The source database is only ever read; the only database this script drops is the scratch one it
# created itself.
#
# Row counts are compared after the dump, so run the drill against a quiescent database (or a
# replica/branch); writes landing mid-drill show up as a mismatch, which is the safe failure.
#
# Environment knobs:
#   DRILL_KEEP_SCRATCH=1  keep the restored scratch database for inspection
#   DRILL_KEEP_DUMP=1     keep the dump file (path is printed)
#   DRILL_JOBS=N          parallel pg_restore jobs (default 1)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RAW_URL="${1:-${DRILL_DATABASE_URL:-${CS_DATABASE_URL:-}}}"
if [ -z "$RAW_URL" ]; then
  echo "usage: $0 <postgresql-url>   (or set DRILL_DATABASE_URL / CS_DATABASE_URL)" >&2
  exit 64
fi
for tool in pg_dump pg_restore psql; do
  command -v "$tool" >/dev/null || { echo "missing $tool (install the PostgreSQL client)" >&2; exit 69; }
done

# libpq does not understand SQLAlchemy driver suffixes.
SRC_URL="$(printf '%s' "$RAW_URL" | sed -E 's#^postgres(ql)?(\+[a-z0-9]+)?://#postgresql://#')"
# Split off the database name: scheme://authority/dbname[?query]
QUERY=""
case "$SRC_URL" in *\?*) QUERY="?${SRC_URL#*\?}" ;; esac
BASE="${SRC_URL%%\?*}"
SRC_DB="${BASE##*/}"
SERVER="${BASE%/*}"
HOST="${SERVER##*@}"
[ -n "$SRC_DB" ] && [ "$SRC_DB" != "$BASE" ] || { echo "the URL must name a database" >&2; exit 64; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SCRATCH_DB="${SRC_DB}_drill_$(date -u +%s)"
SCRATCH_URL="$SERVER/$SCRATCH_DB$QUERY"
[ "$SCRATCH_DB" != "$SRC_DB" ] || { echo "refusing: scratch name equals source" >&2; exit 70; }
WORK="$(mktemp -d "${TMPDIR:-/tmp}/taleem-drill.XXXXXX")"
DUMP="$WORK/$SRC_DB-$STAMP.dump"
CREATED_SCRATCH=0

now() { python3 -c 'import time; print(f"{time.monotonic():.3f}")'; }
elapsed() { python3 -c "import sys; print(f'{float(sys.argv[2]) - float(sys.argv[1]):.2f}')" "$1" "$2"; }
q() { psql "$1" -X -q -A -t -v ON_ERROR_STOP=1 -c "$2"; }

cleanup() {
  status=$?
  if [ "$CREATED_SCRATCH" = "1" ] && [ "${DRILL_KEEP_SCRATCH:-0}" != "1" ]; then
    q "$SRC_URL" "DROP DATABASE IF EXISTS \"$SCRATCH_DB\"" >/dev/null 2>&1 \
      || echo "warning: could not drop scratch database $SCRATCH_DB" >&2
  fi
  if [ "${DRILL_KEEP_DUMP:-0}" = "1" ]; then
    echo "dump kept at $DUMP"
  else
    rm -rf "$WORK"
  fi
  exit "$status"
}
trap cleanup EXIT INT TERM

echo "== backup/restore drill  $STAMP"
echo "   source:   $HOST/$SRC_DB (credentials not shown)"
echo "   scratch:  $HOST/$SCRATCH_DB"
echo "   pg_dump:  $(pg_dump --version)"
echo "   server:   $(q "$SRC_URL" 'SHOW server_version')"

# Table inventory + exact row counts, as "schema.table<TAB>count" lines, sorted.
TABLES_SQL="SELECT quote_ident(schemaname) || '.' || quote_ident(tablename) FROM pg_tables
  WHERE schemaname NOT IN ('pg_catalog', 'information_schema') ORDER BY 1"
counts() {
  local url="$1" t
  for t in $(q "$url" "$TABLES_SQL"); do
    printf '%s\t%s\n' "$t" "$(q "$url" "SELECT count(*) FROM $t")"
  done
}
alembic_rev() { q "$1" "SELECT string_agg(version_num, ',' ORDER BY version_num) FROM public.alembic_version" 2>/dev/null || echo "(none)"; }

echo "== 1. pg_dump (custom format)"
t0="$(now)"
pg_dump --format=custom --no-owner --no-privileges --file="$DUMP" "$SRC_URL"
t1="$(now)"
DUMP_BYTES="$(wc -c <"$DUMP" | tr -d ' ')"
echo "   dump: $DUMP_BYTES bytes in $(elapsed "$t0" "$t1")s"
SRC_COUNTS="$(counts "$SRC_URL")"
SRC_REV="$(alembic_rev "$SRC_URL")"

echo "== 2. restore into scratch database"
q "$SRC_URL" "CREATE DATABASE \"$SCRATCH_DB\"" >/dev/null
CREATED_SCRATCH=1
t2="$(now)"
pg_restore --no-owner --no-privileges --exit-on-error --jobs="${DRILL_JOBS:-1}" \
  --dbname="$SCRATCH_URL" "$DUMP"
t3="$(now)"
RESTORE_S="$(elapsed "$t2" "$t3")"
echo "   restore: ${RESTORE_S}s"

echo "== 3. verify"
DST_COUNTS="$(counts "$SCRATCH_URL")"
DST_REV="$(alembic_rev "$SCRATCH_URL")"
t4="$(now)"
fail=0
TABLES="$(printf '%s\n' "$SRC_COUNTS" | grep -c . || true)"
ROWS="$(printf '%s\n' "$SRC_COUNTS" | awk -F'\t' '{s += $2} END {print s + 0}')"
if [ "$SRC_COUNTS" = "$DST_COUNTS" ]; then
  echo "   row counts: MATCH ($TABLES tables, $ROWS rows)"
else
  echo "   row counts: MISMATCH"
  diff <(printf '%s\n' "$SRC_COUNTS") <(printf '%s\n' "$DST_COUNTS") | sed 's/^/     /' || true
  fail=1
fi
printf '%s\n' "$SRC_COUNTS" | awk -F'\t' '{printf "     %-48s %s\n", $1, $2}'
if [ "$SRC_REV" = "$DST_REV" ] && [ "$SRC_REV" != "(none)" ]; then
  echo "   alembic revision: MATCH ($SRC_REV)"
else
  echo "   alembic revision: MISMATCH (source $SRC_REV, restored $DST_REV)"
  fail=1
fi
REPO_HEAD=""
if command -v alembic >/dev/null && [ -f "$ROOT/services/core-api/alembic.ini" ]; then
  REPO_HEAD="$(cd "$ROOT/services/core-api" && alembic heads 2>/dev/null | awk '{print $1}' | sort | paste -sd, - || true)"
fi
if [ -n "$REPO_HEAD" ]; then
  if [ "$REPO_HEAD" = "$DST_REV" ]; then
    echo "   repository alembic head: MATCH ($REPO_HEAD)"
  else
    echo "   repository alembic head: DIFFERS (repo $REPO_HEAD, restored $DST_REV)"
    fail=1
  fi
else
  echo "   repository alembic head: not checked (alembic CLI unavailable)"
fi

echo "== result"
echo "   dump_seconds=$(elapsed "$t0" "$t1") dump_bytes=$DUMP_BYTES"
echo "   restore_seconds=$RESTORE_S   (RTO for this database size, restore step only)"
echo "   restore_plus_verify_seconds=$(elapsed "$t2" "$t4")"
if [ "$fail" = "0" ]; then
  echo "   verdict: PASS"
else
  echo "   verdict: FAIL"
  exit 1
fi
