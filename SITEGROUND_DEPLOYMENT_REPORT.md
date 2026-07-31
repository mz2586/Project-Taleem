# SiteGround Deployment Report

**Outcome: RC1 cannot be deployed to SiteGround. The target platform is architecturally
incompatible with the RC1 stack, and no Project Taleem SiteGround account exists.** No deployment
was performed and no changes were made to any server. This report documents what was attempted, the
first-hand evidence, and the correct path forward — it does not fabricate a working deployment.

Date: 2026-07-31.

## Deployment URL

**None.** No temporary staging URL or subdomain was created, because the deployment is not possible
on SiteGround (see blockers below). Presenting a URL would be misleading.

## What was attempted

1. Searched the repository and environment for a Project Taleem SiteGround account, deploy scripts,
   or credentials — **none exist**.
2. Found one SiteGround SSH host in the local config: `alphacom` →
   `giowm1357.siteground.biz`. This is the **Atlas Computers / Alphacom** account — a separate,
   unrelated B2B (computer-hardware) client's live shared hosting, **not** Project Taleem
   infrastructure.
3. Ran a **read-only, non-destructive** capability probe of that SiteGround environment (runtime and
   database availability only — no writes, no files created, nothing deployed) to establish the
   platform's actual capabilities first-hand.

I deliberately did **not** deploy Project Taleem onto the Alphacom account: it would mix two
unrelated clients' infrastructure and risk an unrelated live storefront, and it does not belong to
this project.

## First-hand evidence (read-only probe of the SiteGround host)

```text
host    : Linux giowm1357.siteground.biz  (SiteGround managed shared hosting)
python  : Python 3.14.6            # RC1 requires 3.12; this is CLI Python, not an app-server runtime
psql    : present (client only)
postgres: NONE — no PostgreSQL server binaries   # SiteGround provides MySQL, not PostgreSQL
mysql   : present                                 # RC1 does not support MySQL
node    : v22.23.1 (CLI only)                      # no persistent Node SSR server on shared hosting
docker  : NOT present                              # cannot run the RC1 container image
php     : PHP 8.2.33                                # what SiteGround shared hosting actually serves
```

## Blocking deployment issues (why SiteGround cannot host RC1)

| # | Requirement (from the mission) | SiteGround shared hosting | Verdict |
| --- | --- | --- | --- |
| 1 | **PostgreSQL** | No PostgreSQL server; MySQL/MariaDB only (probe: no `postgres`/`pg_ctl` binaries) | **Hard blocker.** RC1 uses `postgresql+psycopg`, two PostgreSQL schemas (`learning`, `curriculum_studio`), and Alembic migrations targeting PostgreSQL. Porting to MySQL is a re-architecture, which RC1 forbids. |
| 2 | **Backend (FastAPI/ASGI)** | No persistent process hosting; Python only via Passenger (WSGI, limited); no Docker | **Hard blocker.** uvicorn/FastAPI is an always-on ASGI service; shared hosting cannot run it. |
| 3 | **Frontend (Next.js)** | No persistent Node server; dynamic routes (`/guardian/children/[ref]`) need SSR | **Blocker.** Only a static shell could be served, and it is non-functional without the backend. |
| 4 | **Monitoring / Kill switch / Health endpoint** | These are endpoints on the running FastAPI process | **Blocker.** No backend process ⇒ no `/health`, `/metrics`, `/v1/ops/*`. |
| 5 | **HTTPS / static / offline assets** | SiteGround can serve static files over HTTPS | Possible in isolation — but useless without (1)–(4). |
| 6 | **Account** | Only an unrelated client's (Alphacom) account is available | **Blocker.** No Project Taleem SiteGround account. |

SiteGround's higher tiers ("Cloud Hosting") are still **managed** — no root, no Docker, no PostgreSQL,
no arbitrary long-running services — so upgrading the plan would not remove blockers 1–4.

## Verification checklist

Nothing could be deployed, so **no verification item passed**. Each is blocked, not failed:

| Check | Status | Reason |
| --- | --- | --- |
| ✓ Application starts | ⛔ blocked | no ASGI/process hosting; no Docker |
| ✓ Database connected | ⛔ blocked | no PostgreSQL on SiteGround |
| ✓ Migrations applied | ⛔ blocked | no PostgreSQL target |
| ✓ API responding | ⛔ blocked | backend cannot run |
| ✓ Frontend loads | ⛔ blocked | only a dead static shell is possible; no backend |
| ✓ Guardian Portal works | ⛔ blocked | needs the backend |
| ✓ Student Portal works | ⛔ blocked | needs the backend |
| ✓ AI Teacher works | ⛔ blocked | needs the backend |
| ✓ Offline package downloads | ⛔ blocked | signed by the backend |
| ✓ Sync works | ⛔ blocked | needs the backend |
| ✓ Monitoring works | ⛔ blocked | backend endpoint |
| ✓ Kill switch works | ⛔ blocked | backend endpoint |

