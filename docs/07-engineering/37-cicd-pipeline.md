# 37 · CI/CD Pipeline

| | |
|---|---|
| **Document ID** | 37 |
| **Owner** | VP Engineering / DevEx Lead |
| **Status** | Draft |
| **Last updated** | 2026-07-19 |
| **Related** | [40 Testing Strategy](40-testing-strategy.md) · [48 Repository Standards](48-repository-standards.md) · [49 Development Workflow](49-development-workflow.md) · [50 Definition of Done](50-definition-of-done.md) · [35 Deployment Architecture](../02-architecture/35-deployment-architecture.md) · [36 Infrastructure Architecture](../02-architecture/36-infrastructure-architecture.md) · [13 Security Model](../03-security-privacy/13-security-model.md) |

## Purpose

This document defines the Continuous Integration and Continuous Delivery pipeline for Project Taleem:
the automated path from a pushed commit to a change running safely in production. It fixes the stages,
gates, security scans, artifact strategy, environment promotion model, and database-migration handling
so that every service and app is built, verified, and shipped the same way.

## Scope

In scope: GitHub Actions workflow topology; per-language pipelines (Next.js frontend, FastAPI
backend); test and quality gates; SAST/dependency/container/secret scanning; image build and registry;
dev → staging → prod promotion; migrations in the pipeline; blue-green/canary deploy hooks; docs CI;
and the set of required status checks. Out of scope: cluster/network topology (owned by
[35 Deployment](../02-architecture/35-deployment-architecture.md) and
[36 Infrastructure](../02-architecture/36-infrastructure-architecture.md)); test content and coverage
policy (owned by [40 Testing Strategy](40-testing-strategy.md)); release/versioning conventions (owned
by [48 Repository Standards](48-repository-standards.md)).

---

## 1. Principles

| # | Principle | Consequence in the pipeline |
|---|---|---|
| 1 | **Trunk is always releasable.** | Every merge to `main` produces a deployable, fully-scanned artifact. |
| 2 | **Fast feedback for the developer.** | Cheap checks (lint, typecheck, unit) run first and fan out in parallel; p50 PR feedback < 8 min (planning assumption). |
| 3 | **The pipeline is the only path to prod.** | No manual `kubectl apply` / `docker push` to prod. Humans approve; the pipeline acts. |
| 4 | **Build once, promote the same artifact.** | An immutable image built at merge is the exact artifact promoted dev → staging → prod. No rebuilds per environment. |
| 5 | **Security is a gate, not a report.** | Secret, SAST, dependency, and container scans can **fail** the build, not just annotate it. |
| 6 | **Child-safety and low-bandwidth budgets are CI gates.** | Bundle-size budget and accessibility checks block merge (see [50 DoD](50-definition-of-done.md)). |
| 7 | **Everything as code.** | Workflows, infra, and environment config live in-repo and are reviewed like product code. |

---

## 2. Pipeline topology (end to end)

```mermaid
flowchart TD
    subgraph Dev["Developer machine"]
        A[Local pre-commit hooks<br/>lint · format · secret scan] --> B[Push branch / open PR]
    end

    B --> CI{{"CI — pull_request"}}

    subgraph CI_STAGES["CI stages (parallel fan-out)"]
        C1[Lint + Format check]
        C2[Typecheck<br/>tsc · mypy]
        C3[Unit tests + coverage]
        C4[Integration + contract tests]
        C5[Secret scan · SAST · dep audit]
        C6[Build image · SBOM · container scan]
        C7[Docs CI<br/>markdownlint · link check]
        C8[a11y + bundle-budget]
    end

    CI --> C1 & C2 & C3 & C4 & C5 & C6 & C7 & C8
    C1 & C2 & C3 & C4 & C5 & C6 & C7 & C8 --> G{All required<br/>checks green?}
    G -- no --> B
    G -- yes --> M[Squash-merge to main]

    M --> CD{{"CD — push to main"}}
    CD --> R[Build + sign immutable image<br/>push to registry]
    R --> DEV[Deploy → dev<br/>auto · run migrations]
    DEV --> SMOKE1[Smoke + synthetic checks]
    SMOKE1 --> STG[Deploy → staging<br/>auto · run migrations]
    STG --> E2E[E2E + load + a11y smoke]
    E2E --> GATE{{Manual approval<br/>+ change record}}
    GATE --> PROD[Deploy → prod<br/>canary → blue-green]
    PROD --> VERIFY[Progressive verify<br/>SLO burn / error rate]
    VERIFY -- healthy --> DONE[Promote 100% + tag release]
    VERIFY -- unhealthy --> RB[Auto-rollback]
```

