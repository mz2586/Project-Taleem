# Release Notes

Human-readable notes per milestone. Newest first. Detailed change lists live in
[CHANGELOG.md](CHANGELOG.md); versions and tags in [VERSION.md](VERSION.md). Maintained locally —
this repository has no remote and the local Git history is authoritative.

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
