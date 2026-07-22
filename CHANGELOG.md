# Changelog

All notable changes to Project Taleem are recorded here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning per [VERSION.md](VERSION.md).
The local Git history is the official project history; each released version maps to an annotated tag.

## [Unreleased]

- Nothing pending.

## [0.7.0] — 2026-07-22

Tag: `phase-7` · Curriculum Production System + Grade 4 complete. See
[PHASE_7_REPORT.md](PHASE_7_REPORT.md). Documentation + curriculum content only — no architecture
redesign; all existing curriculum, learning, offline, student, guardian, and assessment components
are reused.

### Added

- **Curriculum production system** (the system to produce curriculum at scale, over the existing
  platform): `CURRICULUM_FRAMEWORK.md` (KG–10 production skeleton), `CONTENT_PRODUCTION_PIPELINE.md`
  (the Draft→Educational→Quality→Child-Safety→Publication→Offline-Packaging flow mapped to the
  existing Curriculum Studio `Workflow` + `OfflinePackageService`), `CONTENT_STANDARDS.md` (8
  standards), `QUALITY_ASSURANCE_CHECKLISTS.md` (6 validation checklists).
- **Grade 4 complete curriculum package** under `curriculum/grade-4/`: `GRADE4_PACKAGE.md` (index) +
  `URDU.md`, `ENGLISH.md`, `GENERAL_SCIENCE.md`, `SOCIAL_STUDIES.md`, `ISLAMIAT_ETHICS.md` (dual
  track); Mathematics reused from Phase 6.1. ~123 objectives across all core subjects, each with
  units, assessments, revision, homework, a term project, misconception library, and guides. All
  `authored-original`, `[RE-EXPRESSED]`, child-safe, Urdu-first; sensitive subjects routed through
  the subject-expert + child-safety review gates.

### Quality

- No source code changed. Gates confirm the platform is unaffected: ruff/black/mypy(strict) green;
  pytest 159 passed, 6 skipped; OpenAPI valid; frontend tsc clean, 78 vitest tests, build green;
  markdownlint 0 errors on all Phase 7 docs.

## [0.6.4] — 2026-07-22

Tag: `phase-6.2C-1` · Offline Engineering Hardening. See [PHASE_6_2C_1_REPORT.md](PHASE_6_2C_1_REPORT.md).
Gate-free subset of the approved [PHASE_6_2C_IMPLEMENTATION_PLAN.md](PHASE_6_2C_IMPLEMENTATION_PLAN.md);
no governance-gated work.

### Added

- **Ed25519 package signing** (pure-stdlib RFC 8032 signer `platform/ed25519.py`; `package_signer.py`;
  optional `signer` on `build_manifest`; `GET /v1/offline/signing-keys`). The private seed never leaves
  the server; production boot fails closed on the default seed. Signs a canonicalization-free payload
  `${package_id}\n${version}\n${content_hash}` (downgrade-resistant).
- **Client signature verification** (`apps/web/lib/offline/signature.ts` via WebCrypto Ed25519;
  `DownloadManager` verifies before trusting bytes; `requireSignature` option; `signature_ok` recorded).
  A **locked cross-language interop vector** is asserted in both the backend and frontend suites.
- **Chaos / fault-injection framework** (`chaos.ts`: `FaultyStore`, `faultyPostBatch`) + chaos tests.
- **Cache purge / de-enrolment mechanism** (`purge.ts` `PurgeService`; `syncClient` honors an optional
  server `purge` signal). Mechanism only — the trigger is governance-gated.
- **Diagnostics enhancements** (signature/integrity/eviction/purge counters; old-shape hydration; still
  local-only).
- **LRU cache eviction** (`DownloadManager.ensureSpace`/`evictLRU` over disposable packages; never
  evicts the un-synced queue/checkpoints).

### Changed

- `_assert_production_safe` also rejects the built-in default offline signing seed in production;
  `test_hardening_4_2` updated accordingly. Manifest gains optional `signature`/`signing_key_id`;
  `BatchResult` gains optional `purge` (both backward-compatible).

### Deferred (still gated)

- Device-bound offline auth token (M-Gov + FD-14), crisis-flag routing (M-Safe), consent-gated
  telemetry upload, at-rest encryption production keys (FD-14), residency pinning (FD-02).

### Quality

- Backend: 159 passed, 6 skipped (PostgreSQL-gated); ruff/black/mypy(strict) green; OpenAPI valid.
  Frontend: `tsc` clean, **78 vitest tests** (incl. Python↔WebCrypto signing interop + chaos), build green.

## [0.6.3] — 2026-07-22

Tag: `phase-6.2B` · Offline Synchronization Engine. See [PHASE_6_2B_REPORT.md](PHASE_6_2B_REPORT.md).

### Added

- **Durable sync consumer** (closes gap G3): `SyncEvidenceConsumer` grades an offline
  `attempt.submitted` delta session-lessly (existing `evaluate` scorer) and records durable
  `AssessmentEvidence` via `LearningUnitOfWork` — **idempotent by the client `evidence_id`** (the
  evidence table is the ledger, so a replay after a server restart is a `DUPLICATE`). Summative items
  are never auto-graded by sync.
