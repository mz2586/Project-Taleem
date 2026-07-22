# End-to-End Validation

Status: **Phase 9 — Pilot Operations.** Documents + validates the complete pilot journey and confirms
**every step is supported by existing architecture** — no redesign. Companion to
[GUARDIAN_EXPERIENCE.md](GUARDIAN_EXPERIENCE.md), [MENTOR_WORKFLOWS.md](MENTOR_WORKFLOWS.md),
[PILOT_RUNBOOK.md](PILOT_RUNBOOK.md).

The journey:
**Guardian → Student → Lesson → Offline study → Assessment → Synchronization → Guardian reporting →
Mentor intervention.**

---

## 1. The journey, mapped to existing components

| # | Step | Existing component(s) | Verified by (test / gate) | Gate/caveat |
| --- | --- | --- | --- | --- |
| 1 | **Guardian** onboards + consents; sees the dashboard | Guardian experience over derived reads (`today`, `history`, `recommendations`, `notifications`, sync visibility) | `test_student_api` (read models); design in [GUARDIAN_EXPERIENCE.md](GUARDIAN_EXPERIENCE.md) | Guardian **auth/linkage** is M-Gov (thin layer over existing reads) |
| 2 | **Student** signs in + starts a session | `POST /v1/learning/sessions`; Student Portal | `test_student_api`, `test_ai_teacher` (session start) | Child-safe **auth** is M-Gov (dev stub for Pilot 0) |
| 3 | **Lesson** is taught (explain / tutor / hint) | AI Teacher `:explain` (styled, grounded) + session `:teach`/`:answer`/`:hint`; templated runtime | `test_ai_teacher` (grounded, non-generative, no-answer), `test_learning_*`, `test_vertical_slice` | Templated only — no LLM (AR-C-06) |
| 4 | **Offline study** — download, verify, render, work offline | Offline packages (6.2A) + Ed25519 signing (6.2C-1) + IndexedDB + SW | `test_offline_packages`, frontend `packagesHardening`/`signature`/`idb` (fake-indexeddb) | On-site Wi-Fi is the offline-safety compensating control |
| 5 | **Assessment** — score answer; formative auto, summative mentor-mediated | Scorer `evaluate` + `AssessmentEvidence` (append-only) + `assessments` (`mentor_mediated`) | `test_learning_*`, `test_student_api`, `test_sync_evidence` | **Never auto-promotes** (mentor-mediated summative) |
| 6 | **Synchronization** — offline attempts sync as durable evidence | Sync engine `/v1/sync/batch` → durable consumer (6.2B) via `LearningUnitOfWork` | `test_sync_evidence` (duplicate/crash-recovery), frontend `syncClient`/`syncCrashRecovery` | Idempotent — **no data loss, no double-count** |
| 7 | **Guardian reporting** — progress timeline + weekly summary + recommendations | Derived reads (`history`, `progress`, `recommendations`) + AI plan | `test_student_api`, `test_ai_teacher` (plan) | Weekly summary = derived rollup, **no new table** |
| 8 | **Mentor intervention** — triage, escalation review, act, follow-up | Mentor-privileged reads + AI plan `weak_topics` + `guardrail.escalate` + `assessments` | `test_ai_teacher` (plan, escalate, IDOR), `test_student_api` | Cohort roster = admin/enrolment (M-Gov); **per-learner data exists** |

**Result:** every step is supported by a component that already exists and is tested. The only pieces
not present are **governance-gated** (guardian/child auth, cohort roster, remote crisis-flag routing) —
each a thin layer over existing data, not a redesign, and blocked by M-Gov / M-Safe by design.

---

## 2. Detailed walk-through

### Step 1 — Guardian

The guardian consents (M-Gov) and views a dashboard composed of `today` + `notifications` + sync
status. Progress timeline = `history` + `progress`. **Validated:** the derived read models return
these shapes (`test_student_api`). **Gate:** guardian identity + child-linkage land with M-Gov.

### Step 2 — Student

The child signs in and `POST /v1/learning/sessions` starts a session. **Validated:** session start +
the full session flow (`test_student_api`, `test_ai_teacher`, `test_vertical_slice`). **Gate:**
child-safe auth is M-Gov (Pilot 0 uses the dev stub internally).

