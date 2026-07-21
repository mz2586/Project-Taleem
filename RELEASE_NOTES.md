# Release Notes

Human-readable notes per milestone. Newest first. Detailed change lists live in
[CHANGELOG.md](CHANGELOG.md); versions and tags in [VERSION.md](VERSION.md). Maintained locally —
this repository has no remote and the local Git history is authoritative.

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
