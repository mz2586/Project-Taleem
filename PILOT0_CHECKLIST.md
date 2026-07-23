# Pilot 0 Checklist

Status: **Phase 11 — Pilot 0 Execution Readiness (WS4).** The turnkey checklists for running Pilot 0
(internal dry run, no children): deployment, operator, mentor, guardian, rollback, and support. Reuses
the existing platform + the Phase 9 runbooks; no new architecture. Companion to
[PILOT0_EXECUTION_PLAN.md](PILOT0_EXECUTION_PLAN.md), [PILOT0_OPERATIONS.md](PILOT0_OPERATIONS.md).

> Pilot 0 is **internal, no real children** (synthetic/consenting-adult testers, dev auth stub). It
> **drills** the safeguarding path. Boxes marked **[human/ops]** are executed by people, not code.

---

## 1. Deployment checklist [ops]

- [ ] **Residency:** the environment + package host + telemetry sink are **in-region** (FD-02). *(C4)*
- [ ] **Provision** the staging environment via IaC; PostgreSQL up; migrations applied
      (`alembic upgrade head`) — never `create_all` in a real environment.
- [ ] **Config safety:** production-safe config verified — no default JWT secret, no default offline
      signing seed (the app **fails closed** on defaults); `DATABASE_URL` set.
- [ ] **Signing:** a real Ed25519 signing seed configured server-side (not the dev default); the client
      is configured with the **pinned public key** (`/v1/offline/signing-keys`).
- [ ] **Monitoring + alerting** live (request metrics, error rate, sync health); dashboards visible.
- [ ] **Backups/DR** configured (PITR); a restore is exercised at least once.
- [ ] **Kill-switch + rollback** deployed and **tested** (halt child-facing use; roll back app/content/
      package to a verified signed version).
- [ ] **Content:** the pilot content arc is **published**; **signed offline packages** built + hosted.
      *(C2)*
- [ ] **Audio:** recorded Urdu audio + captions packaged with each lesson; offline playback verified.
      *(C1)*
- [ ] **Smoke:** `GET /health`, `/health/ready`, `/metrics` OK; a full session runs against staging.
- [ ] **Automated assurance suite green** against staging config
      (`pytest tests/test_pilot0_assurance.py`). *(C5 automated)*

## 2. Operator (site coordinator) checklist [ops]

- [ ] **Devices** prepared + verified per [DEVICE_PREPARATION.md](DEVICE_PREPARATION.md): MDM-managed,
      encrypted, locked-down, PWA + SW installed, packages **verified**, persistent storage requested,
      spare-device pool ready.
- [ ] **Network:** guaranteed on-site Wi-Fi up; a captive-portal/offline scenario tested.
- [ ] **Roster:** testers assigned; **no real children** in Pilot 0.
- [ ] **Staffing present:** mentors, **safeguarding lead on-call**, engineering on-call, content
      on-call.
- [ ] **Start-of-day:** device check (charged, storage, packages verified, **queues empty**),
      kill-switch reachable, monitoring visible.
- [ ] **End-of-day:** **all sync queues drained** (no pending-to-sync); notes logged; devices secured.
- [ ] **Assurance run scheduled:** on-device **a11y audit**, **external pentest**, real-device **load
      test**, and the **safeguarding drill** (C5/C6) are booked during Pilot 0.

## 3. Mentor checklist [human]

- [ ] Briefed on [MENTOR_WORKFLOWS.md](MENTOR_WORKFLOWS.md) + the safeguarding runbook.
- [ ] Can open the **learner overview** + **students-needing-intervention** (AI plan weak topics) +
      **escalation review** for a tester.
- [ ] Can act on an escalation **in person** and record a follow-up note.
- [ ] Owns the **mentor-mediated summative** (constructed items reviewed by a human — never
      auto-graded).
- [ ] Reinforces authored misconception corrections in person; keeps sessions short + kind.
- [ ] Knows the escalation ladder + SLA; **safety always outranks the lesson**.

## 4. Guardian checklist [human] (Pilot 0 = adult testers; the guardian *flow* is dry-run)

- [ ] The guardian dashboard composes existing reads (`today`, `history`, `progress`,
      `recommendations`, `notifications`, sync status) — exercised with a test account.
- [ ] Consent + rights messaging is present + clear (what's collected, opt-out, a human is reachable).
      *(Guardian **auth/linkage** is M-Gov — Pilot-1; Pilot 0 dry-runs the flow with a test account.)*
- [ ] Offline sync visibility is honest ("saved; will update when back online").
- [ ] No child PII is shown anywhere (pseudonymous `student_ref` only).

## 5. Rollback procedure [ops]

1. **Trigger:** any S0/S1 incident ([INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md)), or a bad app/content
   release.
2. **Kill-switch first** if child-facing safety/data is at risk — halt use immediately.
3. **App rollback:** redeploy the previous known-good app version.
4. **Content/package rollback:** re-point to the previous **published, signed** package version — a
   rollback is always a **verified** older package, never an unsigned one (signature + content hash
   still enforced).
5. **Data:** offline queues are **durable + idempotent** — no data is lost; a replay is a `duplicate`,
   never a double-count. If needed, restore DB from PITR.
6. **Verify:** health + a smoke session + the automated assurance suite green; confirm queues drain.
7. **Record:** blameless post-incident note; update the risk register.

## 6. Support guide [human, condensed — full version in PILOT_RUNBOOK §5]

| Symptom | First action |
| --- | --- |
| Lesson won't open offline | re-download + **verify**; check pinned signing key |
| "Audio not available" | rebuild package; verify audio; interim: text + captions |
| Answers not updating | reassure — grading is queued offline; confirms on sync (by design) |
| Pending-to-sync not clearing | check Wi-Fi/captive portal; the queue is durable — it drains |
| Signature/hash rejected | re-download / refresh pinned key; **never** bypass verification |
| Child stuck after hints | AI Teacher escalates → **mentor intervenes in person** |
| Wrong learner's data (shared device) | "switch learner" clears the prior cached view |
| Storage full | LRU-evict disposable packages (never the queue) |

**Golden rules:** never bypass signature/hash verification; never delete an **un-synced** queue; safety
outranks the lesson; if unsure, escalate.

---

## 7. Pilot 0 exit (all must be true)

- [ ] Every learner journey passes **end-to-end on the pilot device** (online + offline).
- [ ] **Automated assurance** green; **a11y audit + pentest + real-device load** passed.
- [ ] **Safeguarding drill** routed distress → human within SLA.
- [ ] Offline degrades gracefully (no dead ends); **no data loss / no double-count** observed.
- [ ] **Kill-switch + rollback** verified.
- [ ] Devices/site/staff ready; monitoring + backups live.

**When all Pilot 0 exit boxes are true → Pilot 1 is authorized** (which then needs **M-Gov + M-Safe**
before real children).
