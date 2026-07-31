# RC1 Operations Guide

Day-2 operations: monitoring, incident controls, backup, restore, upgrade, and troubleshooting.
Companions: [MONITORING_RUNBOOK.md](MONITORING_RUNBOOK.md), [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md),
[RC1_DEPLOYMENT_GUIDE.md](RC1_DEPLOYMENT_GUIDE.md).

## Monitoring

Golden signals are exposed two ways: Prometheus text at `GET /metrics`, and an authenticated summary
at `GET /v1/ops/status` (role `system` or `mentor`). Key series:

| Metric | Meaning |
| --- | --- |
| `taleem_requests_total{method,path}` | traffic |
| `taleem_errors_total{kind=client\|server}` | 4xx / 5xx counts |
| `taleem_request_duration_ms` | latency (sum + count) |
| `taleem_kill_switch_blocked_total` | child-facing requests refused while halted |
| `taleem_sessions_started_total`, `taleem_objectives_mastered_total`, `taleem_misconceptions_detected_total` | learning signals |
| `taleem_guardian_views_total`, `taleem_guardian_denied_total` | guardian portal usage / denials |

Alert thresholds and the operator response for each signal are in
[MONITORING_RUNBOOK.md](MONITORING_RUNBOOK.md) §3. A kill-switch 503 is deliberately **not** counted
as a server error (it has its own counter), so an intentional halt does not trip the error alert.

## Kill switch (incident halt)

Operator-only control to immediately stop child-facing traffic during an incident. While engaged,
child-facing routes return 503; `/health`, `/metrics`, and `/v1/ops/*` stay reachable so you can
observe and disengage.

```bash
TOK="Bearer <system-jwt>"
curl -XPOST -H "$TOK" -d '{"reason":"incident"}' https://api.taleem.example/v1/ops/kill-switch:engage
curl       -H "$TOK"                              https://api.taleem.example/v1/ops/status
curl -XPOST -H "$TOK"                              https://api.taleem.example/v1/ops/kill-switch:disengage
```

Only the `system` role may flip it (deny-by-default PDP). For when to use it, see
[INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md).

## Backup

The database is the only durable state (sessions are transient; offline sync is idempotent). Back up
PostgreSQL with `pg_dump`:

```bash
pg_dump --format=custom --no-owner \
  "postgresql://USER:PASS@DBHOST:5432/taleem" > taleem-$(date +%Y%m%d-%H%M).dump
```

Schedule regular dumps (e.g. hourly incremental via managed-DB snapshots + daily logical dumps), store
off-site, and encrypt at rest. Also back up the secrets (`TALEEM_JWT_DEV_SECRET`,
`TALEEM_OFFLINE_SIGNING_SEED`) in a secrets manager — losing the signing seed invalidates issued
offline package signatures.

## Restore

```bash
# 1. Stop the API (or engage the kill switch) to prevent writes during restore.
# 2. Recreate/point at an empty database, then:
pg_restore --clean --if-exists --no-owner \
  -d "postgresql://USER:PASS@DBHOST:5432/taleem" taleem-YYYYMMDD-HHMM.dump
# 3. Confirm schema is current, then restart:
docker run --rm -e CS_DATABASE_URL="postgresql+psycopg://USER:PASS@DBHOST:5432/taleem" \
  taleem/core-api:rc1 alembic current      # should equal the deployed image's head
```

Test restores regularly — an untested backup is not a backup. Verify with `make simulate` against the
restored stack.

## Upgrade

Forward-only, migration-first:

```bash
# 1. Back up (above).
# 2. Build the new image (reproducible from requirements.lock).
docker build -t taleem/core-api:<new> services/core-api
# 3. Apply migrations (reversibility is CI-verified).
docker run --rm -e CS_DATABASE_URL=... taleem/core-api:<new> alembic upgrade head
# 4. Deploy the new image; smoke-test.
curl -fsS https://api.taleem.example/health/ready && make simulate
# 5. Rebuild + redeploy the web app if NEXT_PUBLIC_* or the API contract changed.
```

Roll back by redeploying the previous image tag; only `alembic downgrade` if a migration is
demonstrably bad, and always with a fresh backup in hand.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Container exits immediately with `InsecureConfigurationError` | `TALEEM_ENV=production` with default/unset `TALEEM_JWT_DEV_SECRET` / `TALEEM_DATABASE_URL` / `TALEEM_OFFLINE_SIGNING_SEED` | supply real secrets + DB URL |
| Browser app shows "offline" though API is up | CORS: `TALEEM_CORS_ALLOWED_ORIGINS` missing/wrong, or `NEXT_PUBLIC_API_URL` not baked at build | set the exact web origin; rebuild web with the correct API URL |
| 500 on first request after deploy | migrations not applied on PostgreSQL (app does not `create_all`) | run `alembic upgrade head` |
| `409 SESSION_STATE_CONFLICT` on `:teach` | client called out of turn (teach after a non-teach plan) | client should re-plan via `:next` and act on the decision |
| `409 CONFLICT` on a Studio review | concurrent double-submit (optimistic lock) | client reloads and retries |
| `503` on child-facing routes; ops/health OK | kill switch engaged | disengage when the incident is resolved |
| Guardian gets `403` for a child | guardian not linked to that child (or child unknown) | correct the association (`TALEEM_GUARDIAN_LINKS`; production: consent workflow) |
| `429` at the edge | rate limiting (gateway) | expected; tune the gateway, not the app |

Every response carries an `x-correlation-id`; use it to join client reports to server logs (structured
JSON, PII-redacted). If a component is wedged, prefer the kill switch + restart over ad-hoc fixes, and
follow [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md) for anything touching child safety or child data.

## Pre-flight smoke check

Before opening a pilot session, run the synthetic-user simulator (drives the real app: complete
journeys, offline verification, failure injection, recovery). Non-zero exit ⇒ do not proceed.

```bash
make simulate
```
