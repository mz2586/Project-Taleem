# Student API Requirements (Phase 5 Design)

Status: **Design only.** Companion to [STUDENT_EXPERIENCE.md](STUDENT_EXPERIENCE.md). Enumerates every
API the Student Portal needs, separating what **already exists** (the built `/v1/learning` API) from
what is **new** and must be designed → reviewed → built (same design-first discipline as Phases 3–4.2)
before the portal ships. No implementation here.

**Cross-cutting requirements for every student endpoint:**

- **Auth:** verified bearer JWT, `role: student`, `sub == student_ref`. The platform already
  **IDOR-guards** learner endpoints (a learner reaches only their own data) and applies deny-by-default
  PDP — new endpoints MUST follow the same pattern (mentor-privileged reads allowed only for the
  mentor surface, not the student portal).
- **Errors:** RFC 9457 `application/problem+json` (as the platform does today).
- **Offline:** each endpoint declares read-cacheability and whether writes are queued+idempotent via
  `sync.batch`.
- **No child PII** in any request/response; learner is the pseudonymous `student_ref`.
- **Contract-first:** every new endpoint gets an OpenAPI contract in `packages/contracts/` and is
  linted in CI (as the existing three are).

---

## 1. Existing endpoints the portal reuses (built in Phase 4.1–4.2)

From `packages/contracts/learning.openapi.yaml` — already implemented, authenticated, IDOR-guarded:

| ID | Method · Path | Purpose | Used by |
| --- | --- | --- | --- |
| `learning.session.start` | POST `/v1/learning/sessions` | Start a session for the learner | Session player |
| `learning.session.next` | POST `/v1/learning/sessions/{id}:next` | Get the engine's next decision | Session player |
| `learning.session.teach` | POST `/v1/learning/sessions/{id}:teach` | Approved utterances + practice items for an objective | Session player |
| `learning.session.answer` | POST `/v1/learning/sessions/{id}:answer` | Score an answer → outcome, feedback, next decision | Session player, Homework, Assessments (formative) |
| `learning.session.end` | POST `/v1/learning/sessions/{id}:end` | End a session → summary | Session complete |
| `learning.knowledge` | GET `/v1/learning/students/{ref}/knowledge` | Mastery per objective (+ uncertainty, state) | Dashboard, Subjects, Profile mastery map |
| `learning.progress` | GET `/v1/learning/students/{ref}/progress` | Progress summary (mastery/attempts/accuracy/events) | Dashboard, Progress, Profile stats |

These cover the **core session loop** end-to-end. The gaps below are the surrounding experience.

## 2. New endpoints required

Each new endpoint: **Purpose · Method·Path · Auth · Request · Response (sketch) · Offline · Screen ·
Acceptance.** Response shapes are design sketches, not final schemas.

### 2.1 `auth.login` / `auth.refresh` (child-safe auth) — NEW

- **Purpose:** exchange a device-linked handle + simple credential (PIN/picture) for a short-lived,
  learner-scoped token; refresh silently.
- **Method·Path:** POST `/v1/auth/student/login`, POST `/v1/auth/student/refresh`.
- **Auth:** login is unauthenticated (credential-based); refresh uses the refresh token. Issues a token
  with `role: student`, `sub == student_ref`.
- **Request (login):** `{ device_handle, credential }` (no PII).
- **Response:** `{ access_token, refresh_token, expires_in, learner: { student_ref, display_name,
  grade_band, locale } }`.
- **Offline:** a valid cached session permits offline sign-in; login itself needs connectivity.
- **Screen:** Sign-in. **Acceptance:** no child PII; token strictly learner-scoped; wrong credential is
  non-punitive; provisioning is a separate guardian/mentor flow (governance-gated).

### 2.2 `dashboard.today` (aggregate) — NEW

- **Purpose:** one call that powers the whole Today screen on a slow link (avoids 5+ round-trips).
- **Method·Path:** GET `/v1/learning/students/{ref}/today`.
- **Auth:** student (own `ref`).
- **Response (sketch):** `{ next_action: { decision, objective_code, lesson_ref, est_minutes },
  today_objectives: [...], revision_due_count, mastery_summary: { mastered, in_progress, total },
  attendance: { streak_days, this_week }, achievements_new: [...], notifications_unread: int,
  offline_packages_ready: [objective_code...] }`.
