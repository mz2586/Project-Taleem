# Student Portal — Architecture (Phase 5 Design)

Status: **Design only** — no implementation. Companion to
[STUDENT_EXPERIENCE.md](STUDENT_EXPERIENCE.md). Defines *how* the student experience is built: the
technical shape of a mobile-first, offline-capable, accessible PWA over the existing `/v1/learning`
API. No frontend code here — this is the blueprint the implementation follows once approved and once
the Phase-1.5 governance gate clears.

Consistent with the fixed stack (Next.js PWA + the platform's FastAPI/`/v1/learning` API) and the
non-negotiables (Android-Go/3G/offline, WCAG 2.2 AA, Urdu-first RTL, child safety).

---

## 1. Technology & rendering strategy

- **Framework:** Next.js (App Router) as a **PWA** (installable, offline-capable), React, TypeScript
  strict. Reuses the existing `apps/web` design system.
- **Rendering:** the learner surface is **app-like and offline-first**, so it is predominantly a
  client-rendered SPA shell (the "app shell" model) with:
  - **Static/prerendered** shell + design assets (fast first paint, cacheable).
  - **Client-side** data + interactivity (the session runs offline from cache; SSR is not usable
    when disconnected).
  - Optional SSR/ISR only for public/marketing or first-load SEO surfaces — **not** the child app,
    which must work offline where SSR cannot.
- **Why not SSR-heavy:** a child on 3G/offline can't round-trip to a server per navigation. The app
  shell + local data model is the only architecture that satisfies the offline non-negotiable.

## 2. High-level architecture

```text
┌──────────────────────────── Device (low-end Android, PWA) ────────────────────────────┐
│  UI (React, design system, RTL, a11y)                                                   │
│    Screens (Today, Session, Profile, …)  ── consume ──▶  View Models / hooks            │
│                                                             │                            │
│  State layer                                                ▼                            │
│    - Server-cache (query cache: knowledge, progress, plan)  Domain store (session saga,  │
│    - UI state (ephemeral)                                   answer log, sync queue)       │
│                                                             │                            │
│  Data access                                                ▼                            │
│    API client  ◀────────────────────────────────  Offline Sync Engine (durable log)     │
│      │  (bearer token, ret/backoff, problem+json)          │                            │
│      │                                              Local persistence (IndexedDB):        │
│      ▼                                                lesson packages, evidence queue,     │
│  Service Worker (cache-first shell, runtime caching,        snapshots, session tokens     │
│   background sync)                                                                        │
└───────────────────────────────────────┬─────────────────────────────────────────────────┘
                                         │ HTTPS (when online)
                                         ▼
                         Platform API  (/v1/learning/*, /v1/sync/batch, /auth/*)
```

## 3. State management

Three clearly-separated state categories (avoid one giant store):

1. **Server-cache state** (mastery, progress, plan, notifications) — a **query cache** (e.g. a
   React-Query-style layer) with: stale-while-revalidate, offline persistence, and background
   refetch. Read models; the server is the source of truth.
2. **Domain/session state** — the **learning-session saga on the client**: current session id, the
   sequence of decisions, the current teacher turn, the local **answer/interaction log** (append-only,
   idempotent client ids), and derived UI (progress pips). Mirrors the server's `SessionState`
   machine so the UI and server agree; persisted to IndexedDB so a session **resumes after
   crash/close** (matches the server saga's resumability).
3. **UI/ephemeral state** — modals, focus, toasts, form inputs — local component state; never
   persisted.

Rules: server-cache is never mutated directly (only via API + invalidation); the session saga is the
only writer of the answer log; the sync engine drains the log to the server and reconciles. All state
is **serializable** (for offline persistence + resume).

## 4. Offline architecture

The heart of the portal. Layers:

- **Service Worker:**
  - **Precache** the app shell + design assets (cache-first) → instant, offline first paint.
  - **Runtime caching** of API GETs (stale-while-revalidate) for plan/progress/knowledge.
  - **Background Sync** to flush the evidence queue when connectivity returns (with retry/backoff).
- **Local persistence (IndexedDB):**
  - **Lesson packages** — the approved `offline_package` per planned/due objective (content + media +
    checksums), so a full session runs offline. LRU-evicted; pre-download on Wi-Fi.
  - **Evidence/interaction queue** — durable, append-only, each item with a **client-generated
    idempotent id**; the unit the sync engine sends to `sync.batch`.
  - **Snapshots** — last-synced mastery/progress/plan for offline dashboards.
  - **Session state** — the in-progress saga, for resume.
  - **Auth** — the short-lived session token + refresh material (protected storage).
- **Sync engine (client):** reconciles with the server's transactional model — sends queued
  interactions via `sync.batch`; the server applies them **idempotently** (dedupe on client id),
  recomputes mastery from evidence, and returns an updated plan/snapshot. **Evidence is append-only
  and never conflicts;** derived state is recomputed server-side (no last-writer-wins on learning
  state). This mirrors the platform's outbox/idempotent-consumer design.
- **Integrity:** offline-package checksums verify content wasn't corrupted; a failed check re-fetches
  on Wi-Fi.

## 5. API client

- **Transport:** HTTPS only; typed client generated from / validated against the OpenAPI contracts
  (`curriculum-studio`, `learning`, and new student contracts) — contract-first, no drift.
- **Auth:** attaches the bearer token; silent refresh on 401; the token is learner-scoped (`sub ==
  student_ref`) so the server's IDOR guard is the backstop.
- **Resilience:** timeouts, exponential backoff + jitter, offline detection → queue instead of fail;
  every write carries an idempotency key.
- **Errors:** parses RFC 9457 `application/problem+json` into typed errors mapped to the calm,
  child-safe error UX (see §7); never surfaces raw status/stack to the child.
- **Batching for slow links:** prefers the aggregated `dashboard.today` over many small calls;
  coalesces where possible to minimize round-trips on 3G.

## 6. Auth & session

- **Child-safe auth:** device-linked learner handle + a simple credential (PIN/picture-password);
  exchanged for a **short-lived** bearer token (role `student`, `sub == student_ref`) + a refresh
  path. No child PII. Provisioning is a guardian/mentor flow (separate context), gated by governance.
- **Session lifecycle:** silent refresh; on hard expiry, a friendly re-sign-in that **preserves the
  learner's place**. Shared-device "switch learner" clears the prior learner's cached view.
- **Least privilege:** the token authorizes only the student surface; nothing in the portal can act as
  a mentor/author.

## 7. Error handling architecture

- **Error taxonomy:** `offline`, `sync-pending`, `not-cached-offline`, `server`, `auth-expired`,
  `content-load`, `wellbeing` (not an error — a safety route). Each maps to a defined UX
  (STUDENT_EXPERIENCE §11).
- **Boundaries:** React error boundaries around each screen and the session player → a graceful,
  child-safe fallback + safe return to Today; never a white screen.
- **Global handler:** normalizes API/problem errors → typed → UX; logs (privacy-safe, correlation-id
  tagged) for diagnostics.
- **Fail-safe:** learning progress is written locally *before* any network attempt, so no error can
  lose it; the sync engine guarantees eventual delivery.

## 8. Security architecture

- **Same posture as STUDENT_EXPERIENCE §12,** realized technically: strict CSP (no inline 3rd-party
  JS, no external hosts), no ads/trackers/analytics SDKs, no open input surfaces, HTTPS + HSTS.
- **Token handling:** short-lived, learner-scoped; stored in protected app storage; never in URL;
  refresh rotates.
- **Data minimization on device:** only pseudonymous learning data + approved content cached; raw AI
  dialogue is not persisted client-side beyond de-identified evidence needed to sync.
- **Content trust:** the player accepts only approved `LessonView` payloads; the type system + client
  make ungrounded AI content **unrenderable**; no client path constructs prompts or reaches a model
  directly.
- **Tamper resistance:** offline-package integrity checks; server remains the authority for mastery
  (client cannot fake mastery — it only submits evidence, which the server scores).

## 9. Performance budgets (mobile-first, enforced)

| Budget | Target (low-end Android / 3G) |
| --- | --- |
| Time to interactive (first load) | ≤ 3 s |
| Time to interactive (repeat, cached) | ≤ 1 s (app shell) |
| Initial JS (gzipped) | small, strictly budgeted; route-split; no heavy libs on the critical path |
| Session start (cached lesson) | ≤ 1 s, works offline |
| Media | lazy, compressed/WebP + audio streamed/cached; pre-fetch only on Wi-Fi |
| Animation | reduced-motion aware; never required; low-end-safe |
| Memory | fits Android-Go headroom; bounded caches (LRU) |

Enforced by code-splitting per route, deferring non-critical work, skeletons over spinners, and CI
performance checks (bundle-size + Lighthouse-style budgets) added to the web-build pipeline.

## 10. Design-system integration

- Consumes `apps/web` tokens + primitives; extends with learning organisms (TeacherTurn, QuestionCard,
  MasteryMap, …) per [STUDENT_COMPONENT_CATALOG.md](STUDENT_COMPONENT_CATALOG.md).
- **Theming:** grade-band presets (Early/Middle/Senior) + dark + high-contrast as token overlays; RTL
  by default via logical properties.
- Components are **presentation-only** and receive already-validated, approved data — no component
  fetches or constructs AI content.

## 11. Observability (privacy-safe)

- Correlation-id propagated from the client into API calls (ties learner actions to the platform's
  server-side telemetry, which already emits domain metrics/logs).
- Client telemetry is **privacy-safe and minimal** (performance, error rates, offline/sync health) —
  **no** behavioral tracking of children, no third-party analytics. Aggregated, pseudonymous.
- Health signals: offline duration, sync backlog size, session resume rate, load performance vs
  budget.

## 12. Proposed structure (illustrative, not prescriptive)

```text
apps/web/app/(student)/            # student route group (App Router)
  today/            session/            profile/
  subjects/         homework/           assessments/
  revision/         achievements/       notifications/  sign-in/
apps/web/lib/student/
  api/              # typed API client (contract-generated) + auth
  session/          # client session saga + answer log
  offline/          # service worker registration, IndexedDB stores, sync engine
  state/            # query cache config, persistence
  a11y/             # focus, live-region, RTL helpers
apps/web/design-system/            # existing tokens + primitives (extended)
apps/web/components/student/       # learning organisms (presentation-only)
```

## 13. Build/CI additions (design intent)

- Extend the existing `web-build` CI job with: type-check (strict), a11y linting, **bundle-size +
  performance budgets**, and a **Lighthouse/PWA** check (offline, installability, a11y score).
- Contract tests: the student API client is validated against the OpenAPI contracts (no drift) — the
  same discipline applied to the backend contracts.

## 14. Dependencies & sequencing (before implementation)

Implementation is gated on: (a) the **Phase-1.5 governance decisions** (child identity/auth, lawful
basis, DPIA, safeguarding); (b) the **new student-facing APIs** (STUDENT_API_REQUIREMENTS) being
designed → reviewed → built with the same design-first discipline; and (c) approval of this design.
The learner-facing session flow already has its backend (`/v1/learning`), so the session player is the
lowest-risk first slice once gated.
