#!/usr/bin/env bash
# Record a SUCCESSFUL database backup for the TaleemBackupStale alert (node_exporter textfile format).
#
#   infra/monitoring/record_backup_success.sh <textfile-dir> [dump-file]
#
# Call it as the last step of the scheduled backup job, only after the dump has been written and
# verified (for example by scripts/db_backup_restore_drill.sh). It writes
# <textfile-dir>/taleem_backup.prom atomically:
#
#   taleem_backup_last_success_timestamp_seconds <unix time>
#   taleem_backup_last_size_bytes <bytes of the dump, when given>
#
# No scheduled backup job exists yet (BACKUP_RESTORE_RUNBOOK.md §5), so nothing calls this today and
# the TaleemBackupNeverReported alert is expected to fire once Prometheus is deployed.
set -euo pipefail

DIR="${1:?usage: $0 <textfile-dir> [dump-file]}"
DUMP="${2:-}"
mkdir -p "$DIR"
TMP="$(mktemp "$DIR/.taleem_backup.prom.XXXXXX")"
{
  echo "# HELP taleem_backup_last_success_timestamp_seconds Unix time of the last successful backup."
  echo "# TYPE taleem_backup_last_success_timestamp_seconds gauge"
  echo "taleem_backup_last_success_timestamp_seconds $(date +%s)"
  if [ -n "$DUMP" ] && [ -f "$DUMP" ]; then
    echo "# HELP taleem_backup_last_size_bytes Size of the last successful backup dump."
    echo "# TYPE taleem_backup_last_size_bytes gauge"
    echo "taleem_backup_last_size_bytes $(wc -c <"$DUMP" | tr -d ' ')"
  fi
} >"$TMP"
chmod 0644 "$TMP"
mv -f "$TMP" "$DIR/taleem_backup.prom"
echo "recorded backup success in $DIR/taleem_backup.prom"
