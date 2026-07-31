# RC1 Installation Guide

How to install Project Taleem RC1 — locally (one command) and for production — and how to verify it
from a clean machine. Companion docs: [RC1_DEPLOYMENT_GUIDE.md](RC1_DEPLOYMENT_GUIDE.md),
[RC1_OPERATIONS_GUIDE.md](RC1_OPERATIONS_GUIDE.md).

## Prerequisites

| Tool | Version | Used for |
| --- | --- | --- |
| Docker + Docker Compose | recent | local stack, production image |
| Python | 3.12 | backend without Docker, tests |
| Node.js | ≥ 20 | web app |
| PostgreSQL | 16 | production database (Compose provides one locally) |

Reproducibility: the backend runtime is pinned in `services/core-api/requirements.lock`; the web app
in `apps/web/package-lock.json`. Fresh installs pull identical versions.

## Local install — one command

```bash
make up
```

This builds the `core-api` image and starts Postgres + the API via `docker-compose.yml`. Migrations
(`alembic upgrade head`) run automatically before the API serves. Verify:

```bash
curl -s http://localhost:8000/health        # {"status":"ok","version":"0.1.0"}
curl -s http://localhost:8000/health/ready   # {"status":"ok",...}
```

Tear down: `make down` (removes the volume).

### Web app (local)

```bash
cd apps/web
npm ci                                        # reproducible install from package-lock.json
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev   # http://localhost:3000
```

The student, guardian, and studio surfaces live under `/student`, `/guardian`, `/studio`. In dev the
portals use a synthetic JWT stub supplied via `NEXT_PUBLIC_DEV_*` env vars (no real identities).

## Backend without Docker (development)

```bash
make install     # creates services/core-api/.venv and installs runtime + dev deps
make migrate     # apply migrations (needs a Postgres at CS_DATABASE_URL)
make run         # uvicorn with reload
```

## Production install (reproducible container)

The production runtime is the pinned container image. Build it:

```bash
docker build -t taleem/core-api:rc1 services/core-api
```

The multi-stage build installs the exact pinned closure (`pip install -r requirements.lock`) then the
app (`pip install --no-deps .`), runs as a non-root user, and includes the Alembic migrations. Run it
against a real PostgreSQL, supplying real secrets (the app **fails closed** on default secrets in
production):

```bash
docker run -d --name taleem-core-api -p 8000:8000 \
  -e TALEEM_ENV=production \
  -e TALEEM_DATABASE_URL="postgresql+psycopg://USER:PASS@DBHOST:5432/taleem" \
  -e CS_DATABASE_URL="postgresql+psycopg://USER:PASS@DBHOST:5432/taleem" \
  -e TALEEM_JWT_DEV_SECRET="<strong-random-secret>" \
  -e TALEEM_OFFLINE_SIGNING_SEED="<32-byte-hex-ed25519-seed>" \
  -e TALEEM_CORS_ALLOWED_ORIGINS="https://app.taleem.example" \
  taleem/core-api:rc1 \
  sh -c "alembic upgrade head && uvicorn taleem_core.main:app --host 0.0.0.0 --port 8000"
```

The web app is built separately (`npm ci && npm run build` in `apps/web`, with `NEXT_PUBLIC_API_URL`
baked at build time) and served by any static/SSR host or `npm start`.

> **Production secrets are mandatory.** With `TALEEM_ENV=production` and default/unset
> `TALEEM_JWT_DEV_SECRET`, `TALEEM_DATABASE_URL`, or `TALEEM_OFFLINE_SIGNING_SEED`, startup raises
> `InsecureConfigurationError` and the process refuses to boot. This is intentional — see the
> operations guide.

## Verify from a clean machine

```bash
# Backend, no Docker, reproducible closure only:
python3 -m venv /tmp/taleem && . /tmp/taleem/bin/activate
pip install -r services/core-api/requirements.lock
pip install --no-deps ./services/core-api
python -c "from taleem_core.main import create_app; from taleem_core.platform.config import Settings; \
  print('routes:', len(create_app(Settings(database_url='')).routes))"   # -> routes: 16

# Full stack:
make up && curl -s localhost:8000/health

# Synthetic end-to-end (drives the real app, exits non-zero on failure):
make simulate
```

## Environment variables

| Variable | Where | Purpose |
| --- | --- | --- |
| `TALEEM_ENV` | api | `local` \| `production`; production enforces real secrets |
| `TALEEM_DATABASE_URL` | api | app runtime PostgreSQL URL (empty ⇒ in-memory SQLite, dev only) |
| `CS_DATABASE_URL` | alembic | migration target PostgreSQL URL |
| `TALEEM_JWT_DEV_SECRET` | api | HS256 signing secret (dev stub; production must override) |
| `TALEEM_OFFLINE_SIGNING_SEED` | api | Ed25519 seed (hex) for offline package signing |
| `TALEEM_CORS_ALLOWED_ORIGINS` | api | CSV of exact allowed browser origins (never `*`) |
| `TALEEM_GUARDIAN_LINKS` | api | guardian→children associations (software layer; consent is governance) |
| `NEXT_PUBLIC_API_URL` | web (build) | API base URL, inlined at build time |
| `NEXT_PUBLIC_DEV_*` | web (build) | dev auth stub (student/guardian ref + token) |