---

## 3. CI stages and gates

CI runs on `pull_request` (and `merge_group` for the merge queue). Stages fan out in parallel; a job
only runs the language pipelines whose paths changed (path filtering) to keep feedback fast.

| Stage | Frontend (Next.js/TS) | Backend (FastAPI/Python) | Gate (blocks merge?) |
|---|---|---|---|
| **Format** | Prettier `--check` | Black `--check`, Ruff format check | Yes |
| **Lint** | ESLint (typescript-eslint, jsx-a11y, tailwind) | Ruff (pyflakes, bugbear, isort, security) | Yes |
| **Typecheck** | `tsc --noEmit` (strict) | `mypy --strict` | Yes |
| **Unit tests** | Vitest + React Testing Library | pytest | Yes — coverage floors per [40](40-testing-strategy.md) |
| **Integration** | Route/API handler tests | pytest + Testcontainers (Postgres/Redis) | Yes |
| **Contract** | Consumer checks vs OpenAPI | Provider verify vs OpenAPI (schemathesis) | Yes |
| **Accessibility** | `axe-core` + Playwright on key routes | — | Yes (WCAG 2.2 AA, see [16](../04-design/16-accessibility-standards.md)) |
| **Bundle budget** | `size-limit` / route JS ≤ 150 KB gzip | — | Yes (NFR [04](../01-product/04-non-functional-requirements.md)) |
| **Secret scan** | gitleaks (full history on PR) | gitleaks | Yes |
| **SAST** | CodeQL (JS/TS) | CodeQL (Python) + Bandit | Yes (High/Critical) |
| **Dependency audit** | `pnpm audit` + OSV-Scanner | `pip-audit` / uv + OSV-Scanner | Yes (High/Critical, no fix-available grace 14d) |
| **Container scan** | Trivy on built image | Trivy on built image | Yes (High/Critical OS+lib) |
| **SBOM** | Syft → CycloneDX artifact | Syft → CycloneDX artifact | No (attached to release) |
| **Docs CI** | markdownlint + lychee link check | same | Yes for `docs/**` changes |

**Coverage floors** (enforced in CI, see [40 Testing Strategy](40-testing-strategy.md)): overall lines
≥ 80%; domain + application layers ≥ 90%; safety-critical modules (AI Teacher guardrails, auth,
grading, consent) ≥ 100% of critical branches.

---

## 4. Example workflow — backend CI (FastAPI)

```yaml
# .github/workflows/ci-backend.yml
name: ci-backend
on:
  pull_request:
    paths: ["services/**", "packages/py-*/**", ".github/workflows/ci-backend.yml"]
  merge_group: {}

permissions:
  contents: read
  security-events: write   # CodeQL upload
  id-token: write          # OIDC to cloud, no long-lived keys

concurrency:
  group: ci-backend-${{ github.ref }}
  cancel-in-progress: true

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with: { enable-cache: true }
      - run: uv sync --frozen --all-extras
      - name: Format & lint
        run: |
          uv run ruff format --check .
          uv run ruff check .
      - name: Typecheck
        run: uv run mypy --strict services packages
      - name: Secret scan
        uses: gitleaks/gitleaks-action@v2

  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env: { POSTGRES_PASSWORD: test }
        options: >-
          --health-cmd "pg_isready" --health-interval 5s --health-retries 10
        ports: ["5432:5432"]
      redis:
        image: redis:7
        ports: ["6379:6379"]
    env:
      DATABASE_URL: postgresql://postgres:test@localhost:5432/postgres
      REDIS_URL: redis://localhost:6379/0
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with: { enable-cache: true }
      - run: uv sync --frozen --all-extras
      - name: Migrate (test DB)
        run: uv run alembic upgrade head
      - name: Unit + integration + contract
        run: uv run pytest -q --cov --cov-report=xml --cov-fail-under=80
      - name: Contract verify (OpenAPI)
        run: uv run schemathesis run --checks all http://localhost:8000/openapi.json
      - uses: codecov/codecov-action@v4

  sast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with: { languages: python }
      - uses: github/codeql-action/analyze@v3
```

