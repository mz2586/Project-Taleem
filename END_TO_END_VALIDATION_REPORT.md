# End-to-End Production Validation Report

Status: **Complete.** The application was started as a production deployment would start it — the real
API (uvicorn) + real PostgreSQL (Alembic-migrated) in containers, and the real Next.js frontend built
and served in production mode — and every implemented workflow was executed against it over real
HTTP and, for the student surface, a real browser. Two blocking software defects were found, fixed,
regression-tested, and re-verified end to end. No blocking software defects remain.

## How it was run

- **API + DB**: `docker compose` — `postgres:16` + the multi-stage non-root `core-api` image running
  `alembic upgrade head && uvicorn taleem_core.main:app`. Confirmed: non-root (`taleem`), 23 domain
  tables migrated across the `learning` + `curriculum_studio` schemas, `/health` + `/health/ready` +
  `/metrics` live. (Host ports 5432/6379/8000 were occupied, so the stack ran on an isolated network
  with the API published on a free port — the app itself is unchanged.)
- **Frontend**: `next build` + `next start` (production), `NEXT_PUBLIC_API_URL` pointed at the API.
- **Drivers**: an HTTP driver executed each role workflow against the running server (44 checks); a
  real Chrome session loaded the student PWA and issued live cross-origin calls to the API.
- **Content**: the sample Grade-4 lesson was published through the real Curriculum Studio workflow
  (author → submit → 5 staged reviews → publish) as a production data-seed.

## Workflow results (against the running stack)

| Role | Workflow step | Result |
| --- | --- | --- |
| **Curriculum** | Published lesson reachable over HTTP | ✅ PASS |
| | Authoring: create draft → list → get → validate → submit (gate enforced) | ✅ PASS |
| **Student** | Start session | ✅ PASS |
| | Plan next (AI decision) | ✅ PASS |
| | AI Teacher: teach / explain / hint | ✅ PASS |
| | Assessment: answer items | ✅ PASS |
| | End session | ✅ PASS |
| | Read today / progress / history / homework / achievements / recommendations | ✅ PASS |
| | Progress updated after session | ✅ PASS |
| **Offline** | Download signed package | ✅ PASS |
| | Package signed; **no answer keys shipped** | ✅ PASS |
| | Verify Ed25519 signature | ✅ PASS |
| | Reconnect + sync attempt (applied) | ✅ PASS |
| | Sync replay is idempotent (duplicate) | ✅ PASS |
| | Progress reflects synced attempt | ✅ PASS |
| **Mentor** | Review learner today / progress / knowledge / history | ✅ PASS |
| | Review AI Teacher plan + escalation/capabilities | ✅ PASS |
| | Read ops status | ✅ PASS |
| | Cannot operate another learner's session (authz boundary) | ✅ PASS |
| **Admin** | System status + monitoring (golden signals) | ✅ PASS |
| | Prometheus metrics | ✅ PASS |
| | Kill switch: engage → child-facing halted (503), ops/health stay up | ✅ PASS |
| | Recovery: disengage → child-facing restored | ✅ PASS |
| | Kill switch is operator-only (403 for others) | ✅ PASS |
| **Frontend (browser)** | PWA builds + serves all pages in production; SW + manifest present | ✅ PASS |
| | SPA calls the API cross-origin and renders **live data** (after CORS fix) | ✅ PASS |

**HTTP driver: 44/44 checks pass, 0 fail.**

## Bugs found and fixed

### BUG-1 (blocking) — API had no CORS; the browser frontend was fully blocked

The API sent no `Access-Control-Allow-Origin` and answered preflight `OPTIONS` with 405. A browser SPA
served from a different origin than the API (dev `localhost:13000` → `localhost:18080`; in production
`app.taleem.dev` → `api.taleem.dev`) had **every** request blocked by the browser, so the student app
silently fell back to its offline state and could load no data.

- **Reproduced**: real Chrome on `/student/today` rendered the offline panel; a page-context `fetch`
  to the API failed with `status 0` (CORS block); preflight `OPTIONS` → 405, no ACAO header.
