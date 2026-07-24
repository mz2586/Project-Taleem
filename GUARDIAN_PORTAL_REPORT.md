# Guardian Portal Report

Status: **Complete and operational.** The Guardian Experience is delivered as a thin, read-only
aggregation over the *existing* platform — no redesign, no new architecture, no governance
implementation. Every data point a guardian sees is produced by a service the Student Platform,
Learning Intelligence, AI Teacher, Assessment, and Offline Sync components already expose. The only
new state introduced is the guardian→children association.

## Architecture reused (nothing re-implemented)

| Guardian data (WS1) | Reused component | How |
| --- | --- | --- |
| Progress overview, knowledge growth | `LearningAnalytics.progress_summary` | consumed as-is (per-objective mastery included) |
| Learning timeline, attendance, streaks | `StudentQueryService.history` | pure derivation over the sessions it returns |
| Weekly summary | same `history` sessions | trailing-7-day pure aggregation |
| Assessment history | `StudentQueryService.assessments` | consumed as-is |
| AI Teacher activity | `AITeacherService.plan` | consumed as-is |
| Recommendations | `StudentQueryService.recommendations` | consumed as-is |
| Intervention notifications | `StudentQueryService.notifications` | filtered (revision-due / at-risk) |
| Achievement history | `StudentQueryService.achievements` | consumed as-is |
| Offline sync status | `AssessmentEvidence` timestamps (via history) | last-sync + staleness derivation |
| Authn / authz | dev JWT verifier + deny-by-default PDP | one new PDP rule (`guardian read guardian.self`) |
| Monitoring, audit, security headers, CORS | platform middleware | inherited unchanged |

The **only new logic** is guardian-facing presentation over that data — `attendance`, `streak`,
`weekly_summary`, `sync_status` — four pure functions in `guardian_service.py`. The only new state is
`GuardianDirectory` (guardian→children links), seeded from config (`TALEEM_GUARDIAN_LINKS`); this is
the software association layer, not the M-Gov consent flow. The same `student_queries`,
`LearningAnalytics`, and `ai_teacher` instances are shared with the learning routers (wired once).

## APIs added (WS2 — only what's required, no duplication)

Three endpoints serve the entire portal by aggregation, rather than duplicating the ~13 student
read endpoints. Each is authenticated, PDP-authorized, IDOR-guarded, validated, audit-logged,
monitored, documented in OpenAPI, and covered by integration tests.

| Method + path | Purpose | Auth |
| --- | --- | --- |
| `GET /v1/guardian/me` | Guardian profile + linked children | guardian role |
| `GET /v1/guardian/dashboard` | Summary across all linked children | guardian role |
| `GET /v1/guardian/children/{studentRef}` | Full detail for ONE **linked** child | guardian role + directory link |

- **Authorization**: PDP `guardian read guardian.self` + a directory link check on the child route.
- **Audit logging**: `guardian_dashboard`, `guardian_child_view`, `guardian_access_denied` (pseudonymous).
- **Monitoring**: `taleem_guardian_views_total{view=…}`, `taleem_guardian_denied_total`.
- **OpenAPI**: `packages/contracts/guardian.openapi.yaml` (redocly-clean; contract-parity test enforced).
- Read-only: no POST/PUT/DELETE on the guardian surface (mutations → 405).

## Pages completed (WS3)

- `/guardian` — dashboard: one card per linked child (mastery ring, streak, achievements, sync
  freshness pill, open-interventions warning), with **loading / empty / error / offline+retry**
  states and an on-demand refresh.
- `/guardian/children/[studentRef]` — full child detail: progress, offline-sync status, streak +
  attendance, this-week summary, knowledge growth, interventions, AI-Teacher recommendations,
  learning timeline, achievements — each with graceful empty rendering; loading / denied / offline /
  error + retry.
- Reuses the existing design language (`ui.tsx` Card/ProgressRing/Skeleton/EmptyState/ErrorBanner,
  the design-system `Button` with mandatory visible labels), skip link, RTL greeting, `role=alert` /
  `role=status` regions. Responsive (max-width, fluid grid). PWA-compatible (same app + service worker).
