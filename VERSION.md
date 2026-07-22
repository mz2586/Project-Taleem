# Version

Current version: **0.9.0**
Milestone: **phase-9** (Pilot Operations & Guardian Experience)
Status: **pre-production / development** — governance-gated; no real child data.
Date: 2026-07-22

The local Git repository is the canonical source of truth. This project is maintained locally; there
is no remote. Every version corresponds to an annotated Git tag on this machine.

## Versioning scheme

`0.<phase-major>.<phase-minor>` while pre-1.0.

- `phase-major` tracks the development phase (see the Master Project Overview).
- `phase-minor` tracks sub-milestones within a phase (e.g. 4.1 = Phase 4, slice 1).
- `1.0.0` is reserved for the first production-ready, governance-cleared release.

The Python package `taleem-core` (`services/core-api/pyproject.toml`) carries its own artifact
version and is bumped independently of this project milestone version.

## Version history

| Version | Tag | Date | Milestone |
| --- | --- | --- | --- |
| 0.9.0 | `phase-9` | 2026-07-22 | Pilot Operations & Guardian Experience — guardian + mentor experience design (over existing read models), pilot ops runbooks (runbook, device prep, incident response), end-to-end validation, success metrics; documentation only, reuses existing platform |
| 0.8.0 | `phase-8` | 2026-07-22 | AI Teacher — templated, curriculum-grounded, explainable teaching orchestration (no LLM): explanation styles, adaptive plan, guardrails, confidence, offline capability matrix; reuses existing components |
| 0.7.0 | `phase-7` | 2026-07-22 | Curriculum Production System (framework, pipeline, standards, QA) + Grade 4 complete package (all core subjects) — documentation + content only, reuses existing platform |
| 0.6.4 | `phase-6.2C-1` | 2026-07-22 | Offline Engineering Hardening — Ed25519 package signing + client verification, chaos/fault-injection framework, cache purge/de-enrolment, diagnostics enhancements, LRU eviction |
| 0.6.3 | `phase-6.2B` | 2026-07-22 | Offline Synchronization Engine — durable sync consumer (attempt→evidence, idempotent), sync queue, background drain, retry, reconcile, resume, diagnostics, status UI |
| 0.6.2 | `phase-6.2A` | 2026-07-22 | Offline-Lite — service worker, IndexedDB, download manager, offline dashboard/lessons, local progress + resume, cache versioning; backend offline package service |
| 0.5.5 | `phase-5.5` | 2026-07-21 | Student Platform Backend APIs (derived read models: homework, reviews, hint, …) |
| 0.5.0 | — | 2026-07-21 | Phase 5 — Student Experience design + portal core scaffold (governance-safe) |
| 0.4.2 | `phase-4.2` | 2026-07-21 | Wire & Harden — CTO-review remediation (auth, wiring, migration, CI, defects) |
| 0.4.1 | `phase-4.1` | 2026-07-21 | Learning persistence + Learning Intelligence design + end-to-end vertical slice |
| 0.3.0 | — | 2026-07-20 | Phase 3 — Curriculum Studio authoring platform |
| 0.2.0 | — | 2026-07-20 | Phase 1.5/2 — governance tracks + M1 walking skeleton + verification |
| 0.1.0 | — | 2026-07-19 | Phase 1 — Foundation blueprint (50 docs + ADRs) |

Tags are applied going forward; earlier versions are recorded here for history and map to the commits
listed in [CHANGELOG.md](CHANGELOG.md).
