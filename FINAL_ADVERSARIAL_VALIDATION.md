# Final Adversarial Validation

Status: **Adversarial validation complete.** The running application was attacked — malformed
requests, forged/expired/wrong-secret auth, IDOR, race conditions, replay, injection, boundary
values, resource exhaustion, and operational abuse — not reviewed. Six real engineering defects were
found, fixed, and covered by regression tests. Attacks were re-run after each fix; the campaign
stopped when further attacks revealed no new defects.

Method: an in-process harness drove the real composed app (`create_app`) via `TestClient`
(`raise_server_exceptions=False`, so any unhandled error surfaces as a 500 rather than hiding).
Concurrency and optimistic-locking findings were reproduced against **real PostgreSQL** (in-memory
SQLite shares one connection via StaticPool and is not representative under threads). Each fix was
verified on the same surface that exposed it.

---

## 1. Defects discovered and fixed

| # | Attack | Defect | Fix | Regression test |
| --- | --- | --- | --- | --- |
| D1 | 20 concurrent `POST :answer` on one session | Optimistic-lock `StaleDataError` on `student_knowledge` → **500** (lost-update prevention worked, but the loser crashed) | UoW translates the conflict; `KnowledgeService.record_attempt`/`ensure_student` retry the read-modify-write; exhaustion → 409 | `test_concurrency.py` (8) |
| D2 | `POST /v1/sync/batch` with no token / another child's `student_ref` | Endpoint was **unauthenticated** and durably recorded assessment evidence for an **arbitrary** learner (forgery / IDOR) | Require auth; enforce `attempt.student_ref == token.sub` (privileged `system` may sync any); missing ref → 422 | `test_attack_hardening.py` (5) |
| D3 | `x-correlation-id: abc\r\nSet-Cookie: …` | CR/LF **echoed verbatim** into the response header and structured logs (response splitting / log injection) | `ensure_correlation_id` accepts only `[A-Za-z0-9._-]{1,128}`, else mints a fresh id | `test_attack_hardening.py` (3) |
| D4 | Flood of `POST /v1/learning/sessions` | `InMemorySessionRepository` was an **unbounded dict** → memory-exhaustion DoS | Bounded LRU store (default 10 000; oldest-touched evicts) | `test_session_store_bounded.py` (3) |
| D5 | Stream of unique sync `clientEventId`s / entity keys | `SyncStore._seen` / `_entities` grew **unbounded** → memory-exhaustion DoS | Bounded LRU (`_MAX_SEEN`/`_MAX_ENTITIES`); safe because attempt idempotency has a durable backstop and the merge policies are idempotent | `test_sync_store_bounded.py` (3) |
| D6 | 8 concurrent identical Curriculum Studio reviews (double-click) | Losing writer's version-guarded UPDATE matched 0 rows → raw `StaleDataError` → **500** | Conflicts map to a retryable **409** app-wide; the service commits inside the handler so the error is catchable; app-level handlers cover flush-time conflicts | `test_studio_conflict.py` (5) |

Verified outcomes after fixing: D1 — PostgreSQL 8/20 concurrent → all 200, zero 500s. D6 —
PostgreSQL 8 concurrent → 1×200 winner + 7×409, zero 500s, exactly one approval applied.

---

## 2. Attacks attempted that the system already withstood

No change was needed for these — the platform handled them correctly:

- **Auth**: garbage token → 401; expired token → 401; `alg=none` forgery → 401; wrong-secret HS256 →
  401; missing `role` claim → 401.
- **Authorization / IDOR**: student → ops kill switch → 403; cross-student `today`/`history`/
  `knowledge`/`ai-teacher/plan`/session `:next` → 403/404; role injected in request body ignored
  (role comes from the token).
- **Injection**: SQL-injection strings in path/params → parameterized, no error, no leak; the API is
  JSON-only (no reflected-HTML/XSS surface); path traversal on package ids → 404; no private key /
  seed ever present in `/v1/offline/signing-keys`; answer keys never ship in offline packages.
- **Malformed / boundary**: malformed JSON → 422; deeply nested JSON → 422 (no crash); wrong
  Content-Type → 422; out-of-range / wrong-type `option` → 422/200 (never 500); negative
  cursor/seq → handled; 1 MB field → 422; 100 k-char correlation id → sanitized to 32 chars; 200
  extra headers → 200.
- **Sync integrity**: replay of the same `clientEventId` → `duplicate`; same `evidence_id` under a
  different event id → not double-applied; unknown delta type → 422.
- **State machine**: answer-before-teach, double-`end`, op on a missing session → 404, never 500.
- **Offline**: package Ed25519-signed; signature binds `package_id + version + content_hash`; client
  verification implemented and wired.
- **Kill switch**: engaged → child-facing routes 503 while `/health`, `/metrics`, `/v1/ops/*` stay
  reachable; a halt 503 is **not** counted as a server error (it has its own
  `taleem_kill_switch_blocked_total` signal), so it does not trip the error-rate alert.
- **HTTP hygiene**: wrong method → 405; production-safety gate fails closed on default secrets.

---

## 3. Post-fix state

- Full local gate suite green: backend **216 passed / 8 skipped**, coverage **96.3%** (ruff, black,
  mypy --strict); web **85** tests; all OpenAPI contracts valid (sync now `bearerAuth` + 401/403;
  studio mutations document 409); markdownlint 0 errors. `make gates` passes.
- The end-to-end **pilot simulator** (`make simulate`, 15 synthetic students, offline verification +
  failure injection) returns **PASS** with zero request errors — no regressions from the fixes.

---

## 4. Remaining known engineering risks

These are residual limitations, not open defects. None is a live vulnerability in the intended
(PostgreSQL, single-instance pilot) deployment.

1. **In-memory SQLite is not concurrency-safe.** The dev/test default (`database_url=""`) uses a
   StaticPool that shares one connection across threads; under concurrent requests it can corrupt
   result parsing. This is a documented dev-only constraint — production fails closed unless a real
   PostgreSQL URL is set, and `docker-compose` now runs PostgreSQL. Do not run the in-memory default
   under concurrent load.
2. **Session state and the sync conflict cache are process-local.** They are correct and now bounded,
   but not shared across replicas; horizontal scaling of the API needs a shared/durable session store
   and idempotency ledger before multi-instance deployment. (Attempt idempotency is already durable
   via the evidence table.)
3. **The kill switch is process-local** (documented). In a multi-worker deployment each worker must
   be signaled; the single-instance pilot is unaffected.
4. **No app-level rate limiting.** Oversized/abusive payloads are rejected and in-memory growth is
   bounded, but request-rate throttling is expected at the edge (reverse proxy / gateway), which is a
   deployment/infrastructure control, not application code.
5. **Auth is the documented HS256 dev stub.** Tokens have no `jti`, so a valid unexpired token can be
   replayed until expiry — acceptable for Pilot 0 (no children, internal). Child-safe production auth
   is governance-gated (M-Gov) and is a human/credential task, not completable in software here.

Items 1–4 are addressed by the production deployment posture (PostgreSQL, a shared store, an edge
gateway) rather than by further application code; item 5 is governance-gated. Within the application
code and its intended deployment, adversarial attacks now reveal no new engineering defects.
