# Monitoring Runbook

Status: **Software Completion Mode.** Operational runbook for the observability that is **actually
implemented** in `core-api`: the golden-signal metrics, the `/v1/ops/status` summary, the
`/metrics` exposition, the operator kill switch, and the alert rules defined as code in
[`infra/monitoring/alerts.yml`](infra/monitoring/alerts.yml). It maps each alert to its meaning and a
first response. Design rationale lives in
[docs/07-engineering/38-monitoring.md](docs/07-engineering/38-monitoring.md); incident handling in
[INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md); pilot operations in
[PILOT0_OPERATIONS.md](PILOT0_OPERATIONS.md); database backup and restore in
[BACKUP_RESTORE_RUNBOOK.md](BACKUP_RESTORE_RUNBOOK.md); load, soak and spike evidence in
[tests/perf/README.md](tests/perf/README.md).

> **Overriding rule:** a child-safety signal outranks any availability or latency alert. When a
> safety concern and a technical alert coincide, act on safety first (see INCIDENT_RESPONSE.md).

**No alert reaches a person yet.** The rules are written, validated (`promtool check rules`) and
unit-tested (`promtool test rules`) in CI, but **no Prometheus, Alertmanager, paging tool or on-call
rota is configured**. Choosing and staffing the destination is an owner decision under M-Safe (§6).
Until then an alert that fires is seen by nobody.

---

## 1. What is instrumented

Every request passes through the observability middleware. Path-like labels carry the matched
**route template** (`/v1/learning/sessions/{session_id}:answer`), never the raw path, so the number
of series stays bounded however many sessions and learners exist. Unrouted requests share the label
`<unmatched>`; requests refused by the kill switch share `<halted>`.

| Metric (`/metrics`) | Type | Meaning |
| --- | --- | --- |
| `taleem_requests_total{method,path}` | counter | Traffic — one per request. |
| `taleem_errors_total{kind="client"}` | counter | Responses with status 4xx. |
| `taleem_errors_total{kind="server"}` | counter | Responses with status 5xx, including unhandled exceptions. |
| `taleem_request_duration_ms{path}` | sum + count | Latency mean (the `/v1/ops/status` average). |
| `taleem_http_request_duration_seconds{method,route,le}` | histogram | Bucketed latency for p95/p99 alerts. Bucket edges include 0.3 s and 0.8 s (PERF-01). |
| `taleem_problem_responses_total{status,code}` | counter | Every RFC 9457 problem response by stable code (`CONSENT_REQUIRED`, `RATE_LIMITED`, …). |
| `taleem_sync_deltas_total{status}` | counter | Offline-sync deltas by outcome: `applied`, `duplicate`, `ignored`, `conflict`. |
| `taleem_sync_batches_refused_total{code}` | counter | Whole sync batches refused by the learner gate (`CONSENT_REQUIRED`, `LEARNER_INACTIVE`). |
| `taleem_kill_switch_engaged` | gauge | `1` while the kill switch is engaged (read at scrape time). |
| `taleem_kill_switch_blocked_total` | counter | Child-facing requests refused while halted. |
| `taleem_ready` | gauge | `1` when `/health/ready` would return 200 (read at scrape time). |
| `taleem_rate_limit_store_errors_total{scope}` | counter | The shared PostgreSQL rate limiter failed and fell back to a per-process limit. |
| `taleem_rate_limited_total{scope}` | counter | Requests refused with 429 by the shared limiter. |
| `taleem_db_pool_checked_out{pool}` / `taleem_db_pool_capacity{pool}` | gauge | SQLAlchemy pool connections in use vs `size + max_overflow`, per pool (`curriculum`, `learning`, `ops`, `identity`; school shares `identity`). |
| `taleem_backup_last_success_timestamp_seconds` | gauge (textfile) | Written by [`infra/monitoring/record_backup_success.sh`](infra/monitoring/record_backup_success.sh) after a successful backup. No scheduled backup calls it yet. |
| `taleem_sessions_started_total`, `taleem_objectives_mastered_total`, `taleem_misconceptions_detected_total` | counter | Learning activity. |

