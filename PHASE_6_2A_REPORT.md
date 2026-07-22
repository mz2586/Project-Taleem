# Phase 6.2A — Offline-Lite Implementation Report

Status: **Complete.** Implements the approved Phase-6.2 offline design ([OFFLINE_ARCHITECTURE.md](OFFLINE_ARCHITECTURE.md),
[OFFLINE_STORAGE_SPEC.md](OFFLINE_STORAGE_SPEC.md), [OFFLINE_SYNC_SPEC.md](OFFLINE_SYNC_SPEC.md),
[OFFLINE_SECURITY_REVIEW.md](OFFLINE_SECURITY_REVIEW.md), [OFFLINE_TEST_PLAN.md](OFFLINE_TEST_PLAN.md)),
**Phase 6.2A only**. No 6.2B/6.2C work. Local commit + `phase-6.2A` tag.

---

## 1. Scope delivered (6.2A checklist)

| Deliverable | Where | Notes |
| --- | --- | --- |
| ✓ Application Shell caching | `apps/web/public/sw.js` | Versioned shell cache, cache-first navigations |
| ✓ Curriculum package download | backend `/v1/offline/packages`, client `DownloadManager` | Content-hashed manifests; `offlineApi.fetchPackage` |
| ✓ Lesson package cache | `apps/web/lib/offline/packages.ts` + IndexedDB `content` store | Verified, atomic install |
| ✓ IndexedDB storage | `apps/web/lib/offline/kv.ts` | `taleem-offline` DB, 7 stores; `IdbStore` + `MemoryStore` |
| ✓ Download manager | `apps/web/lib/offline/packages.ts` | Verify + quota pre-flight + progress + remove |
| ✓ Offline lesson loading | SW runtime cache + `DownloadManager.getLesson` | Renders from cache with no network |
| ✓ Offline dashboard | SW network-first-with-cache for `/v1/learning/students/*` + `ReadCache` | "As-of" snapshots |
| ✓ Offline progress persistence | `apps/web/lib/offline/progress.ts` | Local durable events (not synced — 6.2A) |
| ✓ Resume interrupted lessons | `apps/web/lib/offline/checkpoint.ts` | Client-side checkpoints + resume |
| ✓ Connectivity detection | `apps/web/lib/offline/connectivity.ts` | Events + optional reachability probe |
| ✓ Offline indicator | `apps/web/components/student/OfflineBadge.tsx` | Now driven by `watchConnectivity` |
| ✓ Automatic cache versioning | `apps/web/lib/offline/cacheVersion.ts` + backend `content_hash` | Content change → new version → stale detection |

### Explicitly NOT implemented (deferred, per instruction)

Background sync · conflict resolution · offline authentication · sync batching · durable session
replay · telemetry upload · governance-gated features. The service worker and stores are structured so
these drop in at 6.2B/6.2C without rework (e.g. `client_event_id` on every progress event is already
the future sync idempotency key; the `sync_meta` store exists for a future cursor).

---

## 2. Backend — offline package service

A published lesson's opaque `offline_package` string becomes a real, verifiable package built on the
fly from the existing curriculum read model. **No new tables, no child data.**

- `contexts/learning/domain/offline_package.py` — **pure** builder: `lesson_offline_content` (child-safe
  projection), `content_hash` (SHA-256 over canonical JSON), `build_manifest` / `build_package`,
  `fits_in_quota` (pre-flight).
- `contexts/learning/application/offline_service.py` — `OfflinePackageService.list_packages()` /
  `get_package(lesson_id)` over the `CurriculumReadModel` port.
- `contexts/learning/adapters/offline_api.py` — `GET /v1/offline/packages` (index) and
  `GET /v1/offline/packages/{lesson_id}` (full package). Authenticated + authorized to read
  `learning.knowledge` (students/mentors already hold this grant — **no new PDP rule, no governance
  change**). Not IDOR-scoped (curriculum is not per-child).
- Wired in `main.py`; `packages/contracts/offline.openapi.yaml` documents it (redocly-valid).

### Two deliberate design properties

1. **No answer keys on the device.** The offline content ships the teaching + attempt surface (title,
   explanation, worked steps, item prompts, options, authored hints) but **never** `correct_option` /
   `option_misconceptions` / corrections. A device therefore cannot reveal an answer offline — a safety
   property. Server-side grading returns with sync in 6.2B.
2. **Content-hash versioning.** `version = content_hash[:12]`; a content change changes the hash, so the
   client treats the cached package as stale (automatic invalidation). **No Ed25519 signing** — that is
   6.2C hardening; the SHA-256 hash gives integrity + versioning for offline-lite.

Cross-reference to the design: OFFLINE_ARCHITECTURE.md §3 (packages), §6 (versioning); the manifest
shape matches the design's `{package_id, lesson_id, version, content_hash, assets, total_bytes}`.

---

## 3. Frontend — offline-lite library + PWA

`apps/web/lib/offline/` — a small, testable library behind a `KVStore` interface (`IdbStore` for the
browser, `MemoryStore` for tests/SSR):

