# Deployment Readiness Report

**Date:** 2026-09-06 · **Commit:** `7982199` (+ 2 uncommitted doc changes) · **Branch:** `main`
**Scope:** Inspection and planning only. **Nothing was deployed. No cloud resource was created,
modified, or deleted. Railway was not touched. No Docker container, image, volume, or database
belonging to any project was altered.**

---

## 1. Release gates — GREEN

`make gates` passes end to end (exit 0, "All gates passed"):

| Gate | Result |
| --- | --- |
| `ruff check src tests` | All checks passed |
| `black --check src tests` | 151 files unchanged |
| `mypy` (strict) | No issues in 113 source files |
| `pytest --cov --cov-fail-under=85` | **258 passed, 8 skipped**, coverage **96.19 %** (122.6 s) |
| Web `tsc --noEmit` | Clean |
| Web `vitest` | **90 passed / 90**, 21 files |
| `redocly lint` (8 contracts) | Valid — 21 non-blocking warnings |
| `markdownlint-cli2` (199 files) | **0 errors** |

Supplementary, run separately:

| Check | Result |
| --- | --- |
| Backend against real PostgreSQL 16 | **266 passed / 0 skipped / 0 failed** |
| Alembic reversibility (`upgrade head` → `downgrade base` → `upgrade head`) | Pass |
| `next build` | 13/13 pages |
| Pilot 0 simulator (20 students, offline, fault injection) | PASS (exit 0) |

**What was fixed to get here:** the 4 markdownlint errors in
`STAGING_PRODUCTION_VALIDATION_2026-08-03.md` (2 × MD034 bare URLs on line 4 → autolinks;
2 × MD022 headings missing a following blank line), plus MD029 ordered-list-prefix errors introduced
by the new `CURRENT_PROJECT_STATUS.md` (its cross-section 1–17 blocker numbering was converted to
bulleted `**n.**` items so the continuous priority numbering survives). **No application code, test,
contract, or configuration file was modified** — documentation only.

---

## 2. Repository state

| Item | Value |
| --- | --- |
| Branch | `main`, tracking `origin/main` |
| HEAD | `7982199` — identical on GitHub (0 ahead / 0 behind after `git fetch`) |
| Tags | 13 local, **13 on the remote — all pushed**, none missing |
| Uncommitted | **2 files** — `STAGING_PRODUCTION_VALIDATION_2026-08-03.md` (modified, +3/−1) and `CURRENT_PROJECT_STATUS.md` (untracked) |
| Local-only secrets | **None** — no `.env*` file exists anywhere in the tree |
| Regenerable artefacts | `.venv` 167 MB, `node_modules` 276 MB, `.next` 72 MB (515 MB of the 550 MB total) |

**Until those 2 files are committed and pushed, GitHub's Docs CI stays red.** The gates are green on
this machine; the remote has not yet seen the fix.

---

## 3. Deployment assets already in the repository

| Asset | State |
| --- | --- |
| `services/core-api/Dockerfile` | Multi-stage, non-root, pinned `requirements.lock`, ships Alembic config + migrations, `HEALTHCHECK`, `ENV TALEEM_ENV=production`, binds `$PORT` |
| `services/core-api/docker-entrypoint.sh` | **Platform-agnostic**: normalises `DATABASE_URL` → `postgresql+psycopg://`, waits up to 60 s for the DB, runs `alembic upgrade head`, execs uvicorn on `$PORT` |
| `apps/web/Dockerfile` | Multi-stage, non-root, Next.js **standalone** output, `NEXT_PUBLIC_API_URL` as a build arg, binds `$PORT`/`HOSTNAME` |
| `apps/web/next.config` | `output: "standalone"` confirmed |
| `.dockerignore` | Present for both services |
| `render.yaml` | Render Blueprint — DB + backend + frontend |
| `KOYEB_NEON_DEPLOYMENT.md` | Step-by-step Koyeb + Neon guide |
| `services/core-api/railway.json`, `apps/web/railway.json` | Railway service configs |
| `docker-compose.yml` | Local Postgres + Redis + core-api |
| `infra/terraform/` | Scaffold, unapplied |

The container plumbing is genuinely good: the entrypoint alone makes the backend deployable on
Railway, Render, Koyeb, Fly, or any PaaS that injects `PORT` and `DATABASE_URL`, with no code change.

---

## 4. 🔴 Blocking defect in BOTH prepared blueprints — they will not boot

**`render.yaml` and `KOYEB_NEON_DEPLOYMENT.md` both predate the EdDSA authentication work
(`7982199`, 2026-08-03) and neither sets `TALEEM_JWT_SIGNING_SEED`.** Since that commit, production
signs tokens asymmetrically and `_assert_production_safe()` fails closed without a 32-byte hex
Ed25519 signing seed that differs from the offline-signing seed.

Verified by executing the real production config gate with exactly the variables each blueprint
supplies:

```text
[render.yaml + Koyeb guide env] REFUSES TO BOOT ->
  InsecureConfigurationError: refusing to start in production with insecure defaults:
  TALEEM_JWT_SIGNING_SEED is unset (production signs tokens asymmetrically, not HS256)

[same + TALEEM_JWT_SIGNING_SEED]  BOOTS OK
```