The same signals are summarised, authenticated, at **`GET /v1/ops/status`** (role `system` or
`mentor`) under the `monitoring` and `counters` keys — use this when you cannot scrape `/metrics`:

```json
{
  "kill_switch": {"engaged": false, "reason": "", "changed_at": 0.0},
  "ready": true,
  "version": "0.1.0",
  "counters": {"sessions_started": 20, "objectives_mastered": 15, "misconceptions_detected": 1},
  "monitoring": {
    "requests_total": 214, "errors_server": 0, "errors_client": 3,
    "server_error_rate": 0.0, "avg_request_ms": 24.6
  }
}
```

The registry is per process. With more than one instance (or serverless invocations), Prometheus
must scrape each instance and the alert expressions aggregate across them.

---

## 2. Health probes

| Probe | Endpoint | Healthy | Use |
| --- | --- | --- | --- |
| Liveness | `GET /health` | `200` | Is the process up? (restart target) |
| Readiness | `GET /health/ready` | `200` (else `503`) | Are dependencies ready? (traffic gate) |
| Ops status | `GET /v1/ops/status` | `200` + `ready:true` | Operator dashboard / alert source |

`/health` and `/metrics` and `/v1/ops/*` stay reachable **even when the kill switch is engaged**, so
an operator can always observe and disengage.

---

## 3. Engaging / disengaging the halt

```sh
# Engage (halts child-facing routes with 503; health/ops stay up)
curl -XPOST /v1/ops/kill-switch:engage -H "Authorization: Bearer <system>" -d '{"reason":"incident"}'
# Disengage
curl -XPOST /v1/ops/kill-switch:disengage -H "Authorization: Bearer <system>"
```

Only a `system` operator may flip it (deny-by-default PDP). See INCIDENT_RESPONSE.md for when.

---

## 4. Alert rules as code

| File | Purpose |
| --- | --- |
| [`infra/monitoring/alerts.yml`](infra/monitoring/alerts.yml) | Prometheus alerting rules (16 rules in 6 groups). |
| [`infra/monitoring/alerts_test.yml`](infra/monitoring/alerts_test.yml) | `promtool test rules` cases: each alert fires on a bad synthetic series and stays quiet on a good one. |
| [`infra/monitoring/prometheus.yml`](infra/monitoring/prometheus.yml) | Template scrape config (job `taleem-core-api`); placeholder targets, no Alertmanager. |
| [`infra/monitoring/check_rules.sh`](infra/monitoring/check_rules.sh) | Runs `promtool check rules`, `check config` and `test rules` (pinned Prometheus 2.53.2). `make alerts-check`; CI job `Alert rules (promtool)`. |

Thresholds: API latency follows PERF-01 in
[docs/01-product/04-non-functional-requirements.md](docs/01-product/04-non-functional-requirements.md)
(p95 < 300 ms, p99 < 800 ms). Every other threshold is a **proposal** to tune once a real traffic
baseline exists; the dev-Codespace measurements behind them are in
[tests/perf/README.md](tests/perf/README.md).