- **`DurableSyncCoordinator`** routes `POST /v1/sync/batch` by delta type: attempts → durable sink;
  progress / lesson.completed / preference → the existing in-memory conflict policy. Added
  `SyncEngine.apply(delta)`.
- **Frontend sync engine** (`apps/web/lib/offline/`): durable `syncQueue` (IndexedDB v2 `evidence_queue`
  store), `syncClient` drain (idempotent status handling, keep-and-retry on offline, dead-letter,
  `backoffMs` full-jitter, cursor), `backgroundSync` (Background Sync + online/visibility auto-drain),
  `reconcile` (idempotent session reconciliation + resume), local `diagnostics`. Service worker `sync`
  handler; `syncApi.batch`; `SyncStatusBadge` + `useSyncStatus` wired into `AppShell`.

### Changed

- `test_integration.py::TestSyncEndpoint` now exercises the still-in-memory delta types, since
  `attempt.submitted` routes to the durable consumer (covered by `tests/test_sync_evidence.py`).

### Deferred (not in 6.2B)

- Offline auth, device-bound credentials, governance-gated identity, child-safety escalation,
  consent-gated telemetry upload, production deployment changes (6.2C+).

### Quality

- Backend: 147 passed, 6 skipped (PostgreSQL-gated); ruff/black/mypy(strict) green; OpenAPI valid.
  Frontend: `tsc` clean, **52 vitest tests** (incl. crash-recovery + 120-attempt long-session over
  fake-indexeddb), `next build` green.

## [0.6.2] — 2026-07-22

Tag: `phase-6.2A` · Offline-Lite Implementation. See [PHASE_6_2A_REPORT.md](PHASE_6_2A_REPORT.md).

### Added

- **Backend offline package service** (derived, C0 curriculum — no new tables, no child data):
  pure builder `contexts/learning/domain/offline_package.py` (content-hashed manifests; child-safe
  content with **no answer keys**; `fits_in_quota` pre-flight), `OfflinePackageService`, and
  `GET /v1/offline/packages` + `GET /v1/offline/packages/{lesson_id}` (auth + read `learning.knowledge`,
  no new PDP rule). Contract `packages/contracts/offline.openapi.yaml`.
- **Frontend offline-lite library** `apps/web/lib/offline/`: IndexedDB store (`taleem-offline`),
  download manager (verify + quota + atomic install), local progress persistence, session checkpoints +
  resume, offline read cache, connectivity detection, client `uuid7`, and cache-versioning helpers.
- **Service worker** upgraded (`apps/web/public/sw.js`): versioned shell + runtime caches; offline
  dashboard + lesson loading via network-first-with-cache-fallback; old caches purged on activate;
  registered via `ServiceWorkerRegister`. `OfflineBadge` now driven by `watchConnectivity`.

### Deferred (not in 6.2A)

- Background sync, conflict resolution, offline auth, sync batching, durable session replay, telemetry
  upload, governance-gated features (6.2B/6.2C).

### Quality

- Backend: 146 passed, 5 skipped (PostgreSQL-gated); ruff/black/mypy(strict) green; 5 OpenAPI contracts
  valid. Frontend: `tsc` clean, **31 vitest tests** (incl. fake-indexeddb offline simulation),
  `next build` green.

## [0.5.5] — 2026-07-21

Tag: `phase-5.5` · Student Platform Backend APIs. See [PHASE_5_5_REPORT.md](PHASE_5_5_REPORT.md).

### Added

- Student-facing query APIs (all **derived** from existing learning data — no new child-data tables):
  `GET /v1/learning/students/{ref}/{today,homework,assessments,reviews,timetable,notifications,
  achievements,history,recommendations}`, `POST …/notifications/{id}:read`, and
  `POST /v1/learning/sessions/{id}:hint` (authored graduated hints, never the answer).
- `StudentReadModel` port + SQLAlchemy adapter, `StudentQueryService`, and `build_student_router`,
  wired into the composition root behind bearer-JWT + PDP, IDOR-guarded.
- `LessonView` projection extended with homework + assessment items (approved content only).
- `packages/contracts/student.openapi.yaml` (CI-linted with the other contracts).
- `tests/test_student_api.py` — SQLite + PostgreSQL-gated integration (seed → drive a real session to
  mastery → exercise every endpoint + auth/IDOR).

### Quality

- 142 tests on PostgreSQL (140 + 2 skipped on SQLite), 97% coverage; ruff/black/mypy(strict) green;
  4 OpenAPI contracts valid.

## [0.5.0] — 2026-07-21

Phase 5 — Student Experience. (Design docs + governance-safe portal core scaffold; untagged.)

### Added

- `docs/12-student-experience/` — full student-experience design (experience, architecture, UI flow,
  API requirements, component catalog).
- `apps/web/app/student/*` — governance-safe portal core (Today, Session, Profile, Progress) over the
  real `/v1/learning` API with a synthetic learner + dev-stub token; no child identity/PII.

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
