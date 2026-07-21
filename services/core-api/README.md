# Core API — developer guide

Project Taleem's backend, **M1 walking skeleton**. Governance-safe scaffolding only — no enrolment,
child accounts, live data, payments, production AI, or safeguarding workflows.

## Architecture (Clean/Hexagonal + DDD)

```text
src/taleem_core/
├── platform/     # cross-cutting frameworks — PURE stdlib, framework-free, fully unit-tested
│   ├── config.py         12-factor settings
│   ├── logging.py        structured logs + runtime PII redaction (allow-list serialization)
│   ├── correlation.py    request correlation ids
│   ├── errors.py         RFC 9457 Problem Details
│   ├── feature_flags.py  deny-by-default flag provider
│   ├── i18n.py           Urdu-first localization + numeral rendering
│   ├── ids.py            UUIDv7 (offline-safe)
│   ├── metrics.py        Prometheus-format registry
│   ├── tracing.py        span abstraction (OTel hook point)
│   └── plugins.py        bounded-context module registry
├── ports/        # hexagonal ports + stub adapters (LLM, cache, storage, clock)
├── contexts/     # bounded-context modules (health, sync, curriculum_studio, learning)
├── vertical_slice/ # Phase-4.1 end-to-end demonstration (author -> teach -> master)
├── auth/         # AuthN (JWT seam) + AuthZ (PDP deny-by-default) frameworks
└── main.py       # FastAPI ASGI adapter / composition root (the ONLY framework-coupled file)
```

**Key property:** the `domain` layers of every context import **no framework** (pure-stdlib,
independently unit-testable). The persistence adapters use SQLAlchemy and the edge uses FastAPI, so
the full suite requires the dev deps (`pip install -e ".[dev]"`).

## Tests

**140 tests** (SQLite portable + PostgreSQL-gated). Domain/decision/estimator logic is covered
≥95%; overall coverage **~96%** (gate ≥ 85%). The PostgreSQL-gated tests (Alembic migration
reversibility, FTS trigger, ORM↔migration schema parity) run when `CS_DATABASE_URL` is set.

```bash
make install       # venv (Python 3.12) + runtime + dev deps
make test          # pytest --cov (≥85% gate)
make lint          # ruff + black --check + mypy (strict)
make migrate       # apply Alembic migrations to CS_DATABASE_URL (both schemas)
make test-pg       # migration reversibility + PostgreSQL-gated tests (needs CS_DATABASE_URL)
make run           # uvicorn taleem_core.main:app --reload
```

## Endpoints (walking skeleton)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/health/ready` | Readiness (dependency probes) |
| GET | `/metrics` | Prometheus exposition |
| POST | `/v1/sync/batch` | Offline sync engine prototype (synthetic data) |
| GET | `/v1/skeleton/protected` | AuthN(JWT) + AuthZ(PDP) seam demo |
| * | `/v1/studio/*` | Curriculum Studio authoring lifecycle (bearer JWT required) |
| * | `/v1/learning/*` | Learning Intelligence sessions + knowledge (bearer JWT; IDOR-guarded) |

All `/v1/studio/*` and `/v1/learning/*` routes require a verified bearer token; the actor's role is
taken from the token, never the request body. Contracts: `packages/contracts/{openapi,
curriculum-studio.openapi,learning.openapi}.yaml`, all served/validated and also at `/openapi.json`.

## What is deliberately NOT here

Enrolment · child/guardian accounts · live student data · payments · production AI (only an offline
`StubLLMProvider`) · safeguarding workflows. These depend on unresolved governance decisions
([FOUNDER_DECISIONS.md](../../FOUNDER_DECISIONS.md)) and are Phase-2.
