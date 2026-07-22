# Guardian Experience

Status: **Phase 9 — Pilot Operations & Guardian Experience.** Designs the guardian (parent/guardian)
experience for the first supervised pilot as a **composition of surfaces that already exist** — the
Student Platform's derived read models, the Learning analytics, the AI Teacher plan, and the offline
sync visibility. **No architecture is redesigned; no new child-data table.** Companion to
[MENTOR_WORKFLOWS.md](MENTOR_WORKFLOWS.md), [END_TO_END_VALIDATION.md](END_TO_END_VALIDATION.md),
[PILOT_SUCCESS_METRICS.md](PILOT_SUCCESS_METRICS.md).

> **Governance gate (honest).** A guardian **reading their own child's data** requires a guardian
> identity + guardian↔child linkage + a `guardian` authorization grant. Guardian provisioning is
> **blocked by the Phase-1.5 governance gate (M-Gov)** (child identity, consent). This document
> therefore designs the guardian *experience over data surfaces that already exist* — every panel maps
> to an existing derived read model. When M-Gov closes (WS1/WS3 of the Master Plan), the guardian role
> is a **thin authorization + linkage layer** over these same reads — not new data, not a redesign.
> For Pilot 1 (on-site, supervised), guardian reporting can also be delivered by the **mentor**
> (a privileged reader) as a compensating path.

---

## 0. Reuse map — every guardian panel is an existing surface

| Guardian panel | Existing surface reused |
| --- | --- |
| Dashboard (today) | `GET /v1/learning/students/{ref}/today` (next action + mastery summary + due reviews) |
| Progress timeline | `GET …/history` (sessions + lessons) + `GET …/progress` (mastery summary) |
| Weekly learning summary | derived rollup over `history` + append-only `AssessmentEvidence` (no new table) |
| Attendance & activity | `history.sessions` (session_id, at) → attendance; evidence → activity |
| Learning recommendations | `GET …/recommendations` + `GET …/ai-teacher/plan` (weak topics, revision) |
| Offline sync visibility | client sync diagnostics (6.2B/6.2C-1) + queue depth + `last_sync_at` |
| Notifications | `GET …/notifications` (+ device-local read-state) |

All are **read-only, derived, pseudonymous** (`student_ref` only — no child PII), authenticated,
authorized, and IDOR-guarded (a guardian sees only their linked child; a mentor may read any).

---

## 1. Guardian dashboard

- **Purpose:** a calm, at-a-glance view of how the child is doing today.
- **Content (from `today`):** the next recommended action + objective, a mastery summary
  (mastered / in-progress / total), and the count of due reviews — plus the offline status and any
  unread notifications.
- **Data:** `today` aggregate + `notifications.unread` + sync status. No PII; Urdu-first.
- **Message tone:** encouraging, non-comparative; effort over cleverness (the platform's guardian
  guidance ethos, [PARENT_GUIDE.md](PARENT_GUIDE.md)).

## 2. Student progress timeline

- **Purpose:** how the child has progressed over time.
- **Content (from `history` + `progress`):** a chronological list of sessions (date, objectives
  practised, attempts, correct) and per-objective mastery movement (mastery summary, achievements).
- **Data:** `history.sessions`, `history.lessons`, `progress.mastery`, `achievements`. Derived from
  the append-only evidence + outbox — the same source of truth mentors see.

## 3. Weekly learning summary

- **Purpose:** a once-a-week digest a guardian can absorb in a minute.
- **Content:** objectives worked this week, new masteries, time-on-task (session count), the current
  focus (next action), and one encouragement line.
- **Data:** a **derived weekly rollup** over `history` + `AssessmentEvidence` for the last 7 days —
  computed from existing data, **no new child-data table** (a derived read model, like `today`).
- **Delivery:** shown in-app; optionally summarized by the mentor for guardians without app access
  (pilot).

## 4. Attendance & activity view

- **Purpose:** did the child show up + engage?
- **Content:** attendance (days with ≥ 1 session, from `history.sessions[].at`) and activity (attempts,
  lessons opened) per day.
- **Data:** `history.sessions` + local progress events (`item_attempted`, `lesson_opened` — 6.2A).
  Attendance is derived from session records; no separate attendance table.

## 5. Learning recommendations

- **Purpose:** what the child should focus on + how a guardian can help.
- **Content:** the top recommendations (`recommendations`) and the AI Teacher's weak topics + revision
  plan (`ai-teacher/plan`), each with a plain-language reason, plus the per-subject "2-minute help at
  home" tips from the curriculum guides.
- **Data:** `recommendations` + `ai-teacher/plan.weak_topics/revision_due` (all derived + explainable;
  the AI Teacher is templated — no generative content).

## 6. Offline sync visibility

- **Purpose:** reassure the guardian that offline work is safe + will sync.
- **Content:** current connectivity, pending-to-sync count, last successful sync time, and a plain
  message ("Your child's answers are saved and will update when back online").
- **Data:** the client sync diagnostics + queue depth (6.2B) — local, C1-only counters, **no student
  PII**. Mirrors the `OfflineBadge` honest-status ethos.

## 7. Notifications

- **Purpose:** timely, gentle nudges (a mastery earned, a review due, "come back tomorrow").
- **Content:** the derived notifications feed (`notifications`), with device-local read-state (the
  server keeps **no** read-state table by design, `notifications/{id}:read` is a server no-op).
- **Rules:** rate-limited, purposeful, never alarming or comparative; no PII; opt-out honored.

---

## 8. Privacy, safety, and consent (guardian-facing)

- **No child PII** in any panel — pseudonymous `student_ref` only; guardians see learning data (C2),
  never raw identity.
- **Consent + rights:** the guardian is told plainly what is collected (only what's needed), gives
  **informed consent** before the child takes part (M-Gov), and can ask questions or **opt out** via
  the mentor/coordinator; a de-enrolment purges the child's on-device data at next connect (6.2C-1).
- **A human is always reachable:** wellbeing/safety concerns route to the on-site safeguarding lead
  (Pilot 1) — the guardian is told how.
- **Residency + retention:** guardian-visible data lives in-region and follows the retention schedule
  (governance/config, WS1).

---

## 9. What lands with M-Gov (not built here)

The guardian **role, identity, and child-linkage** (a thin authorization + linkage layer over the same
reads) land with the child-safe auth work (WS3) once M-Gov closes. The **data surfaces already exist**;
Phase 9 designs the experience over them and validates the end-to-end journey
([END_TO_END_VALIDATION.md](END_TO_END_VALIDATION.md)). Nothing here requires new architecture.