> RC1 itself is verified operational on a **compatible** platform — see
> [END_TO_END_VALIDATION_REPORT.md](END_TO_END_VALIDATION_REPORT.md),
> [GUARDIAN_PORTAL_REPORT.md](GUARDIAN_PORTAL_REPORT.md), and [RC1_CHECKLIST.md](RC1_CHECKLIST.md):
> real PostgreSQL 16 + uvicorn + browser, all workflows green, pilot simulator PASS. The problem is
> the target host, not the application.

## Options considered and rejected

- **Static frontend export to SiteGround** — SiteGround can serve static files, but the Next.js app
  needs the backend API for every action (auth, sessions, guardian data, sync). A static shell with
  no backend fails every verification item and would be a dead page presented as a "deployment." Not
  done.
- **Deploy onto the Alphacom SiteGround account** — inappropriate (unrelated client, live storefront
  risk) and still blocked by items 1–4. Not done.
- **Re-architect RC1 to MySQL + WSGI/PHP + static export** — explicitly out of scope (RC1: "do not
  redesign architecture"), and it would no longer be RC1.

## Remaining deployment issues

The single remaining issue is **the target platform**: SiteGround shared hosting cannot run RC1's
PostgreSQL + ASGI + SSR stack. RC1 needs a host that provides:

- a PostgreSQL 16 database (managed or self-hosted),
- a container runtime **or** a persistent Python ASGI process (for `taleem/core-api`),
- a way to serve the Next.js app (Node SSR host, or a static/CDN host + a reachable API origin),
- HTTPS + a reverse proxy for TLS and rate limiting.

Concrete compatible targets (the RC1 deployment guide already covers this exact flow): a small
cloud VM or container platform (e.g. a Docker host / Kubernetes / a PaaS supporting containers) with
a managed PostgreSQL. Deployment steps, environment variables, migrations, health checks, and the
smoke test are documented in [RC1_DEPLOYMENT_GUIDE.md](RC1_DEPLOYMENT_GUIDE.md) and
[RC1_INSTALLATION_GUIDE.md](RC1_INSTALLATION_GUIDE.md); they were verified this cycle against real
PostgreSQL 16.

**Recommendation:** provision a SiteGround-alternative that supports PostgreSQL + containers (or a
persistent ASGI runtime), then follow `RC1_DEPLOYMENT_GUIDE.md`. If SiteGround must be used, it can
host **only** a static marketing/landing page — not the RC1 application.

## Environment variables required (for a compatible host)

Unchanged from the RC1 guides — reproduced for convenience:

| Variable | Purpose |
| --- | --- |
| `TALEEM_ENV=production` | enforces real secrets (fails closed on defaults) |
| `TALEEM_DATABASE_URL` | app PostgreSQL URL (`postgresql+psycopg://…`) |
| `CS_DATABASE_URL` | migration target PostgreSQL URL |
| `TALEEM_JWT_DEV_SECRET` | HS256 signing secret (strong random) |
| `TALEEM_OFFLINE_SIGNING_SEED` | 32-byte hex Ed25519 seed for offline package signing |
| `TALEEM_CORS_ALLOWED_ORIGINS` | exact web origin(s), never `*` |
| `TALEEM_GUARDIAN_LINKS` | guardian→children associations (software layer) |
| `NEXT_PUBLIC_API_URL` | API base URL, baked into the web build |

## Screenshots

None — there is no deployed environment to screenshot. Fabricating one would be dishonest. Live
screenshots of RC1 running on a compatible PostgreSQL-backed stack (Guardian Portal, student flow)
are in [GUARDIAN_PORTAL_REPORT.md](GUARDIAN_PORTAL_REPORT.md) and this session's validation.

## Summary

- No changes were made to any server; only a read-only capability probe was run.
- SiteGround shared hosting cannot host RC1 (no PostgreSQL, no Docker, no persistent ASGI/Node).
- No Project Taleem SiteGround account exists; the only SiteGround access is an unrelated client's.
- **The SiteGround deployment is not achievable as specified.** RC1 is deployment-ready on a
  PostgreSQL-capable container/VM host per `RC1_DEPLOYMENT_GUIDE.md`.
