# Engineering Guide — Project Taleem

Entry point for the codebase. The blueprint lives in [docs/](./docs); this covers the **code**.

## Phase status

We are in **Phase 1.5 — Remediation**, running three parallel tracks (see the review deliverables):

- **Track A** — [FOUNDER_DECISIONS.md](./FOUNDER_DECISIONS.md) (governance)
- **Track B** — [EXTERNAL_VALIDATION_CHECKLIST.md](./EXTERNAL_VALIDATION_CHECKLIST.md) (independent review)
- **Track C** — Engineering Safe Zone: the **M1 walking skeleton** in this repo

Track C builds **only** work with zero dependency on unresolved governance decisions. It deliberately
does **not** implement enrolment, child accounts, live data, payments, production AI, or safeguarding
workflows — so that Phase 2 unblocks immediately once governance reaches GO.

## Repository layout

```text
taleem/
├── services/core-api/   FastAPI backend (M1). Pure-stdlib core + FastAPI edge adapter.
├── apps/web/            Next.js PWA scaffold (design system + offline shell).
├── packages/contracts/ OpenAPI + (future) event schemas — contract-first.
├── infra/terraform/    IaC skeleton (provider pending FD-02).
├── docs/               the 50-doc blueprint + Phase-1.5 remediation artifacts (51–59).
├── .github/workflows/  docs.yml (blueprint CI) + ci.yml (code CI).
├── Makefile · docker-compose.yml
└── ARCHITECTURE_REVIEW / BLUEPRINT_GAP_ANALYSIS / RISK_REMEDIATION_PLAN / FINAL_RECOMMENDATIONS
```

## Quickstart

```bash
make install       # uv venv (Python 3.12) + deps
make test          # pytest + coverage — 57 tests, 96% coverage (≥85% gate)
make test-core     # zero-install smoke of framework/domain layers — 46 stdlib tests
make lint          # ruff + black --check + mypy (strict)
make up            # local stack (Postgres + Redis + core-api) via Docker
make help          # list all targets
```

Verified end-to-end on 2026-07-20 — see [BUILD_VERIFICATION_REPORT.md](./BUILD_VERIFICATION_REPORT.md).

## Engineering principles (enforced)

- Clean/Hexagonal + DDD: the domain/platform core imports no framework; adapters live at the edges.
- Contract-first: [openapi.yaml](./packages/contracts/openapi.yaml) is the source of truth.
- Deny-by-default authorization; fail-closed; PII never in logs (allow-list serialization).
- Governance-safe: no code path touches a child or an unresolved decision.

See [ENGINEERING_READINESS_SCORE.md](./ENGINEERING_READINESS_SCORE.md) for what is verified vs. scaffolded.
