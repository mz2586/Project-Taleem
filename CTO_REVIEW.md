# CTO Readiness Review — Milestone M1 (post Phase 4.1)

Reviewer: acting CTO / Principal Engineer. Type: **review only — no code modified.** Date: 2026-07-21.
Repository: local `project-taleem`, HEAD `7987e22` (tag `phase-4.1`), working tree clean.

Method: four independent read-only subsystem audits (build/CI/DX, Curriculum Studio + persistence,
Learning Intelligence + slice, APIs/security/observability/testing/frontend), each producing
file-cited findings, then cross-checked, de-duplicated, and prioritized here. Claims were verified by
reading code and running the suites; nothing was taken on trust from prior reports.

Effort legend: **S** ≤ half a day · **M** ≈ 0.5–2 days · **L** > 2 days.
Severity: **BLOCKER** (integrity/security/CI failure; blocks Phase 5) · **HIGH** (must resolve before
Phase 5 implementation) · **MEDIUM** (fix during hardening) · **LOW** (hygiene).

---

## 1. Executive summary

Project Taleem is, at the design and domain level, **genuinely strong**: a clean
hexagonal/DDD architecture with verified domain purity in both bounded contexts, swappable
learning-science ports, immutable curriculum versioning, a transactional outbox, and an exemplary
"design → adversarial review → build" discipline. The Phase-4.1 vertical slice is **real, not mocked** —
it exercises the actual persistence, scorer, estimator, forgetting, and decision engine end to end.

The dominant, repeated finding across all four audits is a single systemic theme:

> **A gap between "built and green in isolation" and "wired into the deployable and guarded by CI."**

Concretely: the SQLAlchemy persistence exists but the running app still mounts the **in-memory**
studio repository; the entire Learning API is **never mounted** in `create_app()` and "works" only in
tests that build their own app; there is **no authentication** on the one business router that is
mounted (privilege is read from the request body); a **CI job is red on every commit**; CI never runs
the Alembic migration or any PostgreSQL-gated test; and two-thirds of the OpenAPI contracts are
unlinted. There are also **two genuine correctness defects** in the learning engine (a `RECURRED`
misconception dead-state; an audit-immutability trigger attached to the wrong partition) and a
concurrency gap (optimistic locking does not detect cross-request lost updates).

None of this is architectural rot — it is **integration and hardening debt** that accumulated because
Phase 3/4 shipped subsystems faster than the composition root, CI, and docs were updated to match.
The correct response is a short, focused **Phase 4.2 "Wire & Harden"** milestone before any Phase 5
(Student Experience) implementation begins.

**Total findings:** 2 BLOCKER · 11 HIGH · 14 MEDIUM · 14 LOW.

---

## 2. Health scores

| Dimension | Score | One-line rationale |
| --- | --- | --- |
| **Repository health** | **72 / 100** | Strong quality gate + clean tree + gitignore, but a permanently-red CI job, stale docs, uv/Make mismatch, demo in the wheel, and root-report clutter. |
| **Architecture health** | **82 / 100** | Clean hexagonal/DDD with verified domain purity and good ports; dinged by application→infrastructure leaks, composition-root lag, optimistic-lock gaps, and base.py duplication. |
| **Engineering maturity** | **70 / 100** | 124 tests / 97% coverage, strict typing, adversarial reviews — offset by a red CI job, no cross-context/integration/load tests, ORM↔migration drift with no guard, and absent runtime observability. |
| **Educational platform readiness** | **60 / 100** | Evidence-based pedagogy is implemented and swappable, but two correctness defects in the misconception model, a naive uncertainty counter, one lesson only, and no data-validation of the models. |
| **Production readiness** | **38 / 100** | Pre-production by design (governance-gated) *and* by state: no auth wired, learning API unmounted, in-memory repo in the app, no learning migration, no PG in CI, no observability, in-memory sessions, offline unexercised, zero load testing. |

