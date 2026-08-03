# Production Validation Report — Railway Staging

**Date:** 2026-08-03  ·  **Environment:** Railway staging (`zonal-victory`, env `production`)
**Backend:** https://taleem-api-production.up.railway.app  ·  **Frontend:** https://taleem-web-production-403a.up.railway.app
**Commit at validation:** `0bc2afd` (+ live redeploys)

---

## 1. Verdict

**Zero critical defects remain.** One critical defect was found **and fixed** during this pass
(service-worker served the wrong page for every route); one hardening item was fixed (prod API docs
exposure). All automated tests pass, and 43/43 live behavioural checks pass against the deployed
instance.

**Important scope note (read this first).** Project Taleem is at milestone **M1 — a "walking
skeleton / governance-safe scaffolding"** (the app says so on its landing page, by design). The
**architecture, security, deployment, and test coverage are production-grade**, but the product is
**not yet a feature-complete production education service**. Several items on the requested checklist
describe capabilities that are intentionally **stubbed or absent at M1** — these are called out
honestly below rather than reported as "passed." "Production-ready" is therefore **qualified**: the
platform is a solid, secure, well-tested M1 foundation; it is not a finished consumer product.

---

## 2. Automated test suites (the real quality baseline)

| Suite | Result |
| --- | --- |
| Backend (`pytest`, hexagonal domain + ASGI adapters) | **243 passed, 8 skipped**, coverage **96.4%** (gate 85%) |
| Backend Postgres-gated (`test-pg`, migrations + SQL persistence) | see §7 (the 8 "skipped" above are these) |
| Frontend (`vitest`: offline engine, sync queue, chaos/crash-recovery, api client, nav model) | **90 passed** (21 files) |
| Frontend production build (`next build`) | **compiles, 13/13 pages** |

---

## 3. Live staging validation — 43/43 checks pass

Probed the deployed instance directly (HS256 dev-JWT minted with the live secret; read-only +
non-destructive — the kill-switch was never engaged).

- **Authentication enforcement (security):** no-token → 401, malformed → 401, bad-signature → 401,
  expired → 401, wrong-role → 403, cross-student IDOR → 403. ✅
- **Guardian flow:** `/v1/guardian/me`, `/dashboard`, `/children/{ref}` reachable + role-gated. ✅
- **Student flow:** all 11 read endpoints (`today, progress, homework, achievements, assessments,
  history, knowledge, notifications, recommendations, reviews, timetable`). ✅
- **AI Teacher / learning session:** full lifecycle over HTTP — create session → `:next` → `:end`
  (`capabilities`, `plan`). ✅ *(templated engine — see §5)*
- **Curriculum Studio (mentor authoring):** `hierarchy`, create draft, `:validate`, `:submit`
  (→ 422 for an incomplete draft, correct), author-cannot-publish (→ 403). ✅
- **Database persistence:** created a draft, re-fetched it in a **separate** request → survived ⇒
  **PostgreSQL persistence confirmed** (not in-memory). ✅
- **Offline:** `packages`, `signing-keys`, `POST /v1/sync/batch`. ✅
- **Ops:** `status` + `kill-switch` are role-gated (correctly 403 for a non-privileged token). ✅
- **Security headers:** `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Content-Security-Policy: default-src 'none'…`, `Referrer-Policy: no-referrer`,
  `Strict-Transport-Security: max-age=63072000; includeSubDomains`. ✅
- **CORS:** echoes the **exact** frontend origin (never `*`); unknown origins get no allow header. ✅

**Additional security probes:** HTTP → HTTPS **301**; 404 body does **not** leak a stack trace;
`DELETE /health` → **405**; malformed JSON → **422** (graceful, not 500); interactive API docs
**disabled in production** (see §4).

**Frontend:** every route returns 200 and renders its **own** localized (Urdu-first, RTL) page —
`/guardian` (Guardian portal), `/student/*` (today/homework/progress/subjects/profile/session),
`/studio` (Curriculum Studio). Mobile viewport (390×844) renders responsively. Unauthenticated data
calls degrade to the correct "offline / session expired → Try again" states (governance-gated auth).

**Light load:** 30 sequential requests, **0 errors**, p50 ≈ 530 ms (single trial replica; latency is
mostly geographic + trial-tier, not error). Heavy load testing was **deliberately not run** — the
project is on a Railway free trial and hammering it would burn credit and risk anti-abuse throttling.

---

## 4. Defects found and fixed this pass

### 🔴 CRITICAL — Service worker served the root shell for every route *(fixed)*
`apps/web/public/sw.js` used a **cache-first app-shell** strategy for navigations
(`caches.match("/")` for every `navigate` request). That pattern is for single-shell SPAs; Project
Taleem is a **multi-route Next.js app** where each route has its own server-rendered HTML + entry
chunk. Effect: once the SW installed on a first visit, **`/guardian`, `/student/*`, `/studio` all
rendered the root "M1 walking skeleton" landing page** for that user — the entire app appeared
broken. Fixed to **network-first** (correct route online; cached shell only as an offline fallback)
plus `skipWaiting` so the corrected SW takes over promptly. **Verified live:** with the SW active,
`/student/today` now renders the real student page.

