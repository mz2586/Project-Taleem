# Version

Current version: **0.4.1**
Milestone: **phase-4.1** (First end-to-end Learning vertical slice)
Status: **pre-production / development** — governance-gated; no real child data.
Date: 2026-07-21

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
| 0.4.1 | `phase-4.1` | 2026-07-21 | Learning persistence + Learning Intelligence design + end-to-end vertical slice |
| 0.3.0 | — | 2026-07-20 | Phase 3 — Curriculum Studio authoring platform |
| 0.2.0 | — | 2026-07-20 | Phase 1.5/2 — governance tracks + M1 walking skeleton + verification |
| 0.1.0 | — | 2026-07-19 | Phase 1 — Foundation blueprint (50 docs + ADRs) |

Tags are applied going forward; earlier versions are recorded here for history and map to the commits
listed in [CHANGELOG.md](CHANGELOG.md).