- A shared `createApiClient` factory (bearer auth + problem+json + status-0 offline error) is used by
  the guardian client so the request/error logic lives in one place, not duplicated.

## Screenshots

- `guardian-dashboard.jpg` — the live dashboard: "السلام علیکم، Amina", child card for `e2e-student`
  (mastery ring, day-streak, achievement badge, "Synced recently"), Refresh + View details.
- Browser-level proof of the child detail (captured as a page-context fetch from origin
  `http://localhost:13000`, since the dev service worker intercepts the dynamic route's navigation):

  ```json
  { "child_status": 200, "has_all": true, "sections": 13,
    "idor_unlinked_status": 403, "weekly": { "attempts": 5, "correct": 5, "accuracy": 1 } }
  ```

  All 13 sections present with live data; an unlinked child returns 403.

## Tests added

| File | Count | Covers |
| --- | --- | --- |
| `tests/test_guardian_api.py` | 14 | profile/dashboard/child; authz; IDOR; parameter tampering; privilege escalation; forged/expired tokens; read-only; sync status; monitoring |
| `tests/test_guardian_derivations.py` | 6 | streak / attendance / weekly / sync-status pure logic |
| `apps/web/lib/__tests__/apiClient.test.ts` | 5 | shared client: auth header, offline error, problem+json, 204 |

Backend **243 passed / 8 skipped, coverage 96.4%**; frontend **90 tests** (85 existing + 5),
`tsc --noEmit` clean, production build compiles both guardian pages; OpenAPI contracts valid;
markdownlint clean; `make gates` green.

## Security findings (WS4 + WS6 — attacked as the student APIs were attacked)

**19/19 adversarial attacks held; no defects found.** A guardian can access **only** linked children.

| Attack | Result |
| --- | --- |
| IDOR — read another guardian's child | 403 |
| IDOR — non-existent child (enumeration) | 403 (identical; no existence disclosure) |
| Role confusion — student/mentor/author token on portal | 403 |
| Privilege escalation — guardian → ops / student-raw / studio | 403 |
| Forged JWT (`alg=none`, wrong secret) | 401 |
| Expired token (replay after expiry) | 401 |
| Missing role claim / garbage token | 401 (not 500) |
| Parameter tampering / path traversal / URL-encoding of an unlinked ref | 403 / 404 |
| Header (CRLF) injection via `x-correlation-id` | sanitized |
| Oversized `sub` | no crash |
| Mutation attempt (POST) | 405 |
| Security headers, no raw PII keys in responses | present / none |

No new engineering defects were discovered, so nothing required fixing beyond the design (the
directory link check + deny-by-default PDP were correct from the first implementation).

## Performance observations

- The dashboard makes N per-child aggregations; each child summary is a small set of read-model
  calls (progress + history + notifications + achievements). Child count is bounded by the directory,
  so cost is O(children) — fine for realistic family sizes. The heavier full-overview call is
  isolated to the single-child route (loaded on demand), keeping the dashboard light.
- No new tables or writes: every guardian request is read-only over existing read models, so it adds
  no write contention and inherits the same optimistic-lock-free read path.

## Remaining software gaps

- **Consent-linked association (M-Gov)**: links are seeded from config; a real deployment populates
  `GuardianDirectory` from the consent workflow. That workflow is governance scope, explicitly out of
  scope here — the software association layer and its IDOR enforcement are complete and tested.
- **Notification read-state / weekly-report export**: notifications are derived read-only (no
  persisted read-state); a downloadable weekly PDF/email is not built (would be a new delivery
  channel, not a data gap — all the data exists at `GET /v1/guardian/children/{ref}`).
- **Pending offline uploads** are device-side; the server reports last-successful-sync + staleness
  and flags that pending work is device-reported. A device→guardian pending-count push is future work.

None of these blocks the Guardian Portal, which is fully operational for viewing every WS1 data point
for linked children.
