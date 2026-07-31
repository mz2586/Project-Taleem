# RC1 Deployment Guide

Build → deploy → migrate → start → health-check, and the architecture it deploys. For install
mechanics see [RC1_INSTALLATION_GUIDE.md](RC1_INSTALLATION_GUIDE.md); for day-2 operations see
[RC1_OPERATIONS_GUIDE.md](RC1_OPERATIONS_GUIDE.md).

## What gets deployed

| Component | Artifact | Notes |
| --- | --- | --- |
| `core-api` | `services/core-api/Dockerfile` → container | FastAPI (ASGI/uvicorn), non-root, pinned deps, bundled Alembic migrations |
| Database | PostgreSQL 16 | authoritative schema is the Alembic migrations (two schemas: `learning`, `curriculum_studio`) |
| Web PWA | `apps/web` Next.js build | `NEXT_PUBLIC_API_URL` baked at build; served by SSR/static host |
| Contracts | `packages/contracts/*.yaml` | OpenAPI per surface; CI-linted; source of truth for clients |

Architecture: Clean/Hexagonal + DDD. Pure-stdlib domain (no framework imports) behind ports; FastAPI
is an edge adapter; SQLAlchemy + Alembic are the persistence adapter. Bounded contexts: `learning`,
`curriculum_studio`, `guardian`, `sync`, `ops`, `health`. Deep design: `docs/02-architecture/` (08
system, 35 deployment, 36 infrastructure) and `ARCHITECTURE_REVIEW.md`.

## 1. Build (reproducible)

```bash
docker build -t taleem/core-api:rc1 services/core-api
```

The image pins the full runtime closure from `requirements.lock`, so a rebuild yields identical
versions regardless of upstream releases. Web:

```bash
cd apps/web && npm ci && NEXT_PUBLIC_API_URL=https://api.taleem.example npm run build
```

## 2. Provision the database

A managed PostgreSQL 16 instance. Create the database and a least-privilege application role. Record
its connection string for `TALEEM_DATABASE_URL` and `CS_DATABASE_URL`.

## 3. Migrate

Migrations are bundled in the image and are the authoritative schema (the app never `create_all()`s
on PostgreSQL). Reversibility is CI-verified (`upgrade → downgrade → upgrade`).

```bash
docker run --rm \
  -e CS_DATABASE_URL="postgresql+psycopg://USER:PASS@DBHOST:5432/taleem" \
  taleem/core-api:rc1 alembic upgrade head
```

## 4. Start services

Supply real secrets (production fails closed on defaults):

```bash
docker run -d --name taleem-core-api -p 8000:8000 \
  -e TALEEM_ENV=production \
  -e TALEEM_DATABASE_URL="postgresql+psycopg://USER:PASS@DBHOST:5432/taleem" \
  -e TALEEM_JWT_DEV_SECRET="<strong-random>" \
  -e TALEEM_OFFLINE_SIGNING_SEED="<32-byte-hex>" \
  -e TALEEM_CORS_ALLOWED_ORIGINS="https://app.taleem.example" \
  taleem/core-api:rc1
```

The container `CMD` runs uvicorn; put migrations either as a one-shot job (step 3) or prepend
`alembic upgrade head &&` to the command. Front the API with a reverse proxy / gateway that
terminates TLS and applies rate limiting (the app relies on the edge for throttling).

## 5. Health checks

| Probe | Endpoint | Healthy | Use |
| --- | --- | --- | --- |
| Liveness | `GET /health` | 200 | restart target |
| Readiness | `GET /health/ready` | 200 (else 503) | traffic gate |
| Metrics | `GET /metrics` | 200 (Prometheus text) | scrape target |
| Ops status | `GET /v1/ops/status` | 200 (auth: system/mentor) | dashboard / alerts |

The image also declares a container `HEALTHCHECK` against `/health`. Post-deploy smoke:

```bash
curl -fsS https://api.taleem.example/health
curl -fsS https://api.taleem.example/health/ready
make simulate          # synthetic end-to-end journey against a running build
```

## CORS + web origin

The API is credentialed (bearer JWT), so CORS uses an **exact-origin allowlist**, never `*`. Set
`TALEEM_CORS_ALLOWED_ORIGINS` to the web app's exact origin(s). A missing/incorrect value makes the
browser block every API call.

## Rollout & rollback

- **Rollout**: build a new tagged image, run migrations, deploy, smoke-test, shift traffic.
- **Rollback**: migrations are reversible (`alembic downgrade`), but prefer forward-only in
  production; to revert code, redeploy the previous image tag. Coordinate any `downgrade` with a
  database backup (see operations guide → Backup/Restore).
- **Kill switch**: during an incident, engage the operator kill switch to halt child-facing traffic
  (503) while health/metrics/ops stay up — see the operations guide.

## Deployment checklist (abridged — full list in RC1_CHECKLIST.md)

- [ ] Image built from `requirements.lock` (reproducible)
- [ ] Real `TALEEM_JWT_DEV_SECRET` + `TALEEM_OFFLINE_SIGNING_SEED` set (no defaults)
- [ ] `TALEEM_DATABASE_URL` / `CS_DATABASE_URL` point at managed PostgreSQL
- [ ] `alembic upgrade head` applied; schema-parity + reversibility green
- [ ] `TALEEM_CORS_ALLOWED_ORIGINS` = the web origin
- [ ] TLS + rate limiting at the edge
- [ ] `/health`, `/health/ready`, `/metrics` reachable; `make simulate` passes
- [ ] Backups configured; restore tested