- **Offline:** highly cacheable (stale-while-revalidate); Today renders from the last snapshot offline.
- **Screen:** Dashboard. **Acceptance:** `next_action` matches what `learning.session.next` would
  decide; composable from existing endpoints if the aggregate is down; no per-child ranking.

### 2.3 `learning.reviews` (revision queue) — NEW (designed in the domain model)

- **Purpose:** the due spaced-review objects for the learner.
- **Method·Path:** GET `/v1/learning/students/{ref}/reviews?due_by=now&limit=N`.
- **Auth:** student. **Response:** `{ reviews: [{ objective_code, lesson_ref, last_seen_at, due_at,
  reason }] }`, prioritized by retention risk × value, capped.
- **Offline:** cacheable; due reviews for cached packages are runnable offline.
- **Screen:** Revision queue, Dashboard `RevisionDueCard`. **Acceptance:** reflects the engine's
  `next_review_at` schedule; capped daily; retrieval-first.

### 2.4 `learning.eligibility` — NEW

- **Purpose:** which objectives are startable given prerequisites (so Subjects can lock correctly).
- **Method·Path:** GET `/v1/learning/students/{ref}/eligibility?subject=...`.
- **Auth:** student. **Response:** `{ objectives: [{ objective_code, eligible: bool, blocked_by:
  [prereq_code...], mastery_state }] }`.
- **Offline:** cacheable snapshot. **Screen:** Subjects. **Acceptance:** matches the decision engine's
  prerequisite gating; a locked objective explains *why*.

### 2.5 `learning.session.hint` — NEW (small addition to the session API)

- **Purpose:** fetch the **next authored hint** for the current item (the graduated hint ladder), so
  the client never invents hints and never reveals the answer first.
- **Method·Path:** POST `/v1/learning/sessions/{id}:hint` with `{ objective_code, item_ref,
  hint_level }`.
- **Auth:** student (own session). **Response:** `{ hint: text|null, level, exhausted: bool }` (null/
  exhausted → offer re-explanation or help).
- **Offline:** hints for a cached lesson package are available offline (they're authored content in the
  package). **Screen:** Session player. **Acceptance:** returns only **authored** hints from the
  published lesson; never the answer; capped.

### 2.6 `timetable.get` — NEW

- **Purpose:** a lightweight suggested daily/weekly plan derived from the learning plan (not free-form
  calendar entry).
- **Method·Path:** GET `/v1/learning/students/{ref}/timetable?range=week`.
- **Auth:** student. **Response:** `{ days: [{ date, blocks: [{ subject, objective_code, est_minutes
  }] }] }`. **Offline:** cacheable. **Screen:** Timetable. **Acceptance:** derived from the same plan
  the engine uses; starting a block launches the correct session.

### 2.7 `homework.list` / `homework.submit` — NEW

- **Purpose:** list assigned/auto practice; submit routes through the existing evidence path.
- **Method·Path:** GET `/v1/learning/students/{ref}/homework`; submission uses
  `learning.session.answer` (homework items are practice items → evidence).
- **Auth:** student. **Response (list):** `{ items: [{ id, subject, objective_code, due_at, status,
  est_minutes }] }`. **Offline:** listable + completable offline (cached items), queued submit.
- **Screen:** Homework. **Acceptance:** completion records evidence in the Student Model; nothing
  promotion-bearing.

### 2.8 `assessment.list` — NEW

- **Purpose:** show formative checks and mentor-supervised summative markers.
- **Method·Path:** GET `/v1/learning/students/{ref}/assessments`.
- **Auth:** student. **Response:** `{ assessments: [{ id, type: formative|summative, subject,
  available, mentor_mediated: bool }] }`. **Offline:** formative cacheable.
- **Screen:** Assessments. **Acceptance:** **no autonomous summative grading/promotion** on the
  student surface; formative via `learning.session.answer`; summative visibly mentor-gated (initiated
  only under the mentor identity-assured flow, per doc 58).

### 2.9 `achievements.list` — NEW (derived from learning events)