| Module | Responsibility |
| --- | --- |
| `kv.ts` | `taleem-offline` IndexedDB (7 stores) + in-memory store + `createStore()` |
| `packages.ts` | `DownloadManager` — fetch → verify (SHA-256 vs manifest) → atomic install; quota pre-flight (`fitsInQuota`, `QuotaExceededError`), integrity (`IntegrityError`), `getLesson`, `remove` |
| `sha256.ts` | Canonical JSON (Python-parity) + `contentHash` + `verifyContent` |
| `cacheVersion.ts` | Shell cache naming, stale-cache + stale-package detection |
| `progress.ts` | `ProgressStore` — durable local progress events + per-lesson summary |
| `checkpoint.ts` | `CheckpointStore` — start/advance/resume/latest/clear |
| `readCache.ts` | `ReadCache` — labelled offline snapshots of student reads; clear-on-switch |
| `connectivity.ts` | `watchConnectivity` (events + probe), `makeProbe`, `currentlyOnline` |
| `ids.ts` | Client `uuid7` (mirrors `platform/ids.py`) |
| `index.ts` | `createOfflineClient`, `registerServiceWorker`, public surface |

- **Service worker** (`public/sw.js`) upgraded: versioned shell + runtime caches; app-shell cache-first;
  network-first-with-cache-fallback for `/v1/offline/*` and `/v1/learning/students/*` (the offline
  dashboard + lesson-loading layer); old `taleem-*` caches purged on `activate`; never caches non-GET,
  cross-origin, tokens, or errors; `SKIP_WAITING` message for user-controlled updates.
- **Registration** wired via `components/ServiceWorkerRegister.tsx` in the root layout (client-only,
  failure-safe).
- **`OfflineBadge`** now uses the shared `watchConnectivity` detector.
- **`offlineApi`** added to `lib/student/api.ts` (`listPackages`, `fetchPackage`).

Conforms to OFFLINE_STORAGE_SPEC.md (store layout, disposable-vs-durable) and OFFLINE_ARCHITECTURE.md
§4 (service worker). No child PII stored — only the pseudonymous `student_ref`.

---

## 4. Testing

| Suite | Count | Covers |
| --- | --- | --- |
| Backend `tests/test_offline_packages.py` | 8 unit + 1 SQLite integration (+1 PG-gated) | builder determinism, **cache-invalidation** (hash changes with content), **no-answer-keys** safety, asset/hash match, injected clock, **storage quota** pre-flight; endpoint round-trip + 404 + auth |
| Frontend `apps/web/lib/offline/__tests__/` (vitest) | 31 across 9 files | cache versioning, sha256 + Python-parity + tamper detection, download manager (install, **integrity reject**, **quota reject**, offline render, remove), progress persistence, checkpoint resume, read cache, connectivity, `uuid7`, and an **IndexedDB offline-browser simulation** (fake-indexeddb): install + render + resume persist across reopen |

Test categories requested — all present: **unit** (both suites), **integration** (backend endpoints),
**offline browser simulation** (`idb.test.ts` via fake-indexeddb), **cache invalidation**
(`cacheVersion.test.ts`, `sha256.test.ts`, backend hash test), **storage quota** (`packages.test.ts`,
backend `fits_in_quota`).

Tooling added: `vitest` + `fake-indexeddb` (dev deps), `vitest.config.ts`, `npm test` script.

---

## 5. Quality gate summary

| Gate | Result |
| --- | --- |
| Ruff | ✅ All checks passed |
| Black (`--check`) | ✅ 109 files unchanged |
| mypy `--strict` | ✅ no issues in 89 source files |
| pytest | ✅ **146 passed, 5 skipped** (5 = PostgreSQL-gated) |
| OpenAPI (redocly 1.25.11) | ✅ all contracts valid (incl. new `offline.openapi.yaml`) |
| Frontend typecheck (`tsc --noEmit`) | ✅ clean |
| Frontend tests (`vitest run`) | ✅ **31 passed** (9 files) |
| Frontend build (`next build`) | ✅ compiled + 12 static pages |

PostgreSQL-gated tests run in CI with `CS_DATABASE_URL`; locally they skip (no PG), consistent with the
existing suite.

---

## 6. Conformance + constraints honored

- **Existing architecture reused, not redesigned:** the sync contract, `uuid7`, evidence model, auth,
  and read APIs are untouched; the offline package service is a new derived read-only surface over the
  existing `CurriculumReadModel`.
- **No new child-data tables; no child PII** anywhere (packages are C0 curriculum; local stores hold only
  `student_ref`).
- **No governance-gated work; no PDP/auth changes.**
- **No generative AI offline** (packages are static approved content; no runtime AI on device).
- **Safety:** answer keys never leave the server; offline is read/attempt-only for the pilot.

---

## 7. Follow-ups (not in 6.2A)

- 6.2B: durable sync consumer (`SyncDelta` → `AssessmentEvidence`), background sync, conflict resolution,
  durable session replay, server-side offline grading.
- 6.2C: Ed25519 package signing, at-rest encryption of C2 stores, device-bound offline token
  (governance-gated), telemetry upload, offline safety crisis-flag routing.
- Minor: web-manifest icons + `Save-Data`/`persist` polish (gap G8) — partially staged (`persist`
  request helper exists); icon assets deferred.
