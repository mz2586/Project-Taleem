# Phase 4.2 — Wire & Harden — Completion Report

Source of truth: [CTO_REVIEW.md](CTO_REVIEW.md). Scope: resolve all BLOCKER findings and the HIGH
findings required before Phase 5. No new product features; no portal work; no architectural redesign.
Date: 2026-07-21. Status: **complete — all quality gates green (SQLite + PostgreSQL).**

## 1. Final quality gate

| Gate | Result |
| --- | --- |
| Ruff (lint) | ✅ PASS |
| Black (format) | ✅ PASS |
| Mypy `--strict` | ✅ PASS (83 source files) |
| Pytest (SQLite) | ✅ **137 passed, 3 skipped** (PG-gated) |
| Pytest (PostgreSQL 16) | ✅ **140 passed, 0 skipped** (all PG-gated tests run) |
| Coverage | ✅ **97%** (gate ≥ 85%; learning domain logic ≥ 95%) |
| Alembic migration reversibility (PostgreSQL) | ✅ upgrade → downgrade → upgrade, both schemas |
| ORM ↔ migration schema parity | ✅ PASS (new guard) |
| OpenAPI contracts (redocly, pinned) | ✅ 3/3 valid |

## 2. Findings resolved (mapped to CTO_REVIEW.md)

| ID | Finding | Resolution | Tests added |
| --- | --- | --- | --- |
| **B1** | No auth on studio router; role from body | Bearer-JWT + PDP on both routers via `auth/dependencies.py`; role derived from token; `actor_role` removed from bodies + contracts; IDOR guard on learning | `test_studio_api` (401/403/authed lifecycle), `test_learning_api` (401, IDOR 403) |
| **B2** | Broken `core-tests` CI job + `make test-core` | Removed the redundant zero-install `unittest` job; replaced broken `test-core` with `test-pg`/`migrate`; docs corrected | CI is now the real `core-quality` + `postgres-tests` |
| **H1** | Learning router never mounted | Mounted `build_learning_router` in `create_app` | `test_hardening_4_2::test_composed_app_mounts_learning_and_studio` |
| **H2** | Mounted app used in-memory studio repo | Composition root wires SQLAlchemy persistence + request-scoped Unit of Work | `test_studio_api` runs over the SQL-backed app |
| **H3** | No learning Alembic migration; env.py blind | `0002_learning_schema.py`; `env.py` registers both metadatas | migration + parity tests (PG) |
| **H4** | CI never ran migrations / PG tests | New `postgres-tests` CI job (postgres:16 service, migration up/down/up, PG-gated pytest) | verified locally on PG 16 |
| **H5** | Only 1 of 3 contracts linted | CI lints `packages/contracts/*.yaml` (pinned redocly) | 3/3 valid |
| **H6** | Optimistic lock cross-request/dormant | Learning root now dirtied on save (`flag_modified`) so `lock_version` engages | `test_root_dirtied_on_save…`, `test_optimistic_lock_rejects_stale_root_write` |
| **H7** | `RECURRED` misconception dead-state | `RECURRED` counts as active, blocks mastery, is re-remediable and surfaced | `test_misconception_recurrence_stays_active_and_counted` |
| **H8** | Default JWT secret bootable in prod | `load_settings()` fails closed on default secret / missing DB URL in production | `test_hardening_4_2` (H8 suite) |
| **H9** | No runtime observability in contexts | `platform/observability.py`; metrics + correlation-tagged logs in publish / attempt / session start-end | `test_slice_emits_domain_metrics` |
| **H10** | ORM ↔ migration drift (`tags`, no guard) | Added `lesson.tags` to ORM + mapper; new PG schema-parity test | `test_schema_parity` |
| **H11** | Audit trigger on leaf partition | Trigger moved to the partitioned parent `audit_log` (propagates to all partitions) | verified on PG (UPDATE blocked) |

Directly-required supporting fixes (needed by the above): `SessionService.get_session` (removed the
router's private-repo access, L1), dynamic published-curriculum graph for the mounted learning API,
and the `end`-from-teaching 500 / ESCALATED-overwrite guards (M1/M2) — required by mounting the
learning router safely.

## 3. Execution trace (composed app, authenticated)

The end-to-end slice still runs green
(`python -m taleem_core.vertical_slice.runner`): author → publish → cold-start → teach → assess →
misconception detect/remediate/clear → mastery → schedule review → analytics → end. New: the
Curriculum Studio and Learning APIs are now reachable in `create_app()` (7 learning + 9 studio
paths in `/openapi.json`), both requiring a bearer token; the studio app persists to SQLAlchemy with
a request-scoped Unit of Work; domain metrics increment on publish/attempt/mastery/session events.

## 4. What was intentionally NOT done (per scope)

MEDIUM/LOW findings not required by a BLOCKER/HIGH fix were left for a later pass and remain in
CTO_REVIEW.md: M3/M4 (evidence-hydration N+1), M5 (misconception clearance strictness), M6/M7
(durable sessions, offline end-to-end), M8 (studio-console a11y), M10/M11 (uv workflow, demo-in-wheel),
and the LOW hygiene items. No Student/Parent/Mentor portal work was performed. No architecture was
redesigned.

## 5. Remaining production blockers before Phase 5 scale-out

Closed by 4.2: auth, router mount, SQL wiring, learning migration, CI migration/PG coverage, the two
correctness defects, ORM/migration drift, insecure prod defaults, and baseline observability. Still
open (tracked in CTO_REVIEW.md, not Phase-5 blockers for *design*, but for scale/production):
governance & safeguarding gate (Phase-1.5), generative-AI-tier safety, durable session store, the
event relay + analytics warehouse, evidence-hydration performance (M3), and estimator validation
from real data.

## 6. Phase 5 gate

The Phase-4.2 exit criteria (all BLOCKER + must-fix HIGH from the CTO review) are met and verified.
The foundation is now authenticated, mounted, SQL-backed, migrated, CI-guarded, and observable —
Phase 5 (Student Experience) *implementation* may proceed on it, within the standing Phase-1.5
governance gate.