Scores are calibrated against a world-class production bar (the project's own standard), not against
"typical for this stage." At this stage the design scores deserve to be high; the production score is
honestly low and should be.

---

## 3. BLOCKER findings

| ID | Finding | Evidence | Why it matters / Risk | Fix | Effort | Pre-P5 |
| --- | --- | --- | --- | --- | --- | --- |
| **B1** | **No authN/authZ on the studio router; privilege is read from the request body.** | `curriculum_studio/adapters/api.py` (no `Depends`); `actor_role` taken from `SubmitIn/ReviewIn/PublishIn/RollbackIn`; JWT+PDP wired only on `/v1/skeleton/protected` (`main.py`); all contract ops carry `security: []`. | Any anonymous caller can create → submit → self-approve → publish → rollback curriculum by asserting `actor_role="curriculum_architect"`. The "no-self-approval / 5-gate" guarantee is bypassable. Once learning mounts, IDOR on `/students/{ref}/knowledge`. | Add a `require_claims` + `pdp.authorize(role, action, resource)` dependency to both routers; derive `actor_role` from verified JWT claims, never the body. | M | **Yes** |
| **B2** | **CI `core-tests` job fails on every commit; `make test-core` is also broken.** | `.github/workflows/ci.yml` runs `python -m unittest discover` with no deps installed; 7 modules now import sqlalchemy/fastapi/pytest → `FAILED (errors=7)`. `Makefile` `test_[!i]*.py` pattern includes the same modules. | A permanently-red required check either blocks all merges or trains the team to ignore red CI — destroying the safety net. The "zero-install stdlib smoke" contract is silently false. | Delete `core-tests` (redundant with `core-quality`) or restrict its pattern to genuinely framework-free modules; fix the Makefile pattern. | S | **Yes** |

---

## 4. HIGH findings

| ID | Finding | Evidence | Why it matters / Risk | Fix | Effort | Pre-P5 |
| --- | --- | --- | --- | --- | --- | --- |
| **H1** | **Learning router never mounted in `create_app()`.** | `main.py` imports/mounts only `build_studio_router`; 0 hits for "learning". `test_learning_api.py` builds its own `FastAPI()`. | Phase 4's entire API surface is unreachable in the deployable; `/openapi.json` omits it; contract-vs-runtime drift that tests don't catch. "Done" work no client can call. | Wire `LearningApiDeps` into `create_app`; add an integration test asserting learning paths in `create_app().openapi()`. | M | Yes |
| **H2** | **The mounted studio app uses the in-memory repository — the SQL persistence is not wired in.** | `main.py`: `CurriculumStudioService(InMemoryLessonRepository(), RecordingPublishPort())`. | Versioning, audit hash-chain, and the outbox never persist in the running app — the persistence layer's guarantees exist only in tests. Correlation IDs never reach a write. | Wire the SQLAlchemy repository + UoW (+ engine/session lifecycle) into `create_app` behind config. | M | Yes |
| **H3** | **No Alembic migration for the `learning` schema; `env.py` can't autogenerate one.** | `alembic/versions/` has only `0001_initial_curriculum_studio`; `env.py` sets `target_metadata` from curriculum_studio only — never imports `LearningBase`. | In production Postgres the learning tables are never created; `--autogenerate` silently misses them. Blocks storing real learners. | Author the learning migration; register `LearningBase.metadata` (combined target) in `env.py`. | M | Yes |
| **H4** | **CI never runs the Alembic migration or any Postgres-gated test.** | `core-quality` has no Postgres service / `CS_DATABASE_URL`; the 2 migration-reversibility + FTS tests skip. | The "authoritative production schema" (migration up/down + `search_vector` trigger) is never exercised by CI — migration rot goes undetected. | Add a `postgres:16` CI service; run pytest with `CS_DATABASE_URL` set. | M | Yes |
| **H5** | **Redocly lints only 1 of 3 OpenAPI contracts.** | `ci.yml` lints `openapi.yaml` only; `curriculum-studio` + `learning` contracts unlinted. | New API contracts are ungated — drift/invalid schemas ship unnoticed. | Glob `packages/contracts/*.yaml`. | S | Yes |
| **H6** | **Optimistic locking does not detect cross-request lost updates.** | Curriculum: `save()` dirties the root so the ORM mechanism works for *overlapping* transactions, but the domain `Lesson` carries no `lock_version` and `save()` re-reads fresh — the version the user saw never re-enters a `WHERE`. Learning: `StudentKnowledge` root is never dirtied (only child evidence rows), so its lock is dormant. | Silent lost updates under concurrent authoring/review or multi-device learning. The advertised concurrency guarantee is partly illusory. | Round-trip the read `lock_version` through the domain/DTO into `save()`; for learning, touch the root on any child change; add a conflict test driven through the service, not raw ORM. | M | Yes |
| **H7** | **`RECURRED` misconception is a silent dead state (genuine defect, reproduced).** | `knowledge.py` `is_active` returns True only for SUSPECTED/CONFIRMED/BEING_REMEDIATED; a cleared-then-re-hit misconception becomes `RECURRED` → `is_active=False`, dropped from `has_confirmed`/`active`, never re-cleared, under-counted. | Recurrence (remediation failed) is the *most* important pedagogical signal and the engine discards it — it will never re-remediate and analytics under-reports. | Include `RECURRED` in `is_active` at ≥ CONFIRMED urgency; emit a detection event. | S | Yes |
| **H8** | **Production can boot with the default dev JWT secret.** | `config.py` defaults `jwt_dev_secret="dev-only-not-secret"`; `is_production` defined but unused; HS256 symmetric. | Shipping without setting the secret = trivially forgeable tokens. | In `load_settings()` raise if `is_production` and secret is default; reject HS256 in prod (per the file's own FD-14 note). | S | Yes |
| **H9** | **Runtime observability is absent from all context code.** | `StructuredLogger`, metrics `registry()`, `tracing.span()` are used only in `main.py` HTTP middleware; `span()` is called nowhere in `src/`. No service/repository emits logs/metrics/spans; `correlation_id` is bound at the HTTP edge but not propagated into sessions/outbox/audit. | No telemetry on rule violations, decisions, mastery updates, or session sagas — undebuggable in production; no SLOs possible. | Instrument application services with spans + domain metrics/logs; thread `correlation_id` through services → UoW → outbox/audit. | M | No (strongly advised) |
| **H10** | **ORM-vs-migration drift, with no automated parity check.** | Tests build SQLite from `metadata.create_all`; the PG migration runs only when `CS_DATABASE_URL` set (skipped in CI). Concrete drift: `lesson.tags text[]` + its GIN index + FTS weight-'B' exist in the migration but the column is absent from `LessonRow` and never written (dead search signal); `ck_lesson_provenance`/`ck_media_provenance` CHECKs are PG-only (copyright invariant untestable on SQLite); index/`DESC`/partial differences. | Two schemas (test vs prod) silently diverge; a documented search signal never works; drift compounds with every future migration. | Add a CI test that reflects ORM metadata vs the migration and asserts parity; reconcile `tags` and the CHECK constraints. **Highest-leverage single fix.** | M | Yes |
| **H11** | **Audit-immutability trigger is on the leaf partition, not the parent (genuine defect).** | `0001_initial`: `trg_audit_immutable` is attached to `audit_log_default`; Postgres row triggers don't cascade from a leaf, so every future monthly partition is UPDATE/DELETE-able. | The append-only / tamper-evidence guarantee (a child-safety / governance control) is unenforced for most partitions. | Attach the trigger to the partitioned parent `audit_log` (PG13+). | S | Yes |

---

## 5. MEDIUM findings

| ID | Finding | Evidence | Why it matters / Risk | Fix | Effort | Pre-P5 |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | `end` from TEACHING raises `SessionError` → HTTP 500 (reproduced). | `session_service.complete_objective` walks TEACHING→ASSESSING (illegal); `api.py :end` calls it from teaching/interacting. | Unhandled 500 on a normal out-of-order client call. | Guard `complete_objective` to run only from INTERACTING (or make end tolerant). | S | No |
| M2 | `end()` overrides ESCALATED and reports SessionCompleted; `ENDED_SAFELY` path is dead. | `session.py end()` has no guard; `session_service.end` calls it for any non-RECORDING state. | A safeguarding escalation can be overwritten to a normal completion — safety/analytics integrity. | Refuse `end()` from ESCALATED/terminal; wire the safe-end path. | S | No (flag for safety review) |
| M3 | Write model round-trips full evidence history every attempt (N+1 / unbounded). | `learning repository.get()` hydrates all evidence; `save()` re-queries all evidence ids; `submit_answer` reloads the aggregate a third time. | O(n) memory + queries per interaction in the learner's lifetime — will not scale. | Use a write model that doesn't hydrate evidence; append without a full id scan; return post-state from `record_attempt`. | M | Yes (before learners accumulate history) |
| M4 | Application layer imports infrastructure. | `knowledge_service`/`session_service`/`analytics` import the concrete `LearningUnitOfWork`; `analytics` runs raw `select()` on ORM models inside `application/`. | Contradicts the stated architecture; couples application to a concrete adapter; analytics is an infra query object in the wrong layer. | Define a `UnitOfWork` Protocol port; move analytics SQL behind an adapter port. | M | No |
| M5 | Misconception "simplified clearance" is too lenient. | `knowledge.py`: one `correct` clears all active misconceptions on the objective (incl. CONFIRMED), no BEING_REMEDIATED stage, no multi-correct requirement. | A lucky guess (p_guess 0.20) or an unrelated correct item clears a real misconception — false mastery. | Require ≥2 consecutive corrects (or remediation-context) and clear only misconceptions the item exercised. Tie to H7. | M | Recommended |
| M6 | Sessions in-memory but documented "durable/resumable"; the tutoring turn trace is lost on restart. | `InMemorySessionRepository`; `session.py` docstring claims durable saga. | Only numeric evidence + outbox persist; SessionStarted/Completed reference a saga with no durable record. Fine for the slice; not a platform claim. | Persist the session aggregate + interactions if resumability/turn audit is required (Phase-5 decision). | L | Decision-dependent |
| M7 | Offline is designed, not exercised end-to-end. | `/v1/sync/batch` is a synthetic prototype disconnected from learning; `offline_package` is a literal string; nothing consumes packages or applies deltas. | The offline capability (a core non-negotiable) is unproven; must not be reported as "working." | Build author-package → device → offline session → sync-back path (Phase-2+). | L | No |
| M8 | Accessibility gaps in the studio console. | `StudioConsole.tsx`: no `aria-live` on errors/validation; `<th>` lacks `scope`; weak `:focus-visible`; `ReadAloud` is icon-only (contradicts the codebase's own icon+text rule). | SR users miss dynamic errors; WCAG 2.2 §2.4.11/§2.4.13 focus; low-literacy sighted users get an emoji only. | Add aria-live, th scope, focus-visible tokens, visible label on ReadAloud. | S–M | No (before any student-facing UI) |
| M9 | README/ENGINEERING docs are materially stale. | Test counts say "57/46/96%" (actual 126/97%); false "contexts import no third-party" invariant; missing curriculum_studio/learning/vertical_slice from the tree and the `/v1/studio/*` endpoints. | New-dev confusion; the false invariant is the root cause of B2. | Refresh both docs. | S | No |
| M10 | `uv` workflow documented but not implemented; no lockfile. | Docs say `make install # uv venv`; `Makefile` uses `python3 -m venv` + pip; no `[tool.uv]`/`uv.lock`. | Promised toolchain absent; non-reproducible installs. | Adopt uv in the Makefile + commit `uv.lock`, or correct the docs. | S | No |
| M11 | The `vertical_slice` demo ships inside the production wheel. | `pyproject.toml` packages `src/taleem_core` wholesale; `vertical_slice/` (runner + lesson) is distributable. | Demo/fixture code in the shipped artifact enlarges runtime surface; blurs the "scaffolding only" boundary. | Move under `tests/`/`examples/` or exclude in hatch build. | S–M | Recommended |
| M12 | Test-suite blind spots. | `test_integration` asserts health/sync/skeleton/metrics only — not studio (mounted) nor learning (unmounted); no cross-context (publish → learning read model) test; no authZ/negative-auth tests; no load/perf tests. | The unmounted-router defect (H1) is invisible to tests; whole-system integration unverified. | Add app-level OpenAPI-drift test, a cross-context integration test, authZ tests (after B1), and a smoke load test. | M | Partly (drift + cross-context) |
| M13 | Serde does not persist injectable timestamps or gate-results snapshot. | `mapper` transition/gate/version values omit domain `at`/`created_at` (DB `now()` used); `gate_results_snapshot` NOT NULL DEFAULT `[]` is never set. | Injectable `clock` never reaches storage (round-trip identity claim fails once versioned); published versions drop the QA-gate evidence they were approved under. | Persist domain times or drop the identity claim; snapshot `quality_gate_results` at publish (+ add to `Version`). | S–M | No |
| M14 | `_default_system_id()` writes on read. | Reached from `get()/find()`; lazily inserts+flushes an `EducationSystemRow` when missing. | A pure read performs a write — fails on a read replica / least-privilege read role. | Seed the default system in the migration; make the resolver read-only. | S | No |

---

## 6. LOW findings (hygiene)

| ID | Finding | Fix | Effort |
| --- | --- | --- | --- |
| L1 | API reaches into `SessionService._sessions` private repo (`api.py`). | Add `SessionService.get_session(id)`. | S |
| L2 | RLS is a visibility filter, not an access boundary (no `FORCE RLS`/`WITH CHECK`/actor predicate). | If it must be a boundary, add FORCE RLS + non-owner role. | S |
| L3 | Duplicated persistence `base.py` (~90 near-identical lines) across contexts. | Keep separate `DeclarativeBase`; factor engine/pragma/translate boilerplate into shared platform helper. | M |
| L4 | Estimator uncertainty is a pure `0.7^n` observation counter, not evidence-consistency; a flip-flopping learner still reaches "confident mastery". | Calibrate/replace via the analytics validation loop. | M |
| L5 | Scheduler/recall semantic mismatch: `on_learned` solves for recall from 1.0 but `predicted_recall` multiplies by mastery<1 → reviews land slightly early. | Reconcile the two formulas. | S |
| L6 | 14-state session saga carries no per-step behavior (structure without behavior). | Attach behavior or simplify. | S |
| L7 | `PublishPort.publish` + `all()` select without `system_id` scope → `MultipleResultsFound`/cross-system leak once a 2nd system exists. | Scope by `system_id` consistently. | S |
| L8 | `_rank_reviews` ranks by stored mastery, not `predicted_recall`. | Rank by decayed recall. | S |
| L9 | `analytics.objectives_in_progress` excludes needs_review/at_risk. | Include or rename. | S |
| L10 | Root-level report clutter (~13 point-in-time `*.md` at repo root). | Move to `docs/_reports/`. | S |
| L11 | `docs/` numbering skips `09`. | Confirm reservation or renumber. | S |
| L12 | `curriculum-research/` at repo root, outside `docs/`, no index. | Move under `docs/` with a README. | S |
| L13 | Redundant `escalate()` guard (RECORDING already in `_ACTIVE`); minor ordering inconsistencies in `select_next`. | Tidy. | S |
| L14 | Cold-start `Diagnose` gate excludes root objectives (matches design note F2) — acceptable, noted. | None (documented). | — |

---

## 7. Cross-cutting reviews (requested dimensions)

- **Repository organisation:** Good bones — clean `.gitignore` (no tracked caches), consistent
  `__init__.py`, sensible `services/apps/packages/infra/docs` split. Detractors: ~13 point-in-time
  report files at the root (L10), a `09` gap in docs numbering (L11), and `curriculum-research/`
  outside `docs/` (L12).
- **Naming consistency:** Strong and consistent — `Row` suffix for ORM, `*Service`, `*Repository`,
  `build_*_router`, snake_case modules, StrEnum values. Minor: contract path params use camelCase
  (`{sessionId}`) while the code uses snake_case — cosmetic only.
- **Architecture consistency:** Hexagonal/DDD is applied consistently and **domain purity is verified
  in both contexts** (no framework imports in either `domain/`). The real inconsistency is the
  **application→infrastructure leak** (M4) and the **composition root lagging** the contexts
  (H1/H2) — the pattern is right; the wiring hasn't kept up.
- **Dependency boundaries:** Cross-context coupling is correctly confined to one adapter
  (`learning/adapters/curriculum_read_model.py` reads Curriculum Studio) — a legitimate integration
  seam. No domain-to-domain cross-context imports. The boundary leak is layer-wise (application →
  concrete UoW/ORM), not context-wise.
- **Code duplication:** Low overall. The one notable duplication is the persistence `base.py`
  boilerplate across contexts (L3) — justified at the `DeclarativeBase` level, factorable at the
  engine/pragma level.
- **Package boundaries:** Mostly clean; the exception is the demo `vertical_slice` shipping in the
  production wheel (M11), which should be excluded or relocated.
- **Future scaling risks:** (1) The learning write path hydrates full evidence history per attempt
  (M3) — the first hard scaling wall. (2) Optimistic locking gaps (H6) surface under concurrency.
  (3) In-memory sessions (M6) cap horizontal scale and lose the tutoring trace. (4) No load/perf
  testing anywhere — scaling behavior is entirely unmeasured. (5) ORM/migration drift (H10) will
  compound as the schema evolves. Note: the deliberate authoring-store-vs-student-scale boundary
  (curriculum objects here, interactions in delivery/analytics) is a **correct** scaling decision and
  remains sound.

---

## 8. Top 20 recommendations (ranked)

1. **Add auth to the studio (and learning) routers; derive `actor_role` from verified JWT claims, not
   the body.** (B1) — closes the curriculum-tampering hole.
2. **Fix/remove the red `core-tests` CI job and the broken `make test-core`.** (B2) — restore CI trust.
3. **Add a schema-parity CI test (ORM metadata vs the Alembic migration).** (H10) — single
   highest-leverage fix; would have caught the `tags`/CHECK drift automatically.
4. **Mount the learning router in `create_app` + assert its paths in an OpenAPI-drift test.** (H1, M12)
5. **Wire the SQL persistence + UoW into the running app (replace in-memory studio repo).** (H2)
6. **Author the `learning` Alembic migration + register `LearningBase.metadata` in `env.py`.** (H3)
7. **Run Postgres + the migration + PG-gated tests in CI (`postgres:16` service, `CS_DATABASE_URL`).** (H4)
8. **Fix the `RECURRED` misconception dead-state.** (H7) — genuine pedagogy defect.
9. **Attach the audit-immutability trigger to the partitioned parent.** (H11) — tamper-evidence gap.
10. **Guard against the default JWT secret (and HS256) in production.** (H8)
11. **Lint all OpenAPI contracts in CI.** (H5)
12. **Close the optimistic-locking cross-request gap in both contexts.** (H6)
13. **Fix the write-model N+1 / full-evidence hydration.** (M3) — first scaling wall.
14. **Instrument application services (spans/metrics/logs) + propagate `correlation_id`.** (H9)
15. **Tighten misconception clearance (multi-correct, item-scoped).** (M5)
16. **Harden session end/escalation (no 500; never overwrite ESCALATED; wire ENDED_SAFELY).** (M1, M2)
17. **Refresh README/ENGINEERING; reconcile the uv-vs-venv story + add a lockfile.** (M9, M10)
18. **Exclude the `vertical_slice` demo from the production wheel.** (M11)
19. **Fix the studio-console accessibility gaps before any student-facing UI.** (M8)
20. **Add a cross-context integration test (studio publish → learning read model) + a smoke load test.** (M12)

---

## 9. Phase 5 go/no-go

**Decision: NO-GO for Phase 5 (Student Experience) implementation — CONDITIONAL GO for Phase 5
design/planning and continued governance-safe work.**

Rationale: Phase 5 builds student/parent/mentor experiences directly on the learning APIs and
persistence. Building user-facing product on foundations that are **unauthenticated (B1), unmounted
(H1), backed by an in-memory repo in the app (H2), un-migrated (H3), unguarded by CI (B2, H4, H5,
H10), and carrying two known correctness defects (H7, H11)** would bake integration debt and a
security hole into every feature above it — the exact opposite of this project's "no technical debt by
design" and "child safety first" principles.

The remedy is small and well-scoped. Insert a **Phase 4.2 — "Wire & Harden"** milestone whose exit
criteria are the two BLOCKERs and the must-fix HIGHs (H1–H8, H10, H11). That is on the order of a few
focused days, not a redesign — the architecture is sound; it needs wiring, CI coverage, and two bug
fixes.

**Go now:** Phase 5 design docs, UX/IA, governance/safeguarding progress (Phase-1.5), and any pure,
child-data-free work. **Blocked until Phase 4.2 exits:** implementing Phase 5 features against the
current API/persistence wiring.

This verdict is consistent with the project's established discipline: design → adversarial review →
**fix what the review found** → build. The review found real, fixable gaps; close them before
building higher.

---

## 10. What is genuinely right (so it is not lost)

- Domain purity holds in **both** contexts (verified) — the hexagonal boundary is real.
- The Phase-4.1 slice is **real, not mocked** — actual persistence, scorer, estimator, forgetting,
  and decision engine, on authored-original content.
- BKT posterior math, the audit hash-chain serialization, serde content fidelity, the single
  reversible curriculum migration, and the **actively-tested no-PII invariant** are all correct.
- The authoring-store vs student-scale-store boundary is a sound long-term scaling decision.
- The design-and-review discipline (adversarial reviews that changed the design, e.g. the cold-start
  fix) is a genuine organizational strength — keep it.

*No code was modified in producing this review.*