### 🟡 HARDENING — Interactive API docs exposed in production *(fixed)*
`/docs`, `/redoc`, `/openapi.json` were publicly reachable. Now **disabled when
`TALEEM_ENV=production`** (still available in dev/local). Verified live: all three → 404, health 200.

Both fixes are committed (`0bc2afd`) and deployed; backend + frontend redeploys are **SUCCESS**.

---

## 5. Honest scope limitations (M1 by design — NOT defects)

These items were on the request list; here is the truthful status rather than a fabricated "pass":

- **AI Teacher — no LLM.** M1 ships a **deterministic, templated, curriculum-grounded** teaching
  runtime (`StubLLMProvider`, explicitly "NON-production"). There is **no generative AI** inference.
  The session lifecycle works and is reproducible; "AI" here means the templated decision engine.
- **Uploads — not implemented.** There are **no file-upload endpoints** (`multipart`/`UploadFile`)
  in the API. Nothing to test; the capability does not exist at M1.
- **Authentication is a dev stub.** Auth is **HS256 with a shared dev secret** (walking-skeleton
  seam). Production requires the planned **asymmetric JWKS + rotating keys + KMS** and the
  child-safe consent/login flow (FD-14). No real child accounts or child PII exist on staging (by
  design — governance gate).
- **No seeded curriculum on staging.** The live DB has **no published lessons** (seeding is a
  test/ops path, not public HTTP). Full **author → 5-gate review → publish → student-learns** chains
  end-to-end in the automated suite, but cannot be driven purely via public HTTP on the live
  instance. Guardian/student *data* screens therefore show empty/offline states until authored
  content + authenticated sessions exist.
- **"Mentor" = Curriculum Studio author/reviewer roles.** Those workflows are covered (create /
  validate / submit / review×5 / publish / versions / rollback) in tests + partially live.
- **Browser compatibility:** verified on **Chrome** (desktop + mobile viewport). A full
  Chrome/Firefox/Safari/Edge matrix was **not** run (would need those engines).
- **Load/perf at scale:** only a light probe (trial-tier constraint). No sustained/soak/spike test.

---

## 6. Requested checklist — status map

| # | Item | Status |
| --- | --- | --- |
| 2 | Crawl every page | ✅ all routes 200, distinct real pages |
| 3 | Test every API endpoint | ✅ 45 endpoints enumerated; all categories exercised live + in tests |
| 4 | Authentication flows | ✅ enforcement + IDOR verified (dev-JWT stub — §5) |
| 5 | Guardian flows | ✅ endpoints + authz; data screens gated (§5) |
| 6 | Student flows | ✅ 11 endpoints + UI |
| 7 | Mentor flows | ✅ Curriculum Studio authoring workflow |
| 8 | Curriculum Studio workflow | ✅ create→validate→submit→review→publish (tests) ; create/validate/persist (live) |
| 9 | Offline sync | ✅ frontend offline suite + live `sync/batch` |
| 10 | AI Teacher | ⚠️ templated / no-LLM by design (§5) |
| 11 | Database persistence | ✅ confirmed live (draft survived re-fetch) + migrations on Railway |
| 12 | Uploads | ❌ feature does not exist at M1 (§5) |
| 13 | Browser compatibility | ⚠️ Chrome only |
| 14 | Mobile responsiveness | ✅ RTL responsive at 390×844 |
| 15 | Security checks | ✅ headers, HSTS, CSP, HTTPS redirect, no stacktrace leak, docs gated |
| 16 | Load testing | ⚠️ light only (trial constraint) |
| 17 | Readiness report | ✅ this document |
| 18 | Fix every issue | ✅ 1 critical + 1 hardening fixed |
| 19 | Repeat until zero critical | ✅ zero critical defects remain |

---

## 7. Postgres-gated suite

Ran `make test-pg` against a real PostgreSQL 16 (Docker). Migrations passed the full
**reversibility** check — `alembic upgrade head` → `downgrade base` → `upgrade head` — and the
entire suite (including the 8 previously-skipped Postgres-gated tests) ran to **100% with no
failures** (`PG_EXIT=0`). This independently corroborates the live persistence result in §3 and the
successful migrations on Railway.

---

## 8. Recommendations before calling it "production"

1. **Replace the dev-JWT stub** with the production auth (asymmetric JWKS + rotation + KMS) and the
   child-safe consent/login flow. This is the single biggest gate to real users.
2. **Seed / author real curriculum** and validate the full author→publish→learn chain over HTTP on a
   real environment.
3. **Move off the Railway free trial** to a durable plan (or the prepared Koyeb + Neon free stack) —
   the current instance shows "28 days / $4.91 left."
4. **AI Teacher:** wire a real LLM provider behind the existing `LLMGateway` port when leaving M1.
5. **Cross-browser + real load testing** on non-trial infra.
6. Consider **precaching per-route** in the SW (beyond network-first) for a richer offline
   multi-route experience.
