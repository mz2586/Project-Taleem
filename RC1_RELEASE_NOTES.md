# RC1 Release Notes

Project Taleem — **Release Candidate RC1** (2026-07-31). First release-candidate packaging of the
working platform. Detailed change history: [CHANGELOG.md](CHANGELOG.md); milestone notes:
[RELEASE_NOTES.md](RELEASE_NOTES.md).

## What RC1 is

A governance-gated, working platform prepared to production quality — not a blueprint. It bundles the
FastAPI `core-api` and the Next.js PWA, with reproducible builds, verified installation, and complete
operational documentation. Real child-facing operation remains behind human governance gates
(consent / DPIA / safeguarding).

## Capabilities in RC1

- **Learning Intelligence** — sessions, BKT mastery, half-life spacing, misconception detection;
  templated (no-LLM) AI Teacher (curriculum-grounded, explainable).
- **Curriculum Studio** — author → staged review → publish workflow (provenance-gated, original
  content only); Grade-4 mathematics package.
- **Offline** — PWA + service worker + IndexedDB; Ed25519-signed lesson packages; durable, idempotent
  sync (no double-count, no lost updates).
- **Guardian Portal** — read-only aggregate of a linked child's progress, streaks, attendance,
  weekly summary, interventions, AI-Teacher activity, achievements, and offline-sync status.
- **Operations** — kill switch, `/v1/ops/status` monitoring (golden signals), health/readiness,
  Prometheus metrics, structured PII-redacted logging, security response headers, exact-origin CORS.

## RC1 release-quality changes

- **Reproducible builds** — pinned `services/core-api/requirements.lock` and
  `apps/web/package-lock.json`; the Dockerfile installs the exact pinned closure (`-r
  requirements.lock` then `--no-deps .`). A rebuild yields identical versions.
- **Dependency audit** — removed six never-imported runtime packages (pydantic-settings,
  python-json-logger, opentelemetry-api/sdk, prometheus-client, pyjwt); the config, logging, metrics,
  and JWT layers are pure-stdlib. Clean-venv boot verified with the removed packages absent.
- **License reconciliation** — metadata (pyproject, package.json, all OpenAPI contracts) previously
  asserted **MIT** while the authoritative `LICENSE` states the code license is an **undecided
  founding-team decision**. Metadata is corrected to reflect "proprietary — license undecided; see
  LICENSE." **Ratifying the license remains an open human decision** (see checklist).
- **Documentation** — README updated from "pre-code blueprint" to the working system; new RC guides
  (install, deploy, operations) covering build/deploy/migrate/health, backup, restore, upgrade, and
  troubleshooting; stale "M1 walking skeleton" descriptions removed from package metadata + root
  contract.
- **Verification** — full quality gates, integration/adversarial tests, browser validation, and the
  synthetic pilot simulator run green (see [RC1_CHECKLIST.md](RC1_CHECKLIST.md)).

## Versioning

- Project milestone: RC1 (this release). Milestone history in [VERSION.md](VERSION.md).
- `taleem-core` package artifact version: `0.1.0` (bumped independently of the milestone, per
  VERSION.md); the API reports this at `/health` and `/v1/ops/status`.

## Known limitations (not defects; carried into the pilot)

- **Governance gates (M-Gov / M-Safe)** — consent, DPIA, child-safe auth, and a live safeguarding
  drill are human approvals required before any real child uses the platform.
- **License ratification** — an open founding-team decision (metadata now honestly reflects
  "undecided").
- **Auth is the documented HS256 dev stub** — no `jti`; production child-safe auth (JWKS/KMS) is
  governance-scoped. Tokens must be rotated and short-lived until then.
- **Single-instance operational state** — session store and the sync idempotency cache are
  process-local (bounded); horizontal scaling needs a shared store first. Attempt idempotency is
  already durable via the evidence table. The kill switch is process-local (signal each worker).
- **Edge concerns** — TLS and rate limiting are expected at the gateway, not in the app.
- **Content + audio** — beyond the Grade-4 package, curriculum authoring/expert review and Urdu audio
  recording are human content work.
- **In-memory SQLite dev default is not concurrency-safe** — production must use PostgreSQL (the app
  fails closed if unset in production).