Both blueprints still set `TALEEM_JWT_DEV_SECRET`, which production now ignores (the verifier is
asymmetric-only; HS256 is refused even with a known secret). **A deployment attempted today from
either blueprint would crash-loop on startup.** The fix is one environment variable plus a
blueprint edit — small, but it must happen *before* any deploy.

Two lesser staleness items:

- The Koyeb guide's "Override the Run command" is now **unnecessary** — `docker-entrypoint.sh`
  already does the URL normalisation, DB wait, and migration it describes.
- `apps/web/railway.json` declares `startCommand: "node server.js"` while the last-running Railway
  manifest used `npx next start -p $PORT`. Repo and platform disagree.

### Correct production environment contract (verified against `platform/config.py`)

| Variable | Required | Notes |
| --- | --- | --- |
| `TALEEM_ENV=production` | ✅ | Already baked into the backend Dockerfile |
| `TALEEM_DATABASE_URL` | ✅ | Derived from `DATABASE_URL` by the entrypoint |
| **`TALEEM_JWT_SIGNING_SEED`** | ✅ | **MISSING FROM BOTH BLUEPRINTS.** 32-byte hex, `openssl rand -hex 32`, must differ from the offline seed |
| `TALEEM_OFFLINE_SIGNING_SEED` | ✅ | 32-byte hex, must not be the built-in default |
| `TALEEM_OFFLINE_SIGNING_KEY_ID` | ○ | e.g. `prod-ed25519-1` |
| `TALEEM_JWT_SIGNING_KID` | ○ | default `taleem-ed25519-1` |
| `TALEEM_JWT_ISSUER` / `TALEEM_JWT_AUDIENCE` | ○ | defaults `taleem-identity` / `taleem-core-api` |
| `TALEEM_JWT_VERIFICATION_KEYS` | ○ | `kid:hexpub,…` — needed only during key rotation |
| `TALEEM_CORS_ALLOWED_ORIGINS` | ○ | exact frontend origin; without it the browser app cannot call the API |
| `TALEEM_GUARDIAN_LINKS` | ○ | guardian→child associations |
| `NEXT_PUBLIC_API_URL` | ✅ (web) | **Build argument** — Next inlines `NEXT_PUBLIC_*` at build time |
| `TALEEM_JWT_DEV_SECRET` | ✗ | Obsolete in production — asymmetric-only since `7982199` |

---

## 5. Is Koyeb + Neon still available and suitable?

### Koyeb — ❌ NO LONGER AVAILABLE for this project

Mistral AI announced its acquisition of Koyeb on **2026-02-17**. Koyeb's own announcement states the
position plainly:

- **New users cannot access the Starter (free) plan** — they "must subscribe to one of our paid
  plans to get started" (Pro **$29/mo**, Scale **$299/mo**, or Enterprise).
- Existing organisations keep their plan for now, but the Starter plan **"will soon be removed"**,
  with no published deprecation date.
- The platform is being folded into **Mistral Compute**, pivoting to AI inference and enterprise GPU
  workloads rather than general-purpose web hosting.

`KOYEB_NEON_DEPLOYMENT.md` opens with *"Sign up… free tier… no credit card required"* — that path no
longer exists for a new account. Even setting cost aside, the strategic direction makes Koyeb a poor
place to put a multi-year education platform. **Recommendation: abandon the Koyeb half of this plan.**

Two further mismatches that were already true: Koyeb's free tier allows only **one** free web service
per organisation (Taleem needs two), on **0.1 vCPU / 512 MB**; and Koyeb's own free Postgres is
capped at **5 active hours**, which is why the guide correctly reached for Neon instead.

### Neon — ✅ STILL AVAILABLE AND GENUINELY SUITABLE

Neon was acquired by **Databricks (May 2025)** and the free plan *improved* afterwards. Current free
plan: **0.5 GB storage**, **100 compute-hours/month**, autoscaling to 2 CU, scale-to-zero always on,
10 branches, no credit card.

Fit for Taleem: **good.** The schema is two Alembic migrations over curriculum and learning tables —
metadata and event rows, no blobs, no media (audio is referenced, never stored in Postgres).
0.5 GB is ample for a Pilot-0-scale dataset. The one thing to watch: **scale-to-zero versus the
readiness probe.** If a platform health check hits `/health/ready` every 30 s and that probe touches
the database, the compute never idles and 100 CU-hours (~4.2 days of always-on) is consumed in under
a week. Point liveness checks at `/health`, let `/health/ready` be polled sparingly, and Neon stays
comfortably free.

**Verdict: keep Neon, drop Koyeb.**

---

## 6. Hosting options compared

