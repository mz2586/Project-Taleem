# Monitoring Runbook

Status: **Software Completion Mode.** Operational runbook for the observability that is **actually
implemented** in `core-api`: the golden-signal counters, the `/v1/ops/status` summary, the
`/metrics` exposition, and the operator kill switch. It maps each signal to a concrete alert
threshold and an operator action. Design rationale lives in
[docs/07-engineering/38-monitoring.md](docs/07-engineering/38-monitoring.md); incident handling in
[INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md); pilot operations in
[PILOT0_OPERATIONS.md](PILOT0_OPERATIONS.md).

> **Overriding rule:** a child-safety signal outranks any availability or latency alert. When a
> safety concern and a technical alert coincide, act on safety first (see INCIDENT_RESPONSE.md).

---

## 1. What is instrumented

Every request passes through the observability middleware, which records:

| Metric (`/metrics`) | Type | Meaning |
| --- | --- | --- |
| `taleem_requests_total{method,path}` | counter | Traffic — one per request. |
| `taleem_errors_total{kind="client"}` | counter | Responses with status 4xx. |
| `taleem_errors_total{kind="server"}` | counter | Responses with status 5xx. |
| `taleem_request_duration_ms` | histogram | Latency (sum + count → mean). |
| `taleem_kill_switch_blocked_total` | counter | Child-facing requests refused while halted. |
| `taleem_sessions_started_total` | counter | Learning sessions started. |
| `taleem_objectives_mastered_total` | counter | Objectives reaching mastery. |
| `taleem_misconceptions_detected_total` | counter | Misconceptions confirmed. |

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

## 3. Alert thresholds → actions

Thresholds are starting points for the pilot; tune against a baseline once real traffic exists.

| Signal | Source | Warning | Critical | Action |
| --- | --- | --- | --- | --- |
| Server error rate | `monitoring.server_error_rate` | > 0.01 | > 0.05 | Inspect logs by `correlation_id`; if a bad deploy, roll back. |
| Any 5xx | `errors_server` | ≥ 1 | rising | Triage; a 5xx is never expected on a healthy path. |
| Avg latency | `monitoring.avg_request_ms` | > 250 | > 750 | Check DB/dep health; readiness may be flapping. |
| Readiness | `/health/ready` | one 503 | sustained 503 | Hold traffic; check dependency probes. |
| Kill-switch blocks | `taleem_kill_switch_blocked_total` | any while a session is expected | — | Confirm the halt was intended; disengage when safe. |
| No sessions starting | `sessions_started` flat during a pilot window | — | — | Client/offline-sync problem; check device + queue. |

### Engaging / disengaging the halt

```sh
# Engage (halts child-facing routes with 503; health/ops stay up)
curl -XPOST /v1/ops/kill-switch:engage -H "Authorization: Bearer <system>" -d '{"reason":"incident"}'
# Disengage
curl -XPOST /v1/ops/kill-switch:disengage -H "Authorization: Bearer <system>"
```

Only a `system` operator may flip it (deny-by-default PDP). See INCIDENT_RESPONSE.md for when.

---

## 4. Pre-flight smoke check

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

## 5. Escalation

1. Capture the `correlation_id` from the failing response header (`x-correlation-id`) and the
   matching log lines.
2. For any child-safety or child-data signal → INCIDENT_RESPONSE.md (S0/S1) immediately.
3. For availability/latency → engage the kill switch if children are affected, then triage.
