# Backup and Restore Runbook

Status: **a rehearsed drill, not an operated backup service.** This runbook covers the backup and
restore drill for the Core API's PostgreSQL database: what the script does, how to run it, how to
read the result, and the recovery times measured so far. Design intent (RPO/RTO targets, regions,
retention) lives in [docs/02-architecture/56-bcdr-plan.md](docs/02-architecture/56-bcdr-plan.md).
Monitoring and alerting live in [MONITORING_RUNBOOK.md](MONITORING_RUNBOOK.md), and incident
handling in [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md).

> **What this is not.** No scheduled backup job, off-site copy, retention policy, or encryption key
> management exists yet. There is no verified live environment (master scope §19), so nothing here
> was run against production. Every measurement below names the environment it came from.

---

## 1. What the database holds

One PostgreSQL database holds every bounded context, each in its own schema, all migrated by one
Alembic history (`services/core-api/alembic/`):

| Schema | Contents | Child data? |
| --- | --- | --- |
| `curriculum_studio` | Lessons, versions, review workflow, quality-gate results, audit log | No |
| `learning` | Knowledge state, mastery, assessment evidence, outbox | Yes (pseudonymous) |
| `identity` | Guardian and learner accounts, consent records, refresh tokens, audit events, rate-limit buckets | Yes |
| `ops` | Shared kill-switch state | No |
| `public` | `alembic_version` | No |

A dump therefore contains **child data and credential hashes**. Treat every dump file as
restricted data: never commit it, attach it to a ticket, or copy it to a personal machine.

---

## 2. The drill

`scripts/db_backup_restore_drill.sh` (also `make backup-drill`) runs one full rehearsal:

1. **Backup.** `pg_dump --format=custom --no-owner --no-privileges` of the source database.
2. **Restore.** Creates a scratch database on the same server (`<source>_drill_<epoch>`) and
   runs `pg_restore --exit-on-error` into it. The restore step is timed: that number is the
   **RTO measurement** for a database of this size.
3. **Verify.**
   - The same set of tables exists in both databases, and every table's exact `count(*)` matches.
   - The restored `public.alembic_version` equals the source's.
   - When the Alembic CLI is available, the restored revision also equals the repository's head.
4. **Clean up.** Drops the scratch database it created and deletes the dump.

Exit status is `0` only when every check passes (`verdict: PASS`).

### Safety properties

- The source database is only read. The only `DROP DATABASE` the script issues targets the scratch
  database it created in the same run.
- The connection URL is never printed. Output shows the host and database name only.
- SQLAlchemy URLs (`postgresql+psycopg://…`) are accepted and converted for libpq.

### Running it

```sh
# Uses CS_DATABASE_URL when no argument is given (the same variable Alembic uses).
make backup-drill

# Or name the database explicitly (prefer DRILL_DATABASE_URL so the URL stays out of shell history).
DRILL_DATABASE_URL="$CS_DATABASE_URL" ./scripts/db_backup_restore_drill.sh
```

Requirements: `pg_dump`, `pg_restore`, and `psql` **of at least the server's major version**
(PostgreSQL 16), and a role that may `CREATE DATABASE`. On Debian or Ubuntu without a recent
client, install `postgresql-client-16` from the PostgreSQL apt repository (apt.postgresql.org).

| Variable | Effect |
| --- | --- |
| `DRILL_KEEP_SCRATCH=1` | Keep the restored scratch database for inspection (drop it by hand afterwards) |
| `DRILL_KEEP_DUMP=1` | Keep the dump file; its path is printed |
| `DRILL_JOBS=N` | Run `pg_restore` with `N` parallel jobs (useful once the database is large) |

### Reading the result