| Option | Cost | Cold start | Durable DB | Effort | Notes |
| --- | --- | --- | --- | --- | --- |
| **Railway Hobby + Railway Postgres** | **~$5–12/mo** | None | ✅ | **Lowest** — config already in repo and previously validated live | No free tier; $5/mo includes $5 usage |
| **Render free + Neon free** | **$0** | ~50–60 s after 15 min idle | ✅ (Neon) | Medium — must edit `render.yaml` to drop its own DB | Render's *own* free Postgres **expires 30 days after creation**, then is deleted — unusable for durable data |
| **Render free + Neon + Cloudflare Pages** | **$0** | Backend only | ✅ | Higher — OpenNext adapter migration | Cloudflare free **permits commercial use**; 12 of 13 frontend routes are already static |
| Vercel Hobby (frontend) | $0 | None | n/a | Low | ⚠️ **Hobby prohibits commercial use** — Taleem is a commercial venture, so this is a licensing risk, not a fit |
| Koyeb + Neon | n/a | — | ✅ | — | ❌ Free tier closed to new users; Starter being removed |

---

## 7. Recommendation

**Deploy on Railway Hobby ($5/month) with Railway's own PostgreSQL, and keep Neon in reserve.**

Why, given the brief asked for low-cost/free:

1. **It is the only stack already proven end-to-end on this codebase.** The 2026-08-03 validation ran
   43/43 live behavioural checks against exactly this configuration, including confirmed PostgreSQL
   persistence and migrations. Both `railway.json` files exist. The failure that took it down was
   trial credit expiring — not a technical defect.
2. **$5/month is below the cost of the rework.** The $0 alternative needs a `render.yaml` rewrite, an
   external Neon database, a second host for the frontend, and re-validation — several hours of work
   plus a permanent ~1-minute cold start on every visit after idle, to save about sixty dollars a year.
3. **No cold starts** matters for an audio-first product aimed at children on poor connections.
4. **Rollback is trivial** — if Railway disappoints, the same containers move to Render or Fly
   unchanged, because `docker-entrypoint.sh` is platform-agnostic.

**Choose the $0 stack (Render free + Neon free) instead if** the project must not carry any recurring
charge at all. It is a legitimate option — just budget the rework and accept the cold starts.

**Do not use** Koyeb (free tier gone, platform pivoting away) or Vercel Hobby (commercial-use
prohibition).

---

## 8. Infrastructure that must run in the cloud

Exactly three long-lived components, plus secrets:

| # | Component | Spec | Notes |
| --- | --- | --- | --- |
| 1 | **Backend** — `taleem-api` | Docker from `services/core-api/Dockerfile`; 256–512 MB RAM, 0.1–0.5 vCPU; HTTP on `$PORT`; health `/health` | Runs `alembic upgrade head` on every start (idempotent) |
| 2 | **Frontend** — `taleem-web` | Docker from `apps/web/Dockerfile` (Next.js standalone); 256–512 MB RAM; health `/` | Needs `NEXT_PUBLIC_API_URL` as a **build arg** — rebuild required if the API URL changes |
| 3 | **Database** — PostgreSQL 16 | 1 GB storage is generous; ~0.25 vCPU | The only stateful component. Two Alembic migrations, verified reversible |

Plus: **HTTPS** (automatic on every candidate platform), **egress** (trivial at pilot scale), and
**four secrets** injected as environment variables — `TALEEM_JWT_SIGNING_SEED`,
`TALEEM_OFFLINE_SIGNING_SEED`, `TALEEM_OFFLINE_SIGNING_KEY_ID`, `TALEEM_CORS_ALLOWED_ORIGINS`.

**Not required:** Redis (in `docker-compose.yml` for local convenience; nothing in the app depends on
it), object storage (no uploads exist), a CDN, a queue, a KMS (needed later for real key custody),
and any GPU or LLM service (the AI Teacher is templated and the `LLMGateway` port is unwired).

---

## 9. Pre-deployment checklist

- [ ] Commit and push the 2 pending documentation files → turns GitHub Docs CI green
- [ ] **Add `TALEEM_JWT_SIGNING_SEED` to `render.yaml` and `KOYEB_NEON_DEPLOYMENT.md`** (or whichever
      blueprint is used) — otherwise the backend crash-loops on boot
- [ ] Generate two distinct 32-byte hex seeds (`openssl rand -hex 32`) and store them in the
      platform's secret store, never in git
- [ ] Reconcile `apps/web/railway.json` `startCommand` with reality
- [ ] Choose the platform and provision the three components above
- [ ] Set `TALEEM_CORS_ALLOWED_ORIGINS` to the exact frontend origin after the frontend URL exists
- [ ] Rebuild the frontend with `NEXT_PUBLIC_API_URL` pointing at the live backend
- [ ] Re-run the live validation checks from `STAGING_PRODUCTION_VALIDATION_2026-08-03.md` §3
- [ ] Tag `0.12.0` and reconcile `VERSION.md` with `RELEASE_NOTES.md`

**Still true regardless of hosting:** no LLM, no published curriculum, no audio, no child-safe
consent/login flow, and no M-Gov / M-Safe sign-off. A deployment today publishes a *technically
sound but empty* system. **No real child data may be entered into it.**

---

*Sources for the platform findings: Koyeb's own acquisition announcement and pricing FAQ, Render's
free-tier documentation, Neon and Databricks pricing pages, Vercel's Hobby plan terms, and
Cloudflare Workers/Pages documentation — all checked 2026-09-06.*
