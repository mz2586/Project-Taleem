# Railway Deployment

Deploy Project Taleem RC1 on Railway: a **backend** service (FastAPI, Docker), a **frontend** service
(Next.js, Docker), and a **PostgreSQL** plugin. HTTPS is automatic on Railway (`*.up.railway.app`).
Deployment-only wiring — no application changes.

## What was fixed for Railway (root causes)

1. **Backend build failed** — the Dockerfile passed `pip install --require-hashes=false`, but
   `--require-hashes` is a boolean flag; modern pip (26.x) rejects a value → build error. Removed the
   flag. (This also broke Render/Koyeb Docker builds.)
2. **No dynamic port / no migrations** — the image bound a fixed `8000` and never migrated, so
   Railway's health check (against its injected `$PORT`) never passed. Added
   `services/core-api/docker-entrypoint.sh`: it normalises `DATABASE_URL` → `postgresql+psycopg://`,
   runs `alembic upgrade head`, then serves on `$PORT`. Verified end-to-end against PostgreSQL.
3. **No Railway config** — added `railway.json` to each service (Dockerfile builder + health check).

## Service setup (Railway dashboard)

Railway monorepo = one service per app, each with a **Root Directory**.

### PostgreSQL

Project → **New → Database → PostgreSQL**. Railway exposes `DATABASE_URL` for reference.

### Backend service — `taleem-api`

| Setting | Value |
| --- | --- |
| Source | GitHub `mz2586/Project-Taleem`, branch `main` |
| **Root Directory** | `services/core-api` |
| Builder | Dockerfile (auto-detected via `railway.json`) |
| Health check path | `/health` (set via `railway.json`) |

**Variables** (Service → Variables):

| Key | Value |
| --- | --- |
| `DATABASE_URL` | reference the Postgres: `${{Postgres.DATABASE_URL}}` |
| `TALEEM_ENV` | `production` |
| `TALEEM_JWT_DEV_SECRET` | a strong value — `openssl rand -hex 32` |
| `TALEEM_OFFLINE_SIGNING_SEED` | 32-byte hex — `openssl rand -hex 32` (different from the JWT one) |
| `TALEEM_OFFLINE_SIGNING_KEY_ID` | `prod-ed25519-1` |
| `TALEEM_CORS_ALLOWED_ORIGINS` | the frontend URL (set after the frontend deploys) |

> With `TALEEM_ENV=production` the app **fails closed** unless the two secrets above are set — so set
> them, or the container will exit on boot. `DATABASE_URL` is required for migrations.

After it deploys, note the backend URL, e.g. `https://taleem-api-production.up.railway.app`, and
verify `…/health` → `{"status":"ok"}`.

### Frontend service — `taleem-web`

| Setting | Value |
| --- | --- |
| Source | same repo, branch `main` |
| **Root Directory** | `apps/web` |
| Builder | Dockerfile (via `railway.json`) |
| Health check path | `/` |

**Variables**:

| Key | Value |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | the backend URL from above (e.g. `https://taleem-api-production.up.railway.app`) |

> `NEXT_PUBLIC_API_URL` is inlined at **build** time; Railway passes service variables to the Docker
> build, and the frontend `Dockerfile` declares `ARG NEXT_PUBLIC_API_URL`. If you change it, redeploy
> (rebuild) the frontend.

### Wire CORS

Set the backend's `TALEEM_CORS_ALLOWED_ORIGINS` to the exact frontend URL (e.g.
`https://taleem-web-production.up.railway.app`) and redeploy the backend.

## Verification

- [ ] Backend build succeeds (no pip error); deploy **healthy**; logs show `applying migrations…`
- [ ] `GET https://taleem-api-*.up.railway.app/health` → `{"status":"ok"}`
- [ ] `GET …/health/ready` → 200
- [ ] `GET …/metrics` → Prometheus text
- [ ] Postgres shows the `learning` + `curriculum_studio` schemas (migrations succeeded)
- [ ] Frontend build succeeds; deploy healthy; `https://taleem-web-*.up.railway.app/` loads
- [ ] Browser `/guardian` reaches the API over CORS (no CORS error)

## Note

The portals authenticate with a dev JWT stub signed by `TALEEM_JWT_DEV_SECRET` (a backend secret), so
authenticated portal data needs the governance-gated child-safe auth flow. Health, metrics, CORS, and
page loads work regardless — this is the documented governance gate, not a deployment defect.
