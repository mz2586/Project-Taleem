# Pilot 0 Operations

Status: **Phase 11 — Pilot 0 Execution Readiness (WS4).** The operations guide for running the Pilot 0
dry run: go-live sequence, monitoring, on-call, the safeguarding drill, kill-switch/rollback, and the
day-of procedure. Consolidates + operationalizes the Phase 9 runbooks; reuses the existing platform, no
new architecture. Companion to [PILOT0_CHECKLIST.md](PILOT0_CHECKLIST.md),
[PILOT0_EXECUTION_PLAN.md](PILOT0_EXECUTION_PLAN.md), [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md).

> Pilot 0 is **internal, no children**. It proves the platform + operations end-to-end and **exits into
> Pilot 1**. Governance gates (M-Gov/M-Safe) block Pilot 1, not Pilot 0.

---

## 1. Go-live sequence (bring up the Pilot 0 environment)

1. **Residency + provision** the in-region staging environment (IaC); PostgreSQL up; `alembic upgrade
   head`.
2. **Config safety:** verify the app **fails closed** on defaults — a real JWT secret and a real
   offline **signing seed** are set (not the dev defaults); `DATABASE_URL` set.
3. **Publish + package content:** publish the pilot arc through the pipeline; **build + sign** offline
   packages; host them in-region; distribute the **pinned public key** to devices.
4. **Observability:** monitoring + alerting + dashboards up; backups/DR (PITR) configured + restore
   exercised.
5. **Kill-switch + rollback:** deploy and **test** both.
6. **Smoke + assurance:** `/health`, `/health/ready`, `/metrics` OK; run a full session; run the
   **automated assurance suite** (`pytest tests/test_pilot0_assurance.py`) green against staging.
7. **Devices:** prepare + verify per [DEVICE_PREPARATION.md](DEVICE_PREPARATION.md).

## 2. Monitoring + health

- **Liveness/readiness:** `GET /health`, `GET /health/ready` (dependency probes).
- **Metrics:** `GET /metrics` (Prometheus) — request rate, latency, error rate; learning-write
  telemetry (`taleem_learning_attempts_total`, `taleem_objectives_mastered_total`, …); sync health.
- **Correlation IDs** on every request (structured logs) for tracing an incident — **no child PII in
  logs** (pseudonymous `student_ref` only).
- **Sync health:** watch dead-letter count (should be ~0), queue-drain time on reconnect, and
  integrity/signature-failure counters (client diagnostics, C1-only).

## 3. On-call + roles (day of)

| Role | On-call for |
| --- | --- |
| Site coordinator | device fleet, schedule, start/end-of-day checks |
| Mentors | facilitation, interventions, mentor-mediated summative |
| **Safeguarding lead** | **all safety escalations (S0)** — the priority, on-call all hours |
| Engineering | app/sync incidents, kill-switch, rollback |
| Content | content defects flagged by mentors |

## 4. Day-of procedure

- **Start of day:** device check (charged, storage, packages **verified**, **queues empty**),
  kill-switch reachable, monitoring visible, staffing present.
- **During:** mentors circulate + act on the AI Teacher intervention list + escalations; watch
  monitoring; any escalation reaches the **present** human immediately.
- **End of day:** confirm **all queues drained**; log content/engagement/safety notes; secure devices.

## 5. Safeguarding drill (C6) [human]

The drill proves the safety net **before** any child (Pilot 1):

1. **Setup:** safeguarding lead on-call; the escalation + reporting workflow configured.
2. **Simulate:** a tester triggers a distress/help signal (in-app affordance and/or the decision-engine
   `ESCALATE` path).
3. **Verify routing:** the signal reaches a **human within the SLA** (T0 ≤ 5 min tier); the present
   safeguarding lead responds.
4. **Verify offline:** trigger it offline — the affordance shows packaged self-help + "tell your mentor
   now"; a **priority safety flag queues** and syncs first on reconnect.
5. **Verify reporting:** the mandatory-reporting workflow is exercised per policy (M-Safe).
6. **Record + review:** log the drill; a miss ⇒ **fix before Pilot 1**.

**Exit:** distress → human within SLA, online and (queued) offline; reporting workflow verified.

## 6. Kill-switch + rollback

- **Kill-switch:** halt child-facing use immediately for any S0/S1 — a serious safety/data incident
  **pauses the pilot** ([INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md)).
- **Rollback:** roll back app/content/package to a **verified, signed** older version (signature +
  content hash still enforced; a rollback is never an unsigned package). DB restore from PITR if needed.
- **Data safety on rollback:** offline queues are durable + idempotent → **no loss, no double-count**;
  reconnect drains them.

## 7. Incident handling (summary; full in INCIDENT_RESPONSE.md)

- **S0 child-safety:** protect the child, pause, escalate to the safeguarding lead — **outranks
  everything**; never delay to debug software first.
- **S1 data/content:** contain (switch/clear profile; kill-switch), assess (C2 learning only, no PII),
  notify DPO/safeguarding, remediate (+ purge on de-enrolment).
- **S2 sync/availability:** durable queue = no loss; verify idempotency; drain on reconnect;
  re-verify packages (never bypass verification).

## 8. Success metrics during Pilot 0

Track the [PILOT_SUCCESS_METRICS.md](PILOT_SUCCESS_METRICS.md) signals from existing data — **north
star: zero unhandled safety incidents.** Any open Critical safety/data issue ⇒ **do not exit** to
Pilot 1.

## 9. Pilot 0 exit → Pilot 1

Exit when every [PILOT0_CHECKLIST.md](PILOT0_CHECKLIST.md) §7 box is true. Pilot 1 (real children) then
needs **M-Gov + M-Safe** — the governance/safeguarding gates — before it starts.