Required checks are configured on the branch protection rule for `main` (see
[48 Repository Standards](48-repository-standards.md) §Protected branches).

---

## 5. Artifact & image build strategy

| Decision | Choice | Rationale |
|---|---|---|
| **Registry** | GitHub Container Registry (GHCR), one repo per service/app. | Native to Actions, OIDC auth, no extra credential surface. Mirror to in-region registry for pull latency near Pakistan. |
| **Image identity** | Tag by immutable `git-sha`; `env-*` tags are moving pointers. | "Build once, promote same digest" (§1.4). Deploys reference the **digest**, never `latest`. |
| **Base images** | Distroless / slim, pinned by digest; non-root user. | Smaller attack surface; reproducible; passes container scan. |
| **Multi-arch** | `linux/amd64` + `linux/arm64`. | Cost-efficient ARM nodes; keeps options open. |
| **Provenance** | Sign with cosign (keyless OIDC) + SLSA provenance attestation + CycloneDX SBOM attached. | Supply-chain integrity; admission control can require a valid signature. |
| **Frontend** | Next.js standalone output containerized; static assets to CDN with immutable hashing. | Low-bandwidth: long-cache hashed assets, small runtime image. |
| **Caching** | Turborepo remote cache + registry layer cache; only affected packages rebuild. | Monorepo build times stay flat as repo grows. |

---

## 6. Environment promotion

Three long-lived environments; the **same image digest** flows through all three. Config differs by
environment via env-scoped secrets/manifests, never by rebuilding.

```mermaid
flowchart LR
    MAIN[main merge] --> BUILD[Build + sign digest]
    BUILD --> DEV[dev<br/>auto-deploy]
    DEV -->|smoke + synthetic pass| STG[staging<br/>auto-deploy]
    STG -->|E2E + load + a11y pass| APPROVE{Manual approval}
    APPROVE --> PROD[prod<br/>canary → blue-green]
```

| Environment | Purpose | Data | Deploy trigger | Gate to next |
|---|---|---|---|---|
| **dev** | Integration of `main`; internal only. | Synthetic/seeded; **no real child data**. | Auto on merge. | Smoke + synthetic pass. |
| **staging** | Prod-like; release rehearsal, E2E, load. | Anonymised/synthetic at prod scale. | Auto after dev green. | E2E + load + a11y + manual sign-off. |
| **prod** | Live students. | Real child data; strict controls per [14 Privacy](../03-security-privacy/14-privacy-model.md). | **Manual approval** (GitHub Environment protection) + change record. | Progressive verification. |

Deployment mechanism is GitOps: the pipeline updates the desired image digest in the environment's
manifests; the cluster reconciler (Argo CD / Flux — decision owned by [35](../02-architecture/35-deployment-architecture.md))
applies it. This keeps the cluster state auditable and rollback = revert a manifest commit.

---

## 7. Database migrations in the pipeline

Migrations are the highest-risk step at 1M scale. Policy: **expand → migrate → contract**, so schema
and code are always backward/forward compatible across a deploy and safe to roll back.

```mermaid
sequenceDiagram
    participant CI as Pipeline
    participant DB as Postgres
    participant App as Service (N & N+1)
    CI->>DB: 1. Expand — add nullable col / new table (backward-compatible)
    CI->>App: 2. Deploy code that writes both old+new (canary)
    App-->>DB: dual-write / backfill job
    CI->>App: 3. Deploy code that reads new
    CI->>DB: 4. Contract — drop old col (separate later release)
```