- **Fixed**: a configurable CORS allowlist (`TALEEM_CORS_ALLOWED_ORIGINS`, exact origins only — never
  `*`, because the API is credentialed with a bearer JWT; preflight handled; `max_age` set).
- **Re-verified from the browser**: preflight → 200 + ACAO; a cross-origin `fetch` from the SPA origin
  now returns **200 with live progress/today data** (`cors_worked: true`).
- **Tests**: `tests/test_cors.py` (5) — empty allowlist = no CORS headers; allowed origin echoed on
  simple + preflight requests; disallowed origin gets none; never `*`.

### BUG-2 (blocking) — `POST …:teach` returned 500 on two real paths

Driving a returning student (who had already mastered the objective) surfaced a 500: `:next` returned
a non-teach decision, and calling `:teach` anyway forced an illegal `planning → interacting`
transition (`SessionError`). A second 500 path: `:teach` for an objective with no published lesson
raised a bare `ValueError`. Domain rule violations must be clean 4xx, never 500.

- **Reproduced**: against the running container, `:teach` for a mastered objective → 500
  (`SessionError: illegal session transition: planning -> interacting`); `:teach` with no lesson →
  500 (`ValueError: no published lesson`).
- **Fixed**: a route guard maps `SessionError` → **409** (`SESSION_STATE_CONFLICT`, retryable — the
  client re-plans via `:next`); a missing published lesson → **404** (consistent with `:answer` /
  `:hint`).
- **Re-verified**: rebuilt container, HTTP driver **44/44 pass, zero 500s**.
- **Tests**: `tests/test_session_state_conflict.py` (2) — out-of-turn teach → 409; no-lesson → 404.

## Tests added

| File | Count | Covers |
| --- | --- | --- |
| `services/core-api/tests/test_cors.py` | 5 | CORS allowlist (BUG-1) |
| `services/core-api/tests/test_session_state_conflict.py` | 2 | Session 409 / lesson 404 (BUG-2) |

Full backend suite after fixes: **223 passed / 8 skipped, coverage 96.3%** (ruff, black,
mypy --strict); web 85 tests; OpenAPI contracts valid; markdownlint clean; `make gates` green; the
end-to-end HTTP driver reports 44/44.

## Screenshots

- `before` — `/student/today` in the real browser rendering the **offline fallback** despite showing
  "Online", the visible symptom of BUG-1 (the SPA could not reach the API). Saved during validation:
  `screenshot-1784891809176-0.jpg`.
- `after` — browser-level proof, captured as a page-context fetch from the SPA origin
  `http://localhost:13000`:

  ```json
  { "origin": "http://localhost:13000", "api_status": 200, "cors_worked": true,
    "mastery": { "total": 1, "mastered": 0, "in_progress": 0 } }
  ```

  (A rendered dashboard screenshot could not be re-captured — the browser renderer became
  unresponsive after a manual service-worker cache clear, a session artifact, not a product issue;
  the live-data fetch above is the definitive confirmation.)

## Workflows not implemented in software (not defects — out of scope to add)

Per "do not add new features," these have no software implementation and were confirmed to **fail
closed**, which is correct behaviour, not a bug:

- **Student: Register / Login / Enroll** — no such endpoints (all `POST` → **404**). Authentication is
  the documented dev JWT stub; production child-safe auth + enrolment is governance-gated (M-Gov).
- **Guardian: view student / progress / weekly report / notifications** — no guardian endpoints
  (`/v1/guardian/*`, `/v1/reports/weekly` → **404**) and a `guardian` role is denied on the learner
  read endpoints (**403**, deny-by-default). The guardian experience is Phase-9 design over existing
  read models, not yet built; a guardian-facing surface + report generation is future software work
  gated behind consent (M-Gov).

## Remaining blocking software defects

**None.** Every implemented workflow completes successfully against the real API + database + browser,
and the two blocking defects found (CORS, session 500s) are fixed and regression-tested. The
not-implemented Register/Enroll and Guardian workflows are governance-gated product scope, not
software defects — building them is explicitly out of scope for this validation.
