# Release Notes

Human-readable notes per milestone. Newest first. Detailed change lists live in
[CHANGELOG.md](CHANGELOG.md); versions and tags in [VERSION.md](VERSION.md). Maintained locally —
this repository has no remote and the local Git history is authoritative.

---

## 0.6.3 — Phase 6.2B: Offline Synchronization Engine (2026-07-22)

Tag: `phase-6.2B`

The other half of offline: what a child does with no network now **syncs safely** when they reconnect.

### Highlights

- **Offline attempts become real evidence.** A queued offline answer is graded server-side and
  recorded as durable `AssessmentEvidence` through the same path a live session uses — reusing the
  existing sync contract, `SyncDelta`, `client_event_id`, and `LearningUnitOfWork`. No new child-data
  table; no domain redesign.
- **Exactly-once, always.** Every attempt carries a client `evidence_id`; the server dedupes on it, so
  reconnect-retries, batch replays, reconcile re-queues, and even a **server restart** all collapse to
  a harmless duplicate. No data loss, no double-count.
- **It resumes itself.** A durable IndexedDB queue survives crashes; on reconnect the app drains
  automatically (Background Sync + online/visibility), retries with jittered backoff, dead-letters the
  truly stuck, reconciles a long offline session, and shows a calm live status.
- **Safety held.** A summative item is never auto-graded by sync (mentor-mediated). No offline auth,
  no consent-gated telemetry — those are later.

### Quality

- Backend: 147 passed, 6 skipped; ruff/black/mypy(strict) green; OpenAPI valid.
- Frontend: `tsc` clean; **52 vitest tests** including crash-recovery and a 120-attempt long offline
  session over fake-indexeddb; `next build` green. See `PHASE_6_2B_REPORT.md`.

---

## 0.6.2 — Phase 6.2A: Offline-Lite (2026-07-22)

Tag: `phase-6.2A`

The first slice of the offline subsystem: a child can open the app, view their dashboard, and load a
downloaded lesson **with no network** — and their progress is saved on-device and resumable.

### Highlights

- **Offline packages.** A published lesson builds into a content-hashed package the app downloads,
  verifies (SHA-256 against the manifest), and caches in IndexedDB. Packages ship the teaching + attempt
  surface but **never answer keys** — a device cannot reveal an answer offline.
- **Offline dashboard + lessons.** A versioned service worker serves the app shell and the student read
  APIs from cache when offline; the download manager renders cached lessons directly.
- **Local progress + resume.** Progress events and session checkpoints persist on-device (IndexedDB), so
  an interrupted lesson resumes where it left off.
- **Automatic cache versioning.** Content changes change the hash, so stale caches are detected and
  refreshed; old shell caches are purged on activate.
- **Honest, safe by design.** No background sync, no offline auth, no on-device grading, no generative
  AI offline, no child PII — only the pseudonymous `student_ref`. Those belong to 6.2B/6.2C.

### Quality

- Backend: 146 passed, 5 skipped; ruff/black/mypy(strict) green; 5 OpenAPI contracts valid.
- Frontend: `tsc` clean; **31 vitest tests** including a fake-indexeddb offline-browser simulation;
  `next build` green. See `PHASE_6_2A_REPORT.md`.

---

## 0.5.5 — Phase 5.5: Student Platform Backend APIs (2026-07-21)

Tag: `phase-5.5`

The backend the approved Student Experience needs — implemented as **derived read models** over data
the learning platform already stores, so **no new child-data tables** were added.

### Highlights

- Eleven student-facing surfaces went live behind the existing auth: the dashboard aggregate
  (`today`), homework, assessments, revision queue, timetable, notifications, achievements, session +
  lesson history, learning recommendations, and graduated `:hint` requests.
- All authenticated, authorized, and **IDOR-guarded** — a learner reaches only their own data; the
  student surface never exposes autonomous promotion/summative grading.
- A full integration test seeds a published lesson, drives a real session to mastery, and exercises
  every endpoint on both SQLite and PostgreSQL.

### Quality

- 142 tests on PostgreSQL, 97% coverage; ruff/black/mypy(strict) green; 4 OpenAPI contracts valid.
  See `PHASE_5_5_REPORT.md`.

### Scope

Governance-safe. No offline subsystem, no production child auth, no new frontend features.

---

## 0.5.0 — Phase 5: Student Experience (2026-07-21)