| Rule | Detail |
|---|---|
| **Tool** | Alembic (SQLAlchemy) per bounded-context DB; migrations versioned in-repo beside the service. |
| **No destructive step in the same release as the code that needs it.** | Drops/renames ship a release *after* all readers/writers are migrated. |
| **Migrations run in the pipeline**, not by hand. | A dedicated pre-deploy job runs `alembic upgrade head` against the target env with an advisory lock so only one runner migrates. |
| **Online, non-blocking DDL.** | `CREATE INDEX CONCURRENTLY`, `lock_timeout`/`statement_timeout` set; long backfills run as idempotent chunked background jobs, not in the migration. |
| **Every migration is reversible or explicitly one-way.** | `downgrade()` implemented or PR labelled `irreversible-migration` with reviewer sign-off. |
| **Staging runs the real migration against prod-scale data** before prod. | Catches lock/duration surprises. |

---

## 8. Progressive delivery — canary & blue-green

| Stage | Traffic | Auto-checks (analysis) | On breach |
|---|---|---|---|
| Canary 1 | 5% | error rate, p95 latency, SLO burn rate, AI Teacher safety-flag rate | Abort + rollback |
| Canary 2 | 25% | same, 5-min window | Abort + rollback |
| Blue-green cut | 100% (new "green") | hold old "blue" warm for fast switch-back | Instant switch to blue |
| Stabilise | 100% | 30-min soak; then scale down blue | — |

Analysis is automated (progressive-delivery controller reading Prometheus SLIs from
[38 Monitoring](38-monitoring.md)). The **core learning path** (login → lesson → submit) has the
strictest abort thresholds because its availability SLO is 99.9%. Rollback is a single reconciler
action (revert to prior digest) and must complete in < 5 min (planning assumption).

---

## 9. Docs CI

Because this repository is documentation-first, `docs/**` changes run their own gate:

- **markdownlint** — heading structure, table formatting, line hygiene.
- **lychee** — link checker for relative cross-references and external URLs (broken internal link = fail).
- **Mermaid parse** — every ```mermaid block must parse (mmdc lint) so diagrams never render broken.
- **Metadata lint** — a small script asserts every doc has the standard metadata block, a Purpose, a
  Scope, an Open Questions section, and a Change Log (see [42 Documentation Standards](42-documentation-standards.md)).

---

## 10. Required status checks (branch protection on `main`)

| Check | Source |
|---|---|
| `ci-frontend / quality` (lint, format, tsc) | ci-frontend.yml |
| `ci-frontend / test` (unit, integration, coverage) | ci-frontend.yml |
| `ci-frontend / a11y-and-budget` | ci-frontend.yml |
| `ci-backend / quality` (ruff, mypy) | ci-backend.yml |
| `ci-backend / test` (pytest, contract, coverage) | ci-backend.yml |
| `security / codeql` | codeql.yml |
| `security / secret-scan` | gitleaks |
| `security / deps-and-container` | trivy + osv |
| `docs / lint-and-links` (if `docs/**` touched) | docs.yml |
| ≥ 1 (≥ 2 for protected paths) approving review + CODEOWNERS | GitHub |

A PR may only enter the merge queue when all applicable checks pass; the merge queue re-runs required
checks against the post-merge state to prevent semantic merge conflicts breaking `main`.

---

## 11. Secrets & pipeline hardening

| Control | Implementation |
|---|---|
| **No long-lived cloud keys** | GitHub OIDC → short-lived cloud role assumption. |
| **Least-privilege `permissions:`** | Every workflow declares minimal `permissions`; default read-only. |
| **Pinned actions** | Third-party actions pinned to a commit SHA; Dependabot updates them. |
| **Env-scoped secrets** | Prod secrets only readable by the `prod` GitHub Environment, which requires approval. |
| **No secrets in logs** | Secret scanning + masked outputs; artifacts scanned before upload. |
| **Fork PRs** | Do not receive secrets; deploy jobs never run from forks. |

---

## Open questions

- **GitOps controller:** Argo CD vs Flux is pending [35 Deployment](../02-architecture/35-deployment-architecture.md); this doc assumes a reconciler exists.
- **In-region registry mirror:** provider and replication SLA for pull latency near Pakistan (planning assumption).
- **Load-test placement:** whether full 1M-scale load runs per-release on staging or on a scheduled cadence (cost trade-off) — coordinate with [40 Testing Strategy](40-testing-strategy.md).
- **Merge queue throughput:** batch size tuning once real PR volume is known.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial draft (Phase 1). | VP Engineering / DevEx Lead |