- **Purpose:** the learner's earned recognitions (mastery milestones, streaks, misconceptions
  cleared), computed from existing learning events (`ObjectiveMastered`, `MisconceptionCleared`,
  streaks).
- **Method·Path:** GET `/v1/learning/students/{ref}/achievements`.
- **Auth:** student. **Response:** `{ achievements: [{ id, name, description, earned_at, criteria }],
  in_progress: [...] }`. **Offline:** cacheable. **Screen:** Achievements, Dashboard strip.
- **Acceptance:** rewards effort/mastery, never speed or beating others; derivable from events (no new
  child data).

### 2.10 `notifications.list` / `notifications.markRead` — NEW

- **Purpose:** calm, capped, in-app nudges.
- **Method·Path:** GET `/v1/learning/students/{ref}/notifications`; POST `.../notifications/{id}:read`.
- **Auth:** student. **Response:** `{ notifications: [{ id, type, message, action, read, created_at }],
  unread: int }`. **Offline:** list cacheable; mark-read queued.
- **Screen:** Notifications. **Acceptance:** frequency-capped; every item maps to a safe in-app action;
  no external links; can be disabled.

### 2.11 `profile.goals.get` / `profile.goals.set` — NEW

- **Purpose:** simple, motivational, non-binding learner goals.
- **Method·Path:** GET/PUT `/v1/learning/students/{ref}/goals`.
- **Auth:** student. **Request (set):** `{ goals: [{ id?, kind: objective|subject|streak, target,
  label }] }`. **Response:** current goals + progress. **Offline:** cache + queued write.
- **Screen:** Profile. **Acceptance:** goals never gatekeep; child-settable; no comparison to others.

### 2.12 `learning.history` — NEW (self, de-identified)

- **Purpose:** the learner's own session/achievement history for the Profile timeline.
- **Method·Path:** GET `/v1/learning/students/{ref}/history?limit=N&cursor=...`.
- **Auth:** student (own only). **Response:** `{ items: [{ session_id, date, subject, objectives,
  outcome_summary }], next_cursor }`. **Offline:** last page cacheable.
- **Screen:** Profile history. **Acceptance:** own data only (IDOR); de-identified; matches recorded
  evidence.

### 2.13 `sync.batch` (existing engine, learner evidence) — EXTEND

- **Purpose:** flush the offline interaction/evidence queue; the platform already has
  `POST /v1/sync/batch` (currently a synthetic prototype). The student portal requires it wired to the
  **learning evidence** path with idempotent application.
- **Auth:** student. **Request:** `{ cursor, deltas: [{ client_event_id, type, entity_key, payload,
  client_seq }] }` (learning interactions/attempts). **Response:** per-delta result + new cursor +
  refreshed plan/mastery snapshot.
- **Offline:** this *is* the sync path. **Screen:** all (background). **Acceptance:** idempotent (dedupe
  on `client_event_id`); evidence append-only; mastery recomputed server-side; no double-counting.

## 3. Summary: existing vs new

| Category | Endpoints |
| --- | --- |
| **Existing (reuse as-is)** | session.start/next/teach/answer/end, knowledge, progress |
| **New — small additions to learning API** | session.hint, reviews, eligibility, today, timetable, homework, assessments, achievements, notifications, goals, history |
| **New — auth (child-safe)** | auth.student.login/refresh (governance-gated) |
| **Extend** | sync.batch wired to learning evidence (idempotent) |

## 4. Design rules for the new endpoints (so they don't repeat CTO findings)

- Authenticated + IDOR-guarded from day one (no `security: []`; role from token).
- OpenAPI contract per endpoint in `packages/contracts/`, CI-linted (H5), with a schema-parity guard
  if they touch persistence (H13).
- Read models where possible (aggregates like `today`, `achievements` are derived from existing
  events/mastery — minimal new storage; avoid new child-data surfaces).
- Migrations designed → reviewed → built (H3/H4) if any new tables are required (most are derived).
- No autonomous promotion/summative path on the student surface (deliberate boundary).

## 5. Governance note

`auth.student.*` and anything touching a real child is **blocked by the Phase-1.5 gate**. This document
specifies the contract so those decisions can be made against a concrete design; it is not an
authorization to build child-facing auth before the gate clears.