| Alert | Severity | Fires when |
| --- | --- | --- |
| `TaleemApiDown` | critical | `up{job="taleem-core-api"} == 0` for 2 min |
| `TaleemNotReady` | critical | `taleem_ready == 0` for 2 min |
| `TaleemHigh5xxRate` / `…Critical` | warning / critical | 5xx > 1% of requests for 5 min / > 5% for 2 min |
| `TaleemLatencyP95OverBudget` | warning | p95 > 300 ms for 10 min (credential routes excluded) |
| `TaleemLatencyP99OverBudget` | warning | p99 > 800 ms for 10 min (credential routes excluded) |
| `TaleemSignInLatencyOverBudget` | warning | sign-in p95 > 1.5 s for 10 min (proposed budget) |
| `TaleemKillSwitchEngaged` | critical | `taleem_kill_switch_engaged == 1` |
| `TaleemConsentRefusalSpike` | warning | > 20 `CONSENT_REQUIRED` responses in 15 min |
| `TaleemRateLimitStoreErrors` | warning | any shared-limiter store error in 5 min |
| `TaleemSyncBatchRejectionSpike` | warning | > 20 sync batches refused or invalid in 15 min |
| `TaleemSyncConflictRatioHigh` | warning | > 5% of synced deltas conflict for 15 min |
| `TaleemDbPoolSaturation` | warning | a pool > 80% checked out for 5 min |
| `TaleemDbPoolExhausted` | critical | a pool 100% checked out for 2 min |
| `TaleemBackupStale` | critical | last successful backup > 26 h old |
| `TaleemBackupNeverReported` | warning | no backup has ever reported success (expected today) |

---

## 5. Each alert: meaning and first response

Capture the `x-correlation-id` of a failing response and the matching log lines before changing
anything. If children are affected and the cause is not understood within minutes, engage the kill
switch (§3) and then triage.

### TaleemApiDown

**Meaning:** Prometheus cannot scrape `/metrics`: the process has crashed, is not listening, or the
network path is broken. **First response:** check `GET /health` directly; read the platform's
deploy and process logs; if a deploy just happened, roll back. If the database is reachable but the
process will not start, check configuration refusals at boot (production refuses a dev JWT seed and
a KDF below 600 000 iterations).

### TaleemNotReady

**Meaning:** the process is up but `/health/ready` probes fail, so it should not receive traffic.
**First response:** `GET /health/ready` shows which check failed. Fix the dependency (usually the
database); do not route traffic to the instance until it reports ready.

### TaleemHigh5xxRate

**Meaning:** more than 1% (warning) or 5% (critical) of requests end in a server error, unhandled
exceptions included. **First response:** group recent `"status": 5xx` log lines by `path`; one route
points to a code or data defect, every route points to the database or a bad deploy. Roll back a
deploy first; otherwise follow INCIDENT_RESPONSE.md.

### TaleemLatencyP95OverBudget

**Meaning:** p95 (or p99) latency of non-credential routes is over the PERF-01 budget for 10
minutes. **First response:** check `TaleemDbPoolSaturation` and host CPU first. Find the slow route:
`histogram_quantile(0.95, sum by (le, route) (rate(taleem_http_request_duration_seconds_bucket[10m])))`.
In the dev-Codespace runs, `GET /v1/offline/packages` was the costliest read (tests/perf/README.md).

### TaleemSignInLatencyOverBudget

**Meaning:** sign-in p95 is over the proposed 1.5 s. Every sign-in runs PBKDF2 at 600 000 iterations,
so this means CPU saturation or a sign-in burst (a class arriving at once, or a credential-stuffing
attempt). **First response:** check `taleem_rate_limited_total` and the 429 count — a rising 429 rate
with many distinct addresses is an attack, not load. Never lower the KDF cost to recover latency; add
capacity instead.

### TaleemKillSwitchEngaged

**Meaning:** an operator engaged the halt; child-facing routes return 503. **First response:**
confirm with the incident lead that it was intended and that an incident record exists
(INCIDENT_RESPONSE.md). Disengage only when the incident lead says so (§3). An unexplained engage is
itself a security incident.

### TaleemConsentRefusalSpike

