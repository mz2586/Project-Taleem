# Phase 5.5 — Student Platform Backend APIs — Completion Report

Scope: implement, test, and document the backend APIs the approved Student Experience needs
(`docs/12-student-experience/STUDENT_API_REQUIREMENTS.md`). No production child identity, no
governance-gated features, no offline subsystem, no frontend features. Date: 2026-07-21.
Status: **complete — all quality gates green (SQLite + PostgreSQL).**

## 1. Approach: derived read models (no new child-data tables)

Every requested surface is **derived** from data the `learning` context already persists — the
Student Knowledge Model (`objective_mastery`), immutable `assessment_evidence`, and the
`learning_outbox` — composed with the published-curriculum read model. This means **no new
child-data storage** was introduced, keeping the work governance-safe, and it extends the existing
architecture without redesigning any completed context.

New pieces (Clean Architecture / DDD preserved):

- **`StudentReadModel` port** + `SqlAlchemyStudentReadModel` adapter — pure read queries over the
  learner's persisted data (objective states, evidence, knowledge events).
- **`StudentQueryService`** (application) — composes the read model + curriculum read model into the
  response shapes; reads only.
- **`build_student_router`** (adapter) — the `/v1/learning/students/{ref}/*` query endpoints.
- **`:hint`** added to the existing session router; **`LessonView`** projection extended with
  homework + assessment items (approved content only).
- All wired into the composition root (`main.py`), behind the existing bearer-JWT + PDP auth,
  IDOR-guarded.

## 2. Scope → endpoint → test (all 11 areas)

| Scope item | Endpoint | Source (derived from) |
| --- | --- | --- |
| Homework | `GET /v1/learning/students/{ref}/homework` | lesson `homework` items + evidence (done/todo) |
| Assessments | `GET …/assessments` | lesson `assessment` blueprint (summative flagged mentor-mediated) |
| Revision queue | `GET …/reviews` | objective states `needs_review`/`at_risk` + `next_review_at`, risk-ordered |
| Timetable | `GET …/timetable` | published-curriculum graph + mastery states |
| Notifications | `GET …/notifications`, `POST …/notifications/{id}:read` | due reviews + `ObjectiveMastered` events |
| Progress | `GET …/today` (aggregate) + existing `…/progress` | states + recommendations |
| Achievements | `GET …/achievements` | `ObjectiveMastered` / `MisconceptionCleared` events |
| Lesson history | `GET …/history` (`lessons`) | evidence grouped by objective |
| Session history | `GET …/history` (`sessions`) | evidence grouped by session |
| Hint requests | `POST /v1/learning/sessions/{id}:hint` | authored hint ladder from the published lesson |
| Learning recommendations | `GET …/recommendations` | misconceptions → reviews → next unlearned objective |

Every endpoint: authenticated (bearer JWT), authorized (`read learning.knowledge`), and IDOR-guarded
(a learner reaches only their own data; mentors may read any). The student surface exposes **no**
autonomous promotion/summative grading (summative is flagged mentor-mediated) — a deliberate boundary.

## 3. Tests

`tests/test_student_api.py` is a full integration test over the composed app: it seeds a published
lesson (the Grade-4 Fractions lesson), drives a **real learning session to mastery** (generating
evidence + mastery + events), then exercises **every** derived endpoint and asserts the results,
plus auth (401) and IDOR (403) guards.

- `test_student_apis_over_sqlite` — over the in-memory SQLite composition (always runs).
- `test_student_apis_over_postgres` — **PostgreSQL-gated** (`CS_DATABASE_URL`): runs the Alembic
  migrations (down→up), then the same flow over the real migrated schema.

## 4. Final quality gate

| Gate | Result |
| --- | --- |
| Ruff (lint) | ✅ PASS |
| Black (format) | ✅ PASS |
| Mypy `--strict` | ✅ PASS |
| Pytest (SQLite) | ✅ 140 passed, 2 skipped (PG-gated) |
| Pytest (PostgreSQL 16) | ✅ **142 passed, 0 skipped** |
| Coverage | ✅ **97%** (new modules: read model 100%, query service 91%, router 95%) |
| OpenAPI contracts (redocly, pinned) | ✅ 4/4 valid (added `student.openapi.yaml`) |

## 5. Deliverables

- Implemented backend APIs (11 surfaces + `:hint`), wired into `main.py`.
- `packages/contracts/student.openapi.yaml` (CI-linted with the others).
- `tests/test_student_api.py` (SQLite + PostgreSQL integration).
- This report.

## 6. Explicitly not done (per scope)

- No offline synchronization subsystem.
- No production child authentication / identity (dev-stub auth only, unchanged).
- No additional frontend features (the portal's existing screens can adopt these APIs later —
  e.g. `today`, `reviews`, `:hint` — but that is frontend work, deferred).
- Notification read-state is tracked client-side in this phase (accepted no-op server-side) to avoid
  introducing a new child-data table.

## 7. Notes for the next milestone

- The frontend Dashboard/Session can now consume `…/today` (one call) and `:hint` (graduated hints),
  replacing the current multi-call composition — a small frontend follow-up.
- If persistent notification read-state or richer timetable scheduling is needed, that is the first
  case for a small new store (design → review → build, as usual).
- The derived approach keeps the student surface storage-free and governance-safe; any move to real
  learners remains blocked by the Phase-1.5 governance gate.
