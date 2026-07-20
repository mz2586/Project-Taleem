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
├── contexts/     # bounded-context modules (health, sync engine prototype)
├── auth/         # AuthN (JWT seam) + AuthZ (PDP deny-by-default) frameworks
└── main.py       # FastAPI ASGI adapter / composition root (the ONLY framework-coupled file)
```

**Key property:** the `platform`, `ports` (logic), `contexts`, and `auth` layers import **no
third-party package**, so the full test suite runs with zero installs. FastAPI/pydantic appear only in
`main.py` (the edge adapter).

## Tests

**57 tests total** — 46 framework/domain unit tests (framework-free, run on stdlib alone) + 11
integration tests (boot the FastAPI app via `TestClient`). Coverage **96%** (gate ≥ 85%).

```bash
# Full suite + coverage (in the venv — the canonical path):
make install       # uv venv (Python 3.12) + runtime + dev deps
make test          # pytest --cov (57 tests, ≥85% gate)

# Zero-install smoke of the framework/domain layers (no venv, no deps):
make test-core     # 46 tests via stdlib unittest

make lint          # ruff + black --check + mypy (strict)
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

The OpenAPI contract is `packages/contracts/openapi.yaml` (contract-first) and is also served at
`/openapi.json` by FastAPI at runtime.

## What is deliberately NOT here

Enrolment · child/guardian accounts · live student data · payments · production AI (only an offline
`StubLLMProvider`) · safeguarding workflows. These depend on unresolved governance decisions
([FOUNDER_DECISIONS.md](../../FOUNDER_DECISIONS.md)) and are Phase-2.
