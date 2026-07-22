# Pilot Runbook

Status: **Phase 9 — Pilot Operations.** The operating manual for the first supervised pilot: onboarding,
offline deployment, daily operations, support, and the data-collection plan. For Pilot 1 (20–50
learners, on-site, supervised, provided devices — [PILOT_PLAN.md](PILOT_PLAN.md)). Reuses the existing
platform; no new architecture. Companions: [DEVICE_PREPARATION.md](DEVICE_PREPARATION.md),
[INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md), [PILOT_SUCCESS_METRICS.md](PILOT_SUCCESS_METRICS.md).

> **Hard gates before any child:** M-Gov (DPIA, consent per child, residency, mandatory-reporting
> policy) and M-Safe (safeguarding live + drilled). No child session starts until both close. Pilot 0
> (internal, no children) runs first.

---

## 1. Roles + staffing (Pilot 1)

| Role | Responsibility |
| --- | --- |
| Site coordinator | Runs the site day-to-day; owns the device fleet + schedule |
| Mentors (≈ 1:10) | Facilitate sessions, own mentor-mediated summative, act on interventions/escalations |
| Safeguarding lead (on-call all pilot hours) | Distress/wellbeing escalations; mandatory reporting |
| Engineering on-call | Sync/app incidents; kill-switch; rollback |
| Content on-call | Content defects flagged by mentors |

---

## 2. Onboarding guide

### 2.1 Site + cohort onboarding

1. Confirm M-Gov closed: **consent recorded per child**, DPIA signed, residency compliant,
   mandatory-reporting policy live.
2. Enrol the cohort (admin/enrolment, M-Gov): assign mentors; **no session without verified consent**.
3. Brief guardians (per [GUARDIAN_EXPERIENCE.md](GUARDIAN_EXPERIENCE.md)): what's collected, consent,
   a human is always reachable, opt-out.
4. Brief mentors ([MENTOR_WORKFLOWS.md](MENTOR_WORKFLOWS.md)) + safeguarding
   ([INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md)).

### 2.2 Learner onboarding (per child, at the site)

1. Guardian consent verified; the child is assigned a **pseudonymous `student_ref`** (no PII on device).
2. Child-safe sign-in (M-Gov auth) on a provided device; age-appropriate, guardian-linked.
3. A short, warm first session with a mentor present; confirm audio-first works for the child.

## 3. Offline deployment guide (daily)

1. **Publish** the day's lessons through the pipeline (Draft → reviews → Publish) — already done for
   Grade 4 content.
2. **Build + sign** each lesson's offline package (6.2A + 6.2C-1 Ed25519).
3. On each device, **download + verify + install** the day's packages; confirm offline render + audio
   ([DEVICE_PREPARATION.md](DEVICE_PREPARATION.md) §3).
4. Confirm the **sync queue is empty** at start of day.
5. Learners work (online or offline); attempts queue offline and **sync with no double-count** (6.2B).

## 4. Daily operating procedure

- **Start of day:** device check (charged, storage, packages verified, queues empty, kill-switch OK);
  Wi-Fi up; safeguarding lead on-call; mentors briefed on today's objectives.
- **During sessions:** mentors circulate, reinforce authored misconception corrections in person, act
  on the AI Teacher's **intervention list** (weak topics) + **escalations**; keep sessions short + kind.
- **On escalation:** the child reaches the **present** mentor/safeguarding lead immediately; the queued
  flag syncs on reconnect.
- **End of day:** confirm **all queues drained** (no pending-to-sync); log content/engagement/safety
  notes; charge + secure devices.
- **SLAs:** distress/wellbeing → human within the safeguarding SLA (on-site immediate); app-blocking
  incident → engineering on-call within the incident SLA ([INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md)).

## 5. Support runbook (common issues → fix)

| Symptom | Likely cause | First action |
| --- | --- | --- |
| Lesson won't open offline | package not installed/verified | re-download + verify; check pinned signing key |
| "Audio not available" | audio asset missing from package | rebuild package; verify audio; interim: text + captions |
| Answers not updating | offline; grading is queued (by design) | reassure; confirm sync drains on reconnect |
| Pending-to-sync not clearing | network down / captive portal | check Wi-Fi; the queue is durable — it drains when back |
| Signature/hash rejected | tampered/corrupt/stale package or key rotated | re-download; refresh pinned key; do **not** bypass verification |
| Child stuck after hints | repeated failure | AI Teacher escalates → **mentor intervenes in person** |
| Wrong learner's data on shared device | profile not switched | "switch learner" clears prior cached view; verify |
| Storage full | low-end device | LRU-evict disposable packages (6.2C-1); never evicts the queue |

**Golden rules:** never bypass signature/hash verification; never delete an **un-synced** queue;
safety always outranks the lesson; if unsure, escalate.

## 6. Data collection plan

- **What is collected:** pseudonymous learning data (C2) — attempts, mastery, evidence, session/sync
  telemetry (C1 counters, no `student_ref`). **No child PII** on device or in telemetry (C3 lives only
  in the governance-gated Identity context, not touched by the pilot surfaces).
- **Why:** to measure the pilot success metrics ([PILOT_SUCCESS_METRICS.md](PILOT_SUCCESS_METRICS.md)):
  learning gain, completion, sync/offline reliability, engagement, mentor load, AI-intervention quality.
- **Basis + consent:** collected only under **informed guardian consent** (M-Gov); guardians told what
  is collected and why; opt-out honored; de-enrolment purges on-device C2 at next connect (6.2C-1).
- **Residency + retention:** in-region storage (FD-02); retention per the schedule (C2 while enrolled +
  tail, then anonymise/partition-drop); telemetry is consent-gated + pseudonymous.
- **Source of truth:** the append-only `AssessmentEvidence` + outbox (learning) and the local sync
  diagnostics (offline) — **no new data pipeline** is introduced.

## 7. Pilot 0 → Pilot 1 gate

Pilot 1 (real children) starts only after **Pilot 0** (internal, no children) passes: every journey
E2E ([END_TO_END_VALIDATION.md](END_TO_END_VALIDATION.md)); a11y + security + **safeguarding drill**
(distress → human within SLA); offline-lite verified on the pilot device; load test with headroom;
**kill-switch + rollback verified**; devices/site/staff/consent ready.

## 8. Kill-switch + rollback

- **Kill-switch:** the operator can halt child-facing use immediately (any serious safety/data
  incident pauses the pilot — [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md)).
- **Rollback:** app/content/package versions can roll back; offline packages are content-hashed +
  signed so a rollback is a verified older package, never an unsigned one.