### Step 3 — Lesson

The AI Teacher `:explain` delivers a styled, **grounded, non-generative** explanation (confidence +
guardrail); the session flow teaches, asks, hints, and corrects — all from **authored** content.
**Validated:** grounding + no-answer + non-generative invariants (`test_ai_teacher`); the session flow
(`test_learning_domain/persistence/api`).

### Step 4 — Offline study

The device downloads the day's package, **verifies the Ed25519 signature + content hash**, installs
atomically, and the lesson **runs fully offline** (templated). **Validated:** backend package build +
signing (`test_offline_packages`, `test_ed25519`); client verify + install + offline render + crash
recovery (frontend `packagesHardening`, `signature`, `idb`, `syncCrashRecovery` over fake-indexeddb).

### Step 5 — Assessment

The scorer grades deterministic items; evidence is **append-only**; summative is **mentor-mediated**
(`assessments.mentor_mediated`). **Validated:** scoring + evidence (`test_learning_*`), the assessment
surface (`test_student_api`). **Guarantee:** no auto-promotion.

### Step 6 — Synchronization

Offline attempts queue and drain to `/v1/sync/batch`; the durable consumer records evidence
**idempotently** (dedupe on `evidence_id` + `client_event_id`). **Validated:** duplicate-upload +
crash-recovery + long-offline-session (`test_sync_evidence`, frontend `syncCrashRecovery`).
**Guarantee:** no loss, no double-count — even after a server restart.

### Step 7 — Guardian reporting

Post-sync, the guardian's timeline + weekly summary + recommendations refresh from the derived reads +
the AI plan. **Validated:** `test_student_api`, `test_ai_teacher` (plan). **Note:** the weekly summary
is a derived rollup over existing evidence/history — **no new child-data table**.

### Step 8 — Mentor intervention

The mentor triages "students needing intervention" (AI plan `weak_topics`), reviews AI Teacher
**escalations** (`guardrail.escalate` + reason), acts **in person**, and records a follow-up.
**Validated:** the plan + escalation + IDOR guard (`test_ai_teacher`); mentor-privileged reads
(`test_student_api`, `test_learning_api`). **Gate:** the cohort roster + persisted notes are
admin/enrolment (M-Gov); per-learner intervention data exists today.

---

## 3. Governance-gated pieces (explicitly, not built here)

| Piece | Gate | Nature (over existing architecture) |
| --- | --- | --- |
| Guardian identity + child-linkage + `guardian` grant | **M-Gov** | thin authz + linkage over existing derived reads |
| Child-safe production auth | **M-Gov** | replaces the dev stub; `Claims.device_id` seam exists |
| Cohort roster + mentor↔learner assignment + persisted notes | **M-Gov** (admin/enrolment) | a roster over existing per-learner data |
| Automated remote crisis-flag routing | **M-Safe** | a `safety.flag` delta over the existing sync path |
| Consent-gated telemetry upload | **consent** | over the existing local diagnostics |

None is a redesign; each is a documented layer over an existing surface, blocked by a governance/safety
gate by design.

---

## 4. Validation status

- **Supported by existing architecture:** ✅ every one of the 8 steps.
- **Automated tests exercising the path:** ✅ backend `test_student_api`, `test_ai_teacher`,
  `test_offline_packages`, `test_ed25519`, `test_sync_evidence`, `test_learning_*`, `test_vertical_slice`;
  frontend `signature`, `packagesHardening`, `idb`, `syncClient`, `syncCrashRecovery`, `reconcile`.
- **Full end-to-end on a device:** the **Pilot 0** dry run (internal, no children) exercises the whole
  journey on the pilot device model — the exit gate before Pilot 1 ([PILOT_RUNBOOK.md](PILOT_RUNBOOK.md) §7).
- **Remaining before real children:** M-Gov + M-Safe (governance/safety gates), not engineering.

The pilot journey is **architecturally complete**: the software supports every step end to end, proven
by the existing test suites; what remains is governance sign-off and the on-site Pilot 0 dry run.
