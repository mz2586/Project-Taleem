# Engineering Readiness Score — Project Taleem (M1 Walking Skeleton)

| | |
|---|---|
| **Track** | C — Engineering Safe Zone |
| **Date** | 2026-07-20 |
| **Scope** | Governance-safe scaffolding + M1 walking skeleton (no child data, no unresolved-decision dependencies) |
| **Goal** | Make Phase 2 unblock *immediately* once governance (Track A) reaches GO |

## 1. Headline

> **Engineering Readiness Score: 83 / 100** — "Foundation built and the verifiable core is green; the
> remaining points are full-stack build execution and production adapters intentionally deferred to
> governance decisions (cloud/residency/KMS/production-AI)."

**Honesty split** (per the environment: Python 3.14 stdlib only, no network for `pip`/`npm install`,
Docker present but no registry):

- **Verified-green here:** the pure-stdlib backend core — **38 unit tests pass**, all modules compile,
  docs CI (markdownlint + links) clean.
- **Structured-but-not-executed here:** FastAPI runtime, `docker build`, and `npm run build` — real,
  coherent, and wired into `ci.yml`, but not run in this sandbox (no package registry access).
- **Intentionally deferred (correct):** production cloud/IaC bodies, KMS/HSM, OTel/Prometheus backends,
  and production AI — all gated on [FOUNDER_DECISIONS.md](./FOUNDER_DECISIONS.md).

## 2. M1 walking-skeleton requirements

| Requirement | Status | Evidence |
|---|---|---|
| Builds successfully | ◐ Core verified; full-stack in CI | All modules compile; FastAPI/Docker/web build defined in `ci.yml`, not run here |
| Tests pass | ☑ **Yes** | `38 tests … OK` via stdlib `unittest` |
| CI green | ◐ Docs CI green (run); code CI authored | `docs.yml` verified locally; `ci.yml` runs on push |
| Dockerized | ☑ Written | `services/core-api/Dockerfile` (multi-stage, non-root, healthcheck) + `docker-compose.yml` |
| Production-quality folder structure | ☑ **Yes** | Hexagonal layout per [47 Folder Structure](./docs/07-engineering/47-folder-structure.md) |
| OpenAPI | ☑ **Yes** | Contract-first `packages/contracts/openapi.yaml` + FastAPI `/openapi.json` |
| Health endpoints | ☑ **Yes** | `/health`, `/health/ready` (+ container HEALTHCHECK) |
| Observability | ☑ Framework | correlation ids, structured logs, metrics, tracing spans |
| Metrics | ☑ **Yes** | `/metrics` Prometheus exposition + registry (tested) |
| Tracing | ◐ Abstraction | span API + OTel hook point (no-op backend until a collector) |
| Documentation | ☑ **Yes** | `ENGINEERING.md`, per-package READMEs, `Makefile`, inline docs |

## 3. Safe-zone component scorecard

Each item the brief listed, scored /5 (5 = production-ready framework; lower = scaffold or deferred).

| Component | Score | State |
|---|---:|---|
| Repository scaffolding | 5 | Complete, hexagonal, doc-47-aligned |
| CI/CD | 4 | `ci.yml` (tests/lint/type/coverage/openapi/docker/web) + `docs.yml`; runners not exercised here |
| Linting | 4 | ruff configured + per-file rules; not run (not installed) |
| Formatting | 4 | black configured; not run |
| Testing framework | 5 | stdlib suite green (38); pytest+coverage gate wired |
| Docker | 4 | Multi-stage non-root Dockerfile + compose; not built here |
| Infrastructure as code | 3 | Terraform skeleton; bodies gated on FD-02 (correct) |
| Authentication framework | 4 | JWT verify seam + Claims, tested; prod JWKS/KMS gated (FD-14) |
| Design system | 5 | Verified tokens from doc 59 (computed WCAG ratios, Sun constraint, 18px Urdu floor) |
| Component library | 3 | Button + mandated ReadAloud; contract set, breadth to grow |
| API framework | 5 | FastAPI adapter + Problem Details + OpenAPI + health |
| Logging | 5 | Structured + runtime PII allow-list redaction, tested |
| Monitoring | 4 | Golden-signal registry + `/metrics`, tested; prod backend pending |
| Observability | 4 | correlation + logs + metrics + spans |
| Configuration management | 5 | 12-factor typed settings, tested |
| Feature-flag system | 5 | Deny-by-default provider + context overrides, tested |
| Localization framework | 5 | Urdu-first catalog + numeral rendering, tested |
| Offline sync-engine prototype | 5 | Remediated conflict policy (idempotent, append-only, no client clock), tested |
| Caching framework | 5 | TTL cache + injected clock, tested |
| Storage abstraction | 5 | ObjectStore port + content-hash, tested |
| AI provider abstraction | 5 | `LLMPort` + tier routing (safety-first) + offline stub, tested; **no production AI** (correct) |
| Plugin architecture | 5 | Module registry + mount-conflict guard, tested |
| Developer documentation | 5 | Guides + Makefile + READMEs |

**Average ≈ 4.4 / 5 → 88% on scaffolding completeness.** The overall **83/100** discounts for the
full-stack build not being *executed* in this environment (a sandbox limitation, not a design gap).

## 4. Guardrails honoured (what was deliberately NOT built)

Per the brief — none of these appear anywhere in the code:

- ❌ student enrolment · ❌ live student data · ❌ payments · ❌ child accounts ·
  ❌ production AI (only an offline `StubLLMProvider`) · ❌ safeguarding workflows.

Every one depends on an unresolved governance decision and is a Phase-2 item. The code contains explicit
guards and comments marking these boundaries.

## 5. How this unblocks Phase 2 on GO

The moment Track A returns the Phase-1.5 decisions:

- **FD-02/03 (cloud/residency)** → fill the Terraform module bodies + provider; the skeleton is ready.
- **FD-14 (KMS)** → swap the JWT HS256 seam for asymmetric JWKS behind the same verifier interface.
- **FD-03 (LLM residency)** → implement a real `LLMProvider` behind the existing `LLMPort` — no product
  code changes (only the adapter).
- **FD-11 (broker)** → implement the event-publisher port; the outbox/consumer seams are contract-first.

Because every production concern sits behind a port/adapter already exercised by tests, Phase 2 is
adapter-implementation, not re-architecture.

## 6. Recommended next engineering steps (pre-GO, still safe)

1. Run `ci.yml` on a real runner (install deps) to convert the ◐ items to ☑.
2. Add contract tests binding `openapi.yaml` ↔ the FastAPI app (schemathesis).
3. Grow the component library + add axe/RTL visual-regression to `web-build`.
4. Add the CDC/outbox seam (behind a port) ready for the FD-11 broker choice.

---

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-20 | Initial engineering readiness score: 83/100; M1 walking-skeleton requirement checklist; 23-component scorecard; guardrails honoured; GO-unblock path. | Engineering (Track C) |
