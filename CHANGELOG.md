# Changelog

All notable changes to Project Taleem are recorded here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning per [VERSION.md](VERSION.md).
The local Git history is the official project history; each released version maps to an annotated tag.

## [Unreleased]

- Nothing yet. (Phase 5 not started.)

## [0.4.2] — 2026-07-21

Tag: `phase-4.2` · Wire & Harden — remediation of the CTO readiness review
([CTO_REVIEW.md](CTO_REVIEW.md)). Resolves all BLOCKER and must-fix HIGH findings; see
[PHASE_4_2_REPORT.md](PHASE_4_2_REPORT.md).

### Security

- Bearer-JWT authentication + deny-by-default PDP authorization on all Curriculum Studio and Learning
  routes; the actor's role is derived from the verified token, never the request body (B1). IDOR
  guard on learner data. Removed `actor_role` from studio request bodies + contracts.
- `load_settings()` fails closed in production on the default JWT secret or an unset database URL (H8).

### Added / Changed

- Composition root wires SQLAlchemy persistence with a request-scoped Unit of Work; the Learning API
  is now mounted in `create_app` (H1/H2). Dynamic curriculum graph from published lessons.
- `0002_learning_schema` Alembic migration for the `learning` schema; `env.py` registers both context
  metadatas (H3). Added `lesson.tags` to the ORM to match the migration (H10).
- Runtime observability for the contexts: domain metrics + correlation-tagged logs on publish,
  attempt, mastery, and session lifecycle (H9).
- CI: removed the permanently-red zero-install job (B2); added a PostgreSQL job that runs migration
  reversibility + PG-gated tests (H4); lints all OpenAPI contracts (H5); new ORM↔migration
  schema-parity test (H13).

### Fixed

- `RECURRED` misconception no longer a silent dead state — it stays active, blocks mastery, and is
  re-remediable (H7).
- Audit-immutability trigger attached to the partitioned parent so it covers all partitions (H11).
- Learning optimistic lock now engages (aggregate root dirtied on save) (H6).
- Session `end` no longer 500s from an out-of-order call and never overwrites an ESCALATED session
  (M1/M2, required by mounting the router).

### Quality

- 140 tests (SQLite + PostgreSQL-gated); 97% coverage; ruff/black/mypy(strict) green; 3 OpenAPI
  contracts valid; migrations reversible on PostgreSQL 16.

## [0.4.1] — 2026-07-21

Tag: `phase-4.1` · Commit: feature `8a7757d` + release docs.

First fully verified end-to-end educational workflow. Bundles Curriculum Studio persistence
(Phase 3.5), the Learning Intelligence Platform design (Phase 4), and the first vertical slice
(Phase 4.1).

### Added

- **Learning Intelligence Platform** (`contexts/learning`): pure domain (Student Knowledge Model with
  BKT mastery + uncertainty, half-life forgetting/spacing, pure Decision Engine with rationale,
  assessment scorer, templated no-LLM AI Teaching Runtime, session saga state machine, domain events)
  behind swappable estimator/forgetting/decision ports; application services (Knowledge, Session,
  Analytics); SQLAlchemy persistence for knowledge + immutable evidence + outbox; FastAPI router
  `/v1/learning`.
- **Vertical slice** (`vertical_slice/`): original Grade-4 Mathematics lesson "Introduction to
  Fractions" and an end-to-end runner producing a full execution trace (author → publish →
  cold-start → teach → assess → misconception detect/remediate/clear → mastery → schedule review →
  analytics → end).
- **Curriculum Studio persistence** (Phase 3.5): SQLAlchemy 2.x models + repository/Unit of Work
  replacing the in-memory adapter behind the same port; Alembic baseline migration verified
  reversible on PostgreSQL 16; four persistence design docs + review under
  `docs/10-curriculum-studio/persistence/`.
- **Learning Intelligence design** (Phase 4): seven design documents + adversarial review under
  `docs/11-learning-intelligence/`.
- OpenAPI contract `packages/contracts/learning.openapi.yaml`.
- `VERTICAL_SLICE_REPORT.md`, plus `CHANGELOG.md`, `RELEASE_NOTES.md`, `VERSION.md`.

### Changed

- `services/core-api` dependencies: added SQLAlchemy, Alembic, psycopg.

### Quality

- 124 tests passed / 2 skipped (Postgres-gated); 97% coverage (learning domain ≈98%, ≥95% bar).
- ruff, black, mypy `--strict`, redocly (3 contracts), markdownlint — all green.

### Governance

- Governance-safe: a single synthetic pseudonymous learner; no real child data. Production blockers
  (governance/safeguarding, generative-AI-tier safety, learning migration + sharding, durable
  sessions, event relay/warehouse) documented in `VERTICAL_SLICE_REPORT.md`.

## [0.3.0] — 2026-07-20

Commit: `7641b0b`.

### Added

- **Curriculum Studio** (Phase 3): AI-native curriculum authoring platform (`contexts/curriculum_studio`)
  — NCP hierarchy, full Lesson aggregate, AI teaching object, assessment items/tests, provenance gate
  (original-content enforcement), 5-gate review workflow with no-self-approval, 9 quality gates,
  immutable versioning + rollback, validator, FastAPI adapter, OpenAPI contract, authoring UI, and
  12 standards docs.

## [0.2.0] — 2026-07-20

Commits: `18f7c80`, `f8d4329`, `38e425f`, `339ff4b`.

### Added

- **Phase 1.5 tracks + Phase 2**: governance decision tracks and external-validation checklist; M1
  walking skeleton (`services/core-api` hexagonal platform core, `apps/web` PWA scaffold, contracts,
  infra skeleton, CI); full engineering verification (readiness 83 → 91); independent executive
  review + roadmap; official Pakistani curriculum resource discovery + ingestion pipeline.

## [0.1.0] — 2026-07-19

Commits: `007daa2` … `2d74a2c`.

### Added

- **Phase 1 Foundation**: complete 50-document blueprint across product, architecture,
  security/privacy, design, education, portals, engineering, and delivery clusters; ADR-0001/0002;
  external architecture review and Phase-1.5 remediation; CI green.

[Unreleased]: local — no releases pending
[0.4.1]: tag phase-4.1
[0.3.0]: commit 7641b0b
[0.2.0]: commit 18f7c80
[0.1.0]: commit 007daa2
