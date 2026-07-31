# Koyeb + Neon Deployment (free tier only)

Deploy Project Taleem RC1 on **free** services: **Neon** (serverless PostgreSQL) + **Koyeb**
(container web services). No paid plans, no credit card required, no application changes — only
deployment files (a frontend `Dockerfile`, a `.dockerignore`, and Next.js `output: "standalone"`).

- **Repository:** <https://github.com/mz2586/Project-Taleem> (branch `main`)
- **Backend:** `services/core-api/Dockerfile` (FastAPI; migrations on start; binds `$PORT`)
- **Frontend:** `apps/web/Dockerfile` (Next.js standalone; binds `$PORT`)
- **HTTPS:** automatic on Koyeb (`*.koyeb.app`)

Both Koyeb and Neon require you to create a free account in the browser — those are the only manual
steps. Everything in the repo is ready.

---

## Step 1 — Neon: free PostgreSQL (browser)

1. Go to **<https://neon.tech>** → **Sign up** (GitHub sign-in works; no card).
2. **Create a project** (any name, region near Koyeb's, PostgreSQL 16).
3. On the project dashboard, open **Connection Details** and copy the connection string. Use the
   **direct (unpooled)** connection for migrations — it looks like:
   `postgresql://<user>:<pass>@ep-xxxx.<region>.aws.neon.tech/<db>?sslmode=require`
   (avoid the `-pooler` host for the migration/DDL run.)
4. Keep this string — it is `DATABASE_URL` for the backend (Step 3).

---

## Step 2 — Koyeb: account + GitHub (browser)

1. Go to **<https://www.koyeb.com>** → **Sign up** (GitHub sign-in; free tier).
2. When prompted, **install the Koyeb GitHub app** and grant access to **`mz2586/Project-Taleem`**.

### CLI authentication (current 2026 method)

The API-token page **moved** — it is no longer at `app.koyeb.com/user/settings/api` (the location the
older CLI prints). Create the token under **Organization Settings → API**
(<https://app.koyeb.com/settings/api>): fill a name → **Create API Access Token** → copy it (shown
once). Then authenticate the CLI with any of:

```sh
koyeb login                       # paste the token when prompted (writes ~/.koyeb.yaml)
# or non-interactive:
export KOYEB_TOKEN="<token>"       # CLI reads this env var
koyeb whoami --token "<token>"     # or pass per-command
```

---

## Step 3 — Koyeb: backend service (FastAPI)

**Create → Web Service → GitHub → `mz2586/Project-Taleem`.** Then set:

| Field | Value |
| --- | --- |
| Branch | `main` |
| Builder | **Dockerfile** |
| Dockerfile location | `services/core-api/Dockerfile` |
| Work directory / build context | `services/core-api` |
| Instance | **Free** (Eco/Nano) |
| Port | `8000` (HTTP) |
| Health check | HTTP path `/health` |
| Service name | `taleem-api` |

**Override the Run command** (normalises the Neon URL to the psycopg dialect, migrates, then serves
on Koyeb's `$PORT`):

```sh
sh -c 'export TALEEM_DATABASE_URL=$(printf "%s" "$DATABASE_URL" | sed -E "s#^postgres(ql)?://#postgresql+psycopg://#"); export CS_DATABASE_URL="$TALEEM_DATABASE_URL"; alembic upgrade head && exec uvicorn taleem_core.main:app --host 0.0.0.0 --port ${PORT:-8000}'
```

**Environment variables:**

| Key | Value |
| --- | --- |
| `TALEEM_ENV` | `production` |
| `DATABASE_URL` | the Neon **direct** connection string from Step 1 |
| `TALEEM_JWT_DEV_SECRET` | a strong random value — run `openssl rand -hex 32` and paste |
| `TALEEM_OFFLINE_SIGNING_SEED` | a 32-byte hex — run `openssl rand -hex 32` and paste (different from the JWT one) |
| `TALEEM_OFFLINE_SIGNING_KEY_ID` | `prod-ed25519-1` |
| `TALEEM_CORS_ALLOWED_ORIGINS` | set **after** Step 4 to the frontend URL (leave blank for now) |

Click **Deploy**. Wait for the build; then note the backend URL, e.g.
`https://taleem-api-<org>.koyeb.app`. Verify:

```sh
curl -s https://taleem-api-<org>.koyeb.app/health        # {"status":"ok",...}
```

---

## Step 4 — Koyeb: frontend service (Next.js)

**Create → Web Service → same repo `mz2586/Project-Taleem`.** Then set:

| Field | Value |
| --- | --- |
| Branch | `main` |
| Builder | **Dockerfile** |
| Dockerfile location | `apps/web/Dockerfile` |
| Work directory / build context | `apps/web` |
| Instance | **Free** |
| Port | `8000` (HTTP) |
| Health check | HTTP path `/` |
| Service name | `taleem-web` |
| **Build argument** | `NEXT_PUBLIC_API_URL` = the backend URL from Step 3 (`https://taleem-api-<org>.koyeb.app`) |

> `NEXT_PUBLIC_API_URL` must be a **build argument** (Koyeb → service → *Build* settings), because
> Next inlines `NEXT_PUBLIC_*` at build time.

Click **Deploy**. Note the frontend URL, e.g. `https://taleem-web-<org>.koyeb.app`.

---

## Step 5 — wire CORS (backend ↔ frontend)

Go back to the **`taleem-api`** service → **Environment** → set:

- `TALEEM_CORS_ALLOWED_ORIGINS` = the frontend URL from Step 4 (exact origin, e.g.
  `https://taleem-web-<org>.koyeb.app`).

Save → the backend redeploys. The browser SPA can now call the API.

> If the app's run command is used (Step 3), it exports `TALEEM_CORS_ALLOWED_ORIGINS` from the env
> var you set here — no code change needed.

---

## Free-tier note (Koyeb service count)

Koyeb's free allowance may cover a limited number of services. If a second free web service is not
available, deploy **`taleem-api`** on Koyeb (it needs the database) and host the **frontend** on
another free, no-card host that supports Next.js SSR — e.g. **Cloudflare Pages** or **Vercel**
(both free) — pointing `NEXT_PUBLIC_API_URL` at the Koyeb backend. The `apps/web/Dockerfile` and
build settings above transfer directly. No paid plan is required.

---

## Verification checklist (after both are live)

- [ ] Neon project shows the database; the backend logs show `alembic upgrade head` succeeded
- [ ] `GET https://taleem-api-*.koyeb.app/health` → `{"status":"ok"}`
- [ ] `GET https://taleem-api-*.koyeb.app/health/ready` → 200
- [ ] `GET https://taleem-api-*.koyeb.app/metrics` → Prometheus text (monitoring)
- [ ] `https://taleem-web-*.koyeb.app/` loads (landing page)
- [ ] Browser: `/guardian` reaches the API over CORS (no CORS error in the console)
- [ ] HTTPS on both `*.koyeb.app` URLs

## Environment variable reference

| Variable | Service | Notes |
| --- | --- | --- |
| `TALEEM_ENV=production` | api | enforces real secrets (fails closed on defaults) |
| `DATABASE_URL` | api | Neon direct URL; run command rewrites to `postgresql+psycopg://` |
| `TALEEM_JWT_DEV_SECRET` | api | `openssl rand -hex 32` |
| `TALEEM_OFFLINE_SIGNING_SEED` | api | `openssl rand -hex 32` (32-byte hex) |
| `TALEEM_OFFLINE_SIGNING_KEY_ID` | api | `prod-ed25519-1` |
| `TALEEM_CORS_ALLOWED_ORIGINS` | api | exact frontend origin (Step 5) |
| `NEXT_PUBLIC_API_URL` | web (build arg) | backend public URL, inlined at build |

## Known note

The portals authenticate with a dev JWT stub signed by `TALEEM_JWT_DEV_SECRET` (a backend secret), so
the frontend cannot bake a matching token at build; authenticated portal data needs the
governance-gated child-safe auth flow. Services, health, metrics, and CORS work regardless — this is
the documented governance gate, not a deployment defect.
