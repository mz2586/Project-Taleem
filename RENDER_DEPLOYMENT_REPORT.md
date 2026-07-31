# Render Deployment Report

Project Taleem RC1 is prepared for Render via a Blueprint (`render.yaml`). Everything automatable is
done and pushed; the final apply is a Render-dashboard action (no Render API key is available to
automate it).

- **Repository:** <https://github.com/mz2586/Project-Taleem> (branch `main`, commit `4bd5417`)
- **Blueprint:** `render.yaml` (verified on GitHub)
- **Platform:** Render — Web Services + managed PostgreSQL 16 + automatic HTTPS (compatible, unlike
  SiteGround)

## What the Blueprint provisions

| Service | Type | Details |
| --- | --- | --- |
| `taleem-db` | PostgreSQL 16 | managed database, `databaseName: taleem`, free plan |
| `taleem-api` | Web (Docker) | `services/core-api/Dockerfile`; migrations run on start; binds `$PORT`; health `/health` |
| `taleem-web` | Web (Node) | `apps/web`; `npm ci && npm run build`; `next start -p $PORT`; health `/` |

## Verification of the Blueprint (pre-apply)

- ✅ Latest GitHub repo confirmed (`main` @ `4bd5417`; render.yaml present, 3068 bytes).
- ✅ `render.yaml` is valid YAML and structurally correct (db + api + web; cross-refs resolve).
- ✅ **Backend build** — Docker from the reproducible RC1 image (`requirements.lock`).
- ✅ **Backend start** — normalises `DATABASE_URL` → `postgresql+psycopg://`, runs
  `alembic upgrade head`, then `uvicorn … --port $PORT`.
- ✅ **Frontend build** — `NEXT_PUBLIC_API_URL="https://$API_HOST"` baked at build (API hostname
  resolved from the `taleem-api` service).
- ✅ **Frontend start** — `next start -p $PORT`.
- ✅ **Health checks** — `/health` (backend), `/` (frontend).
- ✅ **CORS** — backend `TALEEM_CORS_ALLOWED_ORIGINS="https://$WEB_HOST"` (frontend hostname); exact
  origin, never `*`.
- ✅ **HTTPS** — automatic on Render for both `*.onrender.com` services.
- ✅ **PostgreSQL** — provisioned by the Blueprint; the app fails closed if the DB URL is absent.

## Environment variables (configured by the Blueprint)

| Variable | Service | Source |
| --- | --- | --- |
| `TALEEM_ENV=production` | api | literal |
| `DATABASE_URL` | api | `fromDatabase: taleem-db.connectionString` (scheme rewritten at start) |
| `TALEEM_JWT_DEV_SECRET` | api | `generateValue` (Render) |
| `TALEEM_OFFLINE_SIGNING_SEED` | api | **`sync:false` — you set it once in the UI (32-byte hex)** |
| `TALEEM_OFFLINE_SIGNING_KEY_ID=prod-ed25519-1` | api | literal |
| `WEB_HOST` | api | `fromService: taleem-web.host` (→ CORS origin) |
| `API_HOST` | web | `fromService: taleem-api.host` (→ `NEXT_PUBLIC_API_URL`) |
| `NODE_VERSION=20` | web | literal |

## Manual step required in the Render UI (blocked here)

Render Blueprint apply needs your dashboard. Exact steps in the message accompanying this report.
The only value you must supply is `TALEEM_OFFLINE_SIGNING_SEED` — a 32-byte hex string, generated
privately with `openssl rand -hex 32` and pasted into the Render field (never committed).

## Post-apply verification checklist (run after the Blueprint deploys)

- [ ] `taleem-db` shows **Available**
- [ ] `taleem-api` build succeeds; **Live**; logs show `alembic upgrade head` then uvicorn startup
- [ ] `https://taleem-api.onrender.com/health` → `{"status":"ok",...}`
- [ ] `https://taleem-api.onrender.com/health/ready` → 200
- [ ] `taleem-web` build succeeds; **Live**
- [ ] `https://taleem-web.onrender.com/` loads (landing page)
- [ ] Browser: `https://taleem-web.onrender.com/guardian` reaches the API over CORS (no CORS error)
- [ ] `https://taleem-api.onrender.com/metrics` returns Prometheus text (monitoring)

## Known deployment notes

- **Auth for the portals:** the portals authenticate with a dev JWT stub signed by
  `TALEEM_JWT_DEV_SECRET`. Render generates that secret server-side, so the frontend cannot bake a
  matching token at build; authenticated portal data therefore requires the governance-gated
  child-safe auth flow (M-Gov) or a manual token step. The services, health, metrics, and CORS all
  work regardless. This is the documented governance gate, not a deployment defect.
- **Free plan:** Render free web services sleep on inactivity and free PostgreSQL is time-limited —
  fine for a staging URL; upgrade the plans for anything durable.