Complete student-experience design (`docs/12-student-experience/`) plus the governance-safe portal
core scaffold (`apps/web/app/student/*`) — Today, Session, Profile, Progress over the real
`/v1/learning` API with a synthetic learner and dev-stub token. No child identity, PII, or deployment.

---

## 0.4.2 — Phase 4.2: Wire & Harden (2026-07-21)

Tag: `phase-4.2`

Remediation of the CTO readiness review — the foundation is now production-shaped, not just
green-in-isolation.

### Highlights

- **Security closed.** Every Curriculum Studio and Learning route now requires a verified bearer
  token; the actor's role comes from the token, not the request body. Learner data is IDOR-guarded,
  and production refuses to boot with the default JWT secret or no database.
- **Actually wired.** The Learning API is mounted in the running app, and the app persists to
  SQLAlchemy (with a per-request Unit of Work) instead of the old in-memory store.
- **Migrations & CI.** A learning-schema migration was added, both schemas are verified reversible on
  PostgreSQL, and CI now runs migrations + PostgreSQL-gated tests, lints every OpenAPI contract, and
  guards ORM↔migration schema parity.
- **Defects fixed.** The `RECURRED` misconception dead-state, the audit-immutability trigger on the
  wrong partition, and the dormant learning optimistic lock are all fixed. Baseline runtime
  observability (domain metrics + correlation) was added to the contexts.

### Quality

- 140 tests (SQLite + PostgreSQL-gated); 97% coverage; ruff/black/mypy(strict), redocly, migrations
  all green. See `PHASE_4_2_REPORT.md` and `CTO_REVIEW.md`.

### Scope

No new product features, no portal work, no architecture redesign. MEDIUM/LOW review items not
required by a BLOCKER/HIGH fix remain tracked for a later pass.

---

## 0.4.1 — Phase 4.1: First end-to-end Learning vertical slice (2026-07-21)

Tag: `phase-4.1`

This milestone proves the entire platform architecture works together, end to end, on one lesson.

### Highlights

- **A real educational workflow runs start to finish.** An original Grade-4 Mathematics lesson
  ("Introduction to Fractions") is authored, reviewed through five gates, and published by Curriculum
  Studio; the Learning Intelligence Platform then loads a student, decides to teach, delivers the
  lesson via the templated AI Teaching Runtime, scores answers, detects and remediates a
  misconception, advances the learner to mastery, schedules revision, records analytics, and closes
  the session — with a captured execution trace of every step.
- **The learning "brain" is evidence-based and swappable.** Mastery (Bayesian Knowledge Tracing with
  uncertainty), forgetting/spacing (half-life), and the decision policy are pure, deterministic, and
  sit behind ports so the pedagogy can evolve without touching the rest of the system.
- **No mocks.** Curriculum Studio and the Student Knowledge Model persist to real SQLAlchemy stores;
  the AI runtime is the real templated (no-LLM) tier, in-scope by construction.

### Quality

- 124 tests pass / 2 skipped (Postgres-gated); 97% coverage (learning domain ≈98%).
- ruff, black, mypy `--strict`, OpenAPI (redocly, 3 contracts), markdownlint — all green.

### For maintainers

- Run the slice: `cd services/core-api && PYTHONPATH=src python -m taleem_core.vertical_slice.runner`
- Full report with trace, metrics, gaps, and production blockers: `VERTICAL_SLICE_REPORT.md`.

### Not included / blockers before scaling

Governance-safe only (synthetic pseudonymous learner; no real child data). Before any child-facing
use: Phase-1.5 governance and safeguarding, generative-AI-tier safety, the learning-store Alembic
migration and sharding, durable sessions, and the event relay + analytics warehouse. See the report.

---

## 0.3.0 — Phase 3: Curriculum Studio (2026-07-20)

The AI-native curriculum authoring platform: hierarchy, Lesson aggregate, AI teaching objects,
assessments, provenance/original-content enforcement, 5-gate review workflow, 9 quality gates,
immutable versioning, and the authoring API/UI.

## 0.2.0 — Phase 1.5 / 2: Governance tracks + M1 walking skeleton (2026-07-20)

Governance decision tracks and external validation; the M1 hexagonal platform skeleton; full
engineering verification; independent executive review + roadmap; and curriculum resource discovery.

## 0.1.0 — Phase 1: Foundation blueprint (2026-07-19)

The complete 50-document blueprint (product, architecture, security/privacy, design, education,
portals, engineering, delivery) plus ADRs and the external architecture review.