| Line | Meaning | If it fails |
| --- | --- | --- |
| `row counts: MATCH` | Every table restored with the same number of rows | A `MISMATCH` lists the differing tables. First rule out writes during the drill (below). Otherwise treat the backup as unusable and investigate before relying on it. |
| `alembic revision: MATCH` | Restored schema is at the same migration as the source | A restore that lands at the wrong revision cannot be served by this build. |
| `repository alembic head: MATCH` | Source is fully migrated for this checkout | `DIFFERS` means the source is behind or ahead of the code. Migrate first, or run the drill from the matching commit. |
| `restore_seconds` | Time to restore the dump (RTO, restore step only) | Compare against the RTO target; see §3. |

**Run the drill against a quiescent database or a branch/replica.** Row counts are read after the
dump, so writes that land mid-drill show up as a mismatch. That is the safe failure, not a false
pass. Two tables churn on their own: `identity.rate_limit_bucket` (rows expire and are purged) and
`identity.refresh_token`. `rate_limit_bucket` is an `UNLOGGED` table, so on a physical replica it is
always empty. Losing it in a real restore is harmless: the limiter simply starts a fresh window.

The summed row total counts partitioned tables twice (the parent and its partitions, for example
`curriculum_studio.audit_log` and `audit_log_default`). The per-table comparison is unaffected.

### In CI

The `E2E journey (uvicorn + PostgreSQL) · backup drill` job in
[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs the drill on every qualifying push. It
uses the database the recorded end-to-end journey has just populated, so the drill restores real
rows across every schema rather than an empty schema. The report is uploaded as the `e2e-evidence`
artifact together with the journey transcripts.

---

## 3. Measured results

RTO here means **restore time for a database of the stated size**. It does not include detecting the
incident, provisioning a server, fetching the dump from off-site storage, or re-pointing the
application. Those steps have no tooling yet, so the end-to-end RTO is unmeasured.

| Date (UTC) | Environment | Server | Data | Dump | Restore (RTO) | Restore + verify | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-22 | **Dev Codespace (not production)**, isolated per-agent database, after `make e2e` | PostgreSQL 16.15, `pg_dump` 16.15 | 31 tables, 96 rows (synthetic journey data + synthetic fixture lesson), Alembic `0006_rate_limit` | 92 164 bytes in 0.21 s | **0.93 s** | 2.69 s | PASS |

What this proves: the dump is complete and restorable, every schema round-trips, and the restored
database is at the expected migration. What it does not prove: anything about production-sized data,
network-attached storage, or a cold standby. Repeat the drill against a production-sized branch
before quoting an RTO to anyone.

---

## 4. Restoring for real

There is no live environment, so this procedure is untested in anger. It is the drill run by hand.

1. **Stop writes.** Engage the kill switch (MONITORING_RUNBOOK.md §3). Child-facing routes return
   503 while ops and health routes stay up.
2. **Pick the dump.** Use the newest dump taken before the incident. Record its timestamp: that is
   the data-loss point (RPO) you are accepting.
3. **Restore into a new database**, never over the damaged one:

   ```sh
   createdb "$NEW_DB"
   pg_restore --no-owner --no-privileges --exit-on-error --dbname="$NEW_DB_URL" taleem.dump
   ```

4. **Verify** the restored database as the drill does: compare table row counts against the dump's
   source where possible, and confirm `SELECT version_num FROM public.alembic_version` equals
   `alembic heads` for the deployed commit.
5. **Re-point the application** (`TALEEM_DATABASE_URL`, or the platform's database binding) to the
   new database, then check `GET /health/ready`.
6. **Disengage the kill switch.** Keep the damaged database for the post-incident review
   (INCIDENT_RESPONSE.md §9) and record the measured restore time in §3 above.

If the incident involves child data (loss, corruption, or exposure), it is an S1 child-data incident.
Follow INCIDENT_RESPONSE.md §3 before and alongside the restore.

---

## 5. Open items

| Item | Status |
| --- | --- |
| Scheduled backups (managed-provider PITR or a cron'd `pg_dump`) | Not implemented; depends on the hosting decision (FD-02) |
| Off-site, encrypted dump storage with retention | Not implemented |
| Production-sized restore rehearsal with a recorded RTO | Not done; needs a live environment |
| Alerting when a scheduled backup fails | Not implemented; needs a staffed alert destination |