**Meaning:** many learners are being refused for missing consent. Causes: a guardian bulk-withdrawal,
a consent policy-version bump that invalidated existing grants, or a regression in consent
derivation. **First response:** compare with recent deploys and policy changes; check the identity
audit trail for `consent.withdrawn` and `learner.sign_in_denied_no_consent`. If it is a regression,
treat it as a child-data incident (children's state is being misread) and follow INCIDENT_RESPONSE.md
— never "fix" it by bypassing the consent gate.

### TaleemRateLimitStoreErrors

**Meaning:** the PostgreSQL-backed limiter failed and each instance fell back to its own in-process
limit, so sign-in throttling is weaker across instances (the per-account lockout is unaffected).
**First response:** check database health and the `identity.rate_limit_bucket` table; log lines
`rate_limit_store_unavailable` carry the error type. Restore the store; the limiter recovers by
itself.

### TaleemSyncBatchRejectionSpike

**Meaning:** devices' offline batches are being refused (learner gate: consent withdrawn or account
inactive) or are invalid (`UNKNOWN_DELTA_TYPE`, `MISSING_STUDENT_REF`). Devices keep refused deltas,
so nothing is lost yet, but children's offline work is not arriving. `TaleemSyncConflictRatioHigh`
means deltas arrive but conflict. **First response:** split by code
(`taleem_sync_batches_refused_total` vs `taleem_problem_responses_total`). Invalid deltas after a
client release point to a client/server contract mismatch: hold the client rollout. Refusals point
back to consent state (see the consent alert).

### TaleemDbPoolSaturation

**Meaning:** a SQLAlchemy pool is over 80% (warning) or fully (critical) checked out; further
requests wait for a connection and then fail. **First response:** check for slow queries and lock
waits (`pg_stat_activity`), then for a traffic surge. Each process holds up to 15 connections per
pool across 4 pools; confirm the server's `max_connections` covers every instance before adding
instances.

### TaleemBackupStale

**Meaning:** no successful database backup for over 26 hours. `TaleemBackupNeverReported` means no
backup job has ever reported — **expected today**, because no scheduled backup exists
(BACKUP_RESTORE_RUNBOOK.md §5). **First response:** check the backup job's own logs; run a manual
dump and the drill (`make backup-drill`). The job must call `record_backup_success.sh` only after a
verified dump.

---

## 6. Alert destination — not configured (owner decision, M-Safe)

The rules evaluate nowhere and notify no one until the following exist. None of them is an
engineering decision:

| Needed | Why | Owner |
| --- | --- | --- |
| A deployed Prometheus (or a managed equivalent) scraping every instance | Rules need an evaluator; the scrape config is a template with placeholder targets | Hosting decision (FD-02) |
| An Alertmanager (or the managed tool's router) with receivers per severity | `critical` pages, `warning` goes to a channel | Engineering, once the tool is chosen |
| A paging tool account (for example PagerDuty or Opsgenie) | Somewhere a page can reach a phone | Owner / budget |
| A staffed on-call rota with named primary and secondary | Master scope §19: on-call is ⚫ M-Safe | Owner + safeguarding lead |
| Routing for child-safety signals to the safeguarding lead | Child-safety signals outrank availability (overriding rule above) | Safeguarding lead (M-Safe) |

When these exist: fill in the `alerting:` block in `infra/monitoring/prometheus.yml`, route
`severity="critical"` to the pager, run a game-day that fires each alert once
(OBS-04), and record the result here.

---

## 7. Pre-flight smoke check

Before opening a pilot session, run the synthetic-user simulator against the target build. It drives
complete journeys, verifies signed offline packages, injects failures, and confirms recovery. A
non-zero exit means **do not proceed**.

```sh
make simulate                       # 20 students, offline + failure-injection, quiet
# or, for a JSON artifact to attach to the session record:
python -m taleem_core.tools.pilot_simulator --students 20 --offline --fail-inject --json smoke.json
```

Expected: `verdict: PASS`, all invariants `PASS`, `errors: []`. Investigate any `FAIL` before use.

---

## 8. Escalation

1. Capture the `correlation_id` from the failing response header (`x-correlation-id`) and the
   matching log lines.
2. For any child-safety or child-data signal → INCIDENT_RESPONSE.md (S0/S1) immediately.
3. For availability/latency → engage the kill switch if children are affected, then triage.
