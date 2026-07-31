# RC1 Checklist

Go/no-go checklist for Release Candidate RC1, with the evidence gathered on 2026-07-31. `[x]` = done
and verified; `[ ]` = an open item (all remaining opens are **non-software / governance**, listed at
the end).

## 1. Repository cleanup

- [x] No committed build cruft (`__pycache__`, `.DS_Store`, logs, tmp) — `git ls-files` clean
- [x] `.gitignore` covers deps, build output, secrets, caches, OS/editor files
- [x] Stale descriptions removed ("M1 walking skeleton" → accurate) in `pyproject.toml`,
  `apps/web/package.json`, root `packages/contracts/openapi.yaml`
- [x] Formatting verified: ruff + black + mypy `--strict` clean; markdownlint 0 errors (190 files)
- [x] License metadata reconciled to the authoritative `LICENSE` (was falsely "MIT")
- [~] Historical process docs retained (heavy cross-linking; moving breaks the CI link-check) —
  decision recorded in the release notes; entry points (README) made current instead

## 2. Dependency audit

- [x] Removed 6 never-imported runtime deps (pydantic-settings, python-json-logger,
  opentelemetry-api/sdk, prometheus-client, pyjwt)
- [x] Versions locked: `services/core-api/requirements.lock` (26 pinned) + `apps/web/package-lock.json`
- [x] Reproducible build wired into the Dockerfile (`pip install -r requirements.lock` then
  `--no-deps .`)
- [x] Verified: clean venv installs the lock + app and boots (fastapi 0.141.1 pinned; 16 routes;
  removed deps confirmed absent)

## 3. Installation

- [x] One-command local: `make up` (Postgres + core-api; migrations auto-run)
- [x] One-command production path documented (reproducible image + run command with real secrets)
- [x] Verified from a clean environment (fresh venv, lock-only install → boots)

## 4. Documentation

- [x] README updated from "pre-code blueprint" to the working system + quickstart + RC pointers
- [x] Architecture documented/referenced (`ARCHITECTURE_REVIEW.md`, `docs/02-architecture/`)
- [x] Deployment — `RC1_DEPLOYMENT_GUIDE.md` (build/deploy/migrate/health/rollback)
- [x] Operations — `RC1_OPERATIONS_GUIDE.md` (monitoring, kill switch)
- [x] Troubleshooting — operations guide §Troubleshooting
- [x] Backup / Restore / Upgrade — operations guide §§Backup, Restore, Upgrade

## 5. Production verification (this run)

- [x] Build from scratch — reproducible clean-venv install verified (Docker build uses the identical
  pinned sequence; earlier RC image build succeeded)
- [x] Deploy from scratch — RC backend started on uvicorn against a real PostgreSQL 16
- [x] Migrate database — `alembic upgrade head` applied to real PostgreSQL (reversibility CI-verified)
- [x] Start services — uvicorn up; startup complete
- [x] Health checks — `/health` and `/health/ready` return 200
- [x] Pilot simulator — `PASS` (20/20 students completed; offline verified; failure-injection +
  recovery; all invariants pass; exit 0)

## 6. Quality gates & validation

- [x] Backend: **243 passed / 8 skipped**, coverage **96.42%** (ruff, black, mypy --strict)
- [x] Frontend: **90 tests** pass; `tsc --noEmit` clean; production build compiles all pages
- [x] Integration + adversarial tests included and green (guardian, pilot-0 assurance, sync
  evidence, integration, concurrency, security)
- [x] OpenAPI contracts valid (8 contracts; redocly)
- [x] Docs: markdownlint 0 errors
- [x] `make gates` — **All gates passed**
- [x] Browser validation — Guardian Portal renders live data from the RC backend over CORS
  (browser → CORS → API → PostgreSQL); student flow + IDOR (403 for unlinked) confirmed earlier

## Open items before general availability (non-software / human decisions)

These do **not** block the RC designation; they gate the RC → production go-live and are surfaced
here for the human go/no-go:

- [ ] **License ratification** — the code license is an undecided founding-team decision (metadata
  now honestly says "undecided"). Required before any external distribution.
- [ ] **Governance sign-off (M-Gov)** — consent flow, DPIA, child-safe authentication.
- [ ] **Safeguarding sign-off (M-Safe)** — policy approval + a live safeguarding drill.
- [ ] **Production secrets** — real `TALEEM_JWT_DEV_SECRET` + `TALEEM_OFFLINE_SIGNING_SEED` (the app
  fails closed on defaults) held in a secrets manager.
- [ ] **Edge** — TLS termination + rate limiting at the gateway.
- [ ] **External penetration test** — independent security audit.
- [ ] **Content + audio** — curriculum authoring/expert review beyond Grade-4; Urdu audio recording.
- [ ] **Scale-out** — a shared session/idempotency store before multi-instance deployment (single
  instance is fully supported now).

## Verdict

All engineering, quality, and release-packaging criteria for a Release Candidate are met and
evidenced above; no blocking software defects remain. Remaining opens are governance/human decisions
that gate go-live, not the candidate. **RC1 READY.**
