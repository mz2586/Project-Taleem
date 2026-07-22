# Offline Learning Subsystem — Architecture (Design Review)

Status: **Design review only (Phase 6.2). No code, no source changes, no commits.** Umbrella document
for the offline subsystem. Companions: [OFFLINE_SYNC_SPEC.md](OFFLINE_SYNC_SPEC.md),
[OFFLINE_STORAGE_SPEC.md](OFFLINE_STORAGE_SPEC.md), [OFFLINE_SECURITY_REVIEW.md](OFFLINE_SECURITY_REVIEW.md),
[OFFLINE_TEST_PLAN.md](OFFLINE_TEST_PLAN.md).

This design **extends existing, partially-built architecture** — it does not redesign it. The parent
specs are `docs/02-architecture/33-offline-architecture.md` (the offline spec) and
`docs/12-student-experience/STUDENT_PORTAL_ARCHITECTURE.md §4`. The conflict/idempotency contract is
the **already-implemented** synthetic prototype in `services/core-api/src/taleem_core/contexts/sync/`
(`domain.py`) wired at `main.py` `POST /v1/sync/batch`. Where a component would require changing a
completed system, it is recorded in **§9 Architectural gaps** as a *recommendation*, not a redesign.

---

## 0. Grounding — what already exists (and is reused verbatim)

| Concern | Existing artifact (reused) | Path |
| --- | --- | --- |
| Offline pack reference | `Lesson.offline_package: str` (opaque `pkg/…`) | `contexts/curriculum_studio/domain/lesson.py:82` |
| Sample pack ref | `offline_package="pkg/math-g4-intro-fractions"` | `vertical_slice/fractions_lesson.py:235` |
| Service worker scaffold | `taleem-shell-v1`, app-shell cache-first, GET-only | `apps/web/public/sw.js` |
| Web manifest | `lang ur`, `dir rtl`, `display standalone` | `apps/web/public/manifest.webmanifest` |
| API client + offline signal | `ApiError(0, {code:"OFFLINE"})` on network fail; swappable `TokenProvider` | `apps/web/lib/student/api.ts` |
| Offline status UI | `OfflineBadge` (online/offline + `pendingCount`, `aria-live`) | `apps/web/components/student/OfflineBadge.tsx` |
| **Sync contract** | `DeltaType`, `SyncDelta`, `apply_batch`, `ItemResult`, conflict rules | `contexts/sync/domain.py` |
| Sync endpoint | `POST /v1/sync/batch` (+ PDP `(system,write,sync.batch)`) | `main.py`, `auth/pdp.py:54` |
| Evidence (system of record) | `AssessmentEvidenceRow` append-only, idempotent by `evidence_id` | `contexts/learning/adapters/persistence/{models.py:86,repository.py:69}` |
| Transactional outbox | `LearningOutboxRow` + `LearningUnitOfWork` (atomic state+event) | `contexts/learning/adapters/persistence/{models.py:111,uow.py}` |
| Client-safe IDs | `uuid7()` (pure-stdlib, "safe to generate on an offline device") | `platform/ids.py` |
| Auth (dev stub) | HS256 bearer, `Claims(sub,role,aal,exp,device_id)`, IDOR guard | `auth/{jwt_verifier,dependencies,pdp}.py` |
| Student read APIs (cacheable) | `/v1/learning/students/{ref}/{today,homework,…}` — GET, derived | `contexts/learning/adapters/student_api.py` |
| Session/hint APIs (queued) | `/v1/learning/sessions…:next/:teach/:answer/:hint/:end` | `contexts/learning/adapters/api.py` |

**Hard constraints inherited (non-negotiable):** no new child-data tables; pseudonymous `student_ref`
only, **no child PII** in storage/tokens/logs; derived read models are disposable, Postgres is the
system of record; evidence is **append-only + idempotent**; **no generative AI offline** (audit
AR-C-06 — the teaching runtime is templated/pure, which is what makes offline safe); offline crisis
affordance must queue a safety flag on reconnect (doc 33 §8, doc 15).

---

## 1. Design principles (from doc 33 §2, made concrete)

- **Offline is a first-class mode, not a fallback.** A learner opens the app with no network and
  completes their day from cache.
- **Local-first writes.** Learning actions are written to a durable on-device queue first, then synced;
  the network is a background concern (doc 33 §2).
- **Deterministic sync, never silent loss.** Every write carries a client-generated idempotency key
  (`client_event_id`, a `uuid7`) and a Lamport `client_seq`; the server is authoritative and dedupes
  (`contexts/sync/domain.py`). No wall-clock ordering (audit AR-H-28).
- **Evidence is a grow-only set.** Because mastery is *derived* from append-only `AssessmentEvidence`
  and the decision engine is *pure*, offline evidence merges by union-on-`evidence_id` and the server
  **re-derives** mastery — so learning state is convergent and cannot be lost or double-counted.
- **Safety is never offline-optional.** No generative AI offline; content is pre-moderated at
  packaging; a distress affordance is always present and queues a priority safety flag.
- **Honest degradation.** No dead ends, no silent failures; the UI always states its true sync/cache
  status (the `OfflineBadge` pattern).

---

## 2. Component architecture

Extends `STUDENT_PORTAL_ARCHITECTURE.md §2`. New/expanded components are marked **[6.2]**.

```text
┌──────────────────────────── Browser (PWA, apps/web) ────────────────────────────┐
│  UI (student pages) ── OfflineBadge (exists)                                      │
│        │                                                                         │
│  View models / query cache                                                       │
│        │                                                                         │
│  ┌─────────────────── Offline core [6.2] ───────────────────┐                    │
│  │  Session saga + Checkpointer   Local progress (derived)   │                    │
│  │  Download manager              Evidence/attempt queue     │                    │
│  │  Package installer + verifier  Sync client (drain)        │                    │
│  └───────────────┬───────────────────────────┬──────────────┘                    │
│        API client (exists: ApiError code=OFFLINE, TokenProvider)                  │
│        │                    │                         │                           │
│  IndexedDB [6.2]      Cache Storage (SW)         Service Worker [6.2 expand]       │
│  (structured:         (byte assets:              (precache shell, runtime          │
│   queue, checkpoints,  app-shell, audio,          caching, Background Sync)        │
│   content JSON,        media, package blobs)                                       │
│   read-model cache,                                                               │
│   sync meta)                                                                      │
└──────────────────────────────────┬───────────────────────────────────────────────┘
                                    │  network (when available)
        ┌───────────────────────────┴───────────────────────────┐
        │  GET  /v1/learning/students/{ref}/*   (cacheable reads) │
        │  POST /v1/learning/sessions…          (queued when off) │
        │  POST /v1/sync/batch                  (drain the queue) │
        │  GET  package blobs (object storage / CDN, signed)      │
        │  GET  /auth/*                         (online only)     │
        └───────────────────────────┬───────────────────────────┘
                                    │
        Server (unchanged contexts) ── sync consumer [6.2, new] ── LearningUnitOfWork
              (learning) ── AssessmentEvidence (append-only) + LearningOutbox (atomic)
```

**Division of storage** (detailed in [OFFLINE_STORAGE_SPEC.md](OFFLINE_STORAGE_SPEC.md)): **Cache
Storage** (via the SW) holds byte assets — app shell, audio, images, package blobs. **IndexedDB** holds
structured data — the outbound write queue, session checkpoints, cached read-model JSON, content
`LessonView`/`ItemView` JSON, and sync metadata. This mirrors doc 33 §5.

---

## 3. Subsystem — Offline lesson packages

- **Purpose:** turn the opaque `Lesson.offline_package` reference into a real, verifiable, downloadable
  bundle of everything one lesson (or a day/week set) needs to run offline: content JSON
  (`LessonView`/`ItemView` — explanation, worked examples, practice/homework items, hints,
  `option_misconceptions`, corrections), audio segments + captions (per
  [AUDIO_SCRIPT_GUIDE.md](AUDIO_SCRIPT_GUIDE.md)), and visuals (`MediaRef` + alt-text).
- **Components:** (server, build-time) a **package builder** that resolves a published lesson into a
  **manifest** + assets and writes them to object storage (doc 09 pattern); (client) a **package
  installer** that fetches, verifies, and stages the bundle. **This builder does not exist yet — see
  §9 gap G1.**
- **Data flow:** publish lesson → builder assembles manifest `{package_id, lesson_ids, version,
  content_hash, assets[{ref, kind, sha256, bytes, url, locale}], signature, signing_key_id}` → store
  blobs + manifest metadata in Postgres → emit `OfflinePackageBuilt` (doc 33 §4) → client learns a pack
  is ready (dashboard `offline_packages_ready`, `STUDENT_API_REQUIREMENTS.md §2.2`) → download manager
  (§5) fetches + verifies → installed to Cache Storage (bytes) + IndexedDB (content JSON).
- **APIs used:** `GET` package manifest + blobs from object storage/CDN; `Lesson.offline_package` as the
  pointer; dashboard `offline_packages_ready`.
- **Failure modes:** missing/renamed asset; manifest/asset hash mismatch; partial download; pack version
  drift vs installed content; oversized pack on a low-end device.
- **Recovery strategy:** atomic install (stage → verify all hashes → flip manifest state to `ready`;
  never expose a half-installed pack); on hash mismatch discard + re-fetch; day-pack **lite by default**
  (doc 33 §4) to bound size; superseded packs retained until their queued writes drain (§ cache
  versioning).
- **Security considerations:** manifest is **Ed25519-signed**; installer verifies signature + per-asset
  SHA-256 before install (integrity from build to device — [OFFLINE_SECURITY_REVIEW.md](OFFLINE_SECURITY_REVIEW.md)
  §2). Content is pre-moderated at packaging (doc 33 §8) so **no unapproved content can reach a child**.
- **Performance considerations:** speech-optimized audio (~64–96 kbps mono, per audio guide); explicit,
  sized, user-initiated download (doc 33 §4); honor `Save-Data`; content JSON is small, media dominates.
- **Acceptance criteria:** a published lesson yields a signed manifest + hashed assets; the client
  installs it atomically; a tampered or truncated asset is rejected; an installed pack runs a lesson
  end-to-end with no network; pack size is reported to the user before download.

---

## 4. Subsystem — Service Worker architecture

- **Purpose:** make the app installable and its shell + cached assets available offline, and host
  background synchronization. Extends the existing scaffold `apps/web/public/sw.js` (currently
  precache `/` + manifest, GET-only network-first). **Registration wiring appears absent — gap G7.**
- **Components:** precache manifest (app shell); runtime caching router; a message channel to the app
  (download progress, cache status); Background Sync registration (§ sync spec). Cache names are
  **versioned** (§7).
- **Data flow:** install → precache shell into `taleem-shell-v{appVersion}` → activate → clean old
  caches → fetch handler routes by request type: **app shell** cache-first with SWR refresh; **content
  audio/media/package blobs** cache-first (immutable, content-hashed); **student read APIs**
  network-first with cache fallback (already the scaffold's intent); **writes** never cached — passed
  through, and when offline the app queues them (not the SW).
- **APIs used:** Service Worker API, Cache Storage API, `fetch` handler, `postMessage`, Background Sync
  API (`ServiceWorkerRegistration.sync`) with a foreground fallback (§8).
- **Failure modes:** SW not registered (no offline at all); stale SW serving old shell; caching a
  `401`/error; caching a non-GET; quota errors mid-cache.
- **Recovery strategy:** register the SW on app load (gap G7); controlled update via `skipWaiting` on an
  explicit user action (avoid disruptive silent swaps); never cache non-200 or non-GET (scaffold already
  guards non-GET); on cache write error fall through to network.
- **Security considerations:** the SW **never caches auth tokens or write responses**; scope limited to
  the app origin; only same-origin + trusted package host; integrity of packages is enforced by the
  installer (§3), not blind SW caching.
- **Performance considerations:** precache only the shell (small); lazy runtime-cache content on first
  use; SWR keeps the shell fresh without blocking; avoid over-precaching to protect low storage.
- **Acceptance criteria:** the app loads fully offline after first visit; the shell updates without a
  hard refresh but never mid-session without consent; no token or error response is ever cached; old
  cache versions are purged on activate.

---

## 5. Subsystem — Download manager

- **Purpose:** fetch, verify, and install offline packages reliably on weak/intermittent networks, with
  explicit user control and storage awareness.
- **Components:** a queue of pending package downloads; a chunked/resumable fetcher; a per-asset verifier
  (SHA-256); a storage pre-flight checker; progress reporting to the UI.
- **Data flow:** user (or "download today's lessons") requests a pack → pre-flight
  `navigator.storage.estimate()` + request `navigator.storage.persist()` → fetch manifest → verify
  signature → download assets (resumable, honoring `Save-Data`) → verify each SHA-256 → stage in Cache
  Storage/IndexedDB → flip manifest state to `ready` → report done. Progress + errors surface via the
  SW message channel / `OfflineBadge`-style status.
- **APIs used:** `fetch` (Range requests for resume), Cache Storage, IndexedDB, StorageManager
  (`estimate`, `persist`), Network Information (`navigator.connection.saveData`).
- **Failure modes:** interrupted download; hash mismatch; insufficient storage; server 5xx; a partially
  written pack after a crash.
- **Recovery strategy:** resumable ranged fetch; discard + retry on hash mismatch (bounded, backoff);
  atomic flip so a crashed install never presents as `ready`; on low storage defer + honest UI (§12);
  idempotent re-download (content-hash addressed).
- **Security considerations:** verify signature before trusting any asset (§3); only download from the
  configured in-region package host (residency — [OFFLINE_SECURITY_REVIEW.md](OFFLINE_SECURITY_REVIEW.md)
  §5); no credentials embedded in package URLs.
- **Performance considerations:** parallelize a small number of asset fetches; prefer day-pack lite;
  compress; resume rather than restart; schedule under Save-Data awareness.
- **Acceptance criteria:** a download interrupted at any point resumes without re-fetching completed
  assets; a corrupted asset is detected and refetched; a pack that would exceed available storage is
  refused with a clear message; download progress is visible and cancellable.

---

## 6. Subsystem — Cache versioning

- **Purpose:** keep the app shell, content, and packages correct across releases and content updates —
  never serve stale or mismatched content, never lose unsynced writes to an eviction.
- **Components:** app-shell cache name `taleem-shell-v{appVersion}`; **content-hash-addressed** package
  assets (immutable); package `version` + `content_hash` on the manifest; a migration/cleanup routine on
  SW `activate` and on schema version bumps (IndexedDB `version`).
- **Data flow:** a new app release bumps the shell cache version → `activate` deletes prior shell caches
  → content assets are addressed by `content_hash` so a changed lesson produces a **new** `package_id`
  (old retained until its queued writes drain, then eligible for eviction) → IndexedDB `onupgradeneeded`
  migrates structured stores by version.
- **APIs used:** Cache Storage (named caches), IndexedDB versioned upgrades, the manifest `version` /
  `content_hash`.
- **Failure modes:** shell/content version skew (new shell expecting new content shape); an IndexedDB
  migration failure; evicting content still referenced by an in-progress session.
- **Recovery strategy:** content is content-hash-addressed so shell can pin the exact version it needs;
  IndexedDB migrations are additive + reversible-safe (follow the repo's Alembic discipline in spirit);
  eviction policy **never** removes unsynced queue/checkpoints (§12).
- **Security considerations:** version identifiers are integrity-checked via the signed manifest; a
  downgrade to an unsigned/older pack is rejected by signature + `signing_key_id`.
- **Performance considerations:** immutable content caching maximizes reuse (no revalidation); only the
  small shell uses SWR.
- **Acceptance criteria:** upgrading the app purges old shell caches and keeps working offline;
  a content update installs as a new package without disturbing an in-progress session; an IndexedDB
  version bump migrates without data loss; no unsynced write is ever evicted by a version change.

---

## 7. Subsystem — Low-storage handling

- **Purpose:** operate on low-end devices with little free storage without ever losing learner writes.
- **Components:** storage pre-flight (StorageManager); an eviction planner (LRU over *disposable* data
  only); persistent-storage request; Save-Data awareness; honest low-storage UI states.
- **Data flow:** before any download, `estimate()` usage/quota → if insufficient, run the eviction
  planner over **disposable** data (fully-synced completed-lesson content, read-model caches) LRU-first →
  if still insufficient, refuse the download with a clear message and offer to remove installed lessons.
  Request `persist()` so the browser is less likely to evict under pressure.
- **APIs used:** StorageManager (`estimate`, `persist`, `persisted`), Cache Storage delete, IndexedDB
  delete; Network Information `saveData`.
- **Failure modes:** browser evicts data under pressure (non-persistent origin); quota exceeded mid-write;
  a shared device filling up across profiles.
- **Recovery strategy:** **queued writes + checkpoints are marked non-evictable and are never deleted
  before sync** (doc 33 §5); request persistent storage; degrade to lite packs; surface "free up space"
  actions; if the browser evicts disposable caches, transparently re-fetch on reconnect.
- **Security considerations:** eviction respects per-profile namespacing (shared-device isolation, doc
  33 §5) — never leak another profile's data while clearing space.
- **Performance considerations:** keep the durable queue small (deltas are tiny JSON); media is the
  storage cost — bias to lite/day packs; evict media before structured data.
- **Acceptance criteria:** with the queue non-empty, no low-storage condition deletes a queued write;
  a download that cannot fit is refused with actionable UI; persistent storage is requested; evicting to
  free space only removes fully-synced disposable data.

---

## 8. Subsystem — Connectivity recovery

- **Purpose:** detect when the network returns and drain the write queue + refresh disposable caches,
  reliably and without a thundering herd.
- **Components:** the existing `OfflineBadge` online/offline listeners; an active **reachability probe**
  (a cheap authenticated GET) because `navigator.onLine` is unreliable; a sync trigger; backoff+jitter.
- **Data flow:** `online` event or successful reachability probe → trigger the sync client to drain the
  queue via `POST /v1/sync/batch` (§ sync spec) → on success refresh disposable read-model caches and
  re-validate the offline auth token → update status UI. If a Background Sync registration exists, the SW
  wakes and drains even without the app foregrounded (§ sync spec).
- **APIs used:** `window` `online`/`offline`, `navigator.onLine`, a lightweight authenticated probe
  endpoint, Background Sync API, `visibilitychange`.
- **Failure modes:** `onLine` true but no real connectivity (captive portal); flapping connectivity;
  many clients reconnecting simultaneously; expired offline token on reconnect.
- **Recovery strategy:** confirm with an active probe before declaring online; **exponential backoff with
  jitter** on the drain loop; idempotent sync makes retries safe; re-validate/refresh the token on
  reconnect (doc 33 §7), re-queueing writes if auth must be refreshed.
- **Security considerations:** the probe is authenticated + cheap; token re-validation on reconnect
  enforces server-side revocation ("revoked session drops on next sync", doc 33 §7).
- **Performance considerations:** jittered backoff avoids synchronized reconnect storms; batch the drain
  (one `sync.batch` call per cycle, not per delta).
- **Acceptance criteria:** a queue drains automatically within a bounded time of real connectivity
  returning; a captive-portal false-positive does not corrupt state; simultaneous reconnects do not
  overload the server (jitter verified); an expired token triggers a clean refresh, not data loss.

---

## 9. Subsystem — Telemetry and diagnostics

- **Purpose:** measure offline health (a Pilot success input) and give support/mentors diagnostics —
  **without** any child PII or content.
- **Components:** a privacy-preserving counter set; a local redacted ring-buffer diagnostic log; a
  diagnostics sync channel (consent + residency gated).
- **Data flow:** offline events increment local counters (download success/fail, bytes, sync latency,
  batch size, duplicate/conflict/ignored counts, integrity failures, storage-pressure events, offline
  session count) → a small ring buffer keeps recent redacted diagnostic lines → on sync, aggregated
  counters are sent through the diagnostics channel (pseudonymous/`device_id` only), respecting consent.
- **APIs used:** local IndexedDB counters; the sync/diagnostics channel; StorageManager/Network
  Information for context.
- **Failure modes:** telemetry accidentally capturing content or `student_ref`-linked detail; unbounded
  log growth; telemetry sent without consent or out of region.
- **Recovery strategy:** schema-restrict telemetry to counters + enums (no free text, no content); bound
  the ring buffer; **gate all telemetry egress on consent + residency** (governance); drop silently if
  not permitted.
- **Security considerations:** classes C1/C0 only (`docs/14-privacy-model.md`); **no C2/C3 data** in
  telemetry; no `student_ref` in diagnostics payloads (use `device_id`); in-region egress.
- **Performance considerations:** counters are cheap; batch diagnostics with the normal sync cycle; ring
  buffer is fixed-size.
- **Acceptance criteria:** telemetry never contains child PII, content, or `student_ref`; diagnostics are
  suppressed without consent; counters reconcile with observed download/sync events; the diagnostic log
  is bounded.

---

## 10. Cross-reference matrix (design decision → existing implementation)

| Design decision | Conforms to / reuses | Evidence |
| --- | --- | --- |
| Delta types + batch shape | `DeltaType`, `SyncDelta(client_event_id,type,entity_key,payload,client_seq)` | `contexts/sync/domain.py` |
| Idempotency key generation | `uuid7()` client-safe | `platform/ids.py` |
| Ordering (no wall-clock) | `apply_batch` orders `(client_seq, client_event_id)`; server version counter | `contexts/sync/domain.py` (AR-H-28) |
| Conflict rules | progress=monotonic-max, completion=idempotent-set, attempt=append-only-union, preference=server-order | `contexts/sync/domain.py` |
| Evidence convergence | append-only, idempotent by `evidence_id`; mastery re-derived | `persistence/repository.py:69`, `domain/knowledge.py` |
| Atomic state+event | `LearningUnitOfWork` (knowledge + outbox in one commit) | `adapters/persistence/uow.py` |
| Cacheable reads | GET, derived, learner-scoped, no new child tables | `adapters/student_api.py` |
| Queued writes | session `:answer` / `homework.submit` reuse evidence path | `adapters/api.py`, `STUDENT_API_REQUIREMENTS.md` |
| Offline signal in client | `ApiError(0,{code:"OFFLINE"})` | `apps/web/lib/student/api.ts` |
| Offline status UI | `OfflineBadge` `pendingCount`, `aria-live` | `apps/web/components/student/OfflineBadge.tsx` |
| SW caching intent | app-shell cache-first, GET-only | `apps/web/public/sw.js` |
| Device-bound offline token | `Claims.device_id` already present | `auth/jwt_verifier.py`, doc 11 |
| No-gen-AI-offline | templated runtime only (pure) | AR-C-06, doc 33 §8 |
| Local persistence split | Cache Storage (bytes) + IndexedDB (structured) | doc 33 §5 |

---

## 11. Central architectural decision — how a "full session" runs offline

The exit criterion "a full session runs offline and syncs with no double-counting" (WS13) hides one
real decision: **the teaching/decision runtime is server-side Python** (`contexts/learning` decision
engine + templated runtime — pure, deterministic, no LLM). Running a *full* session offline needs those
decisions on-device. Three options:

| Option | What it means | Cost | Fit |
| --- | --- | --- | --- |
| **A — Offline-lite (cache + queue)** | Cache content for viewing + queue attempts; decisions/mastery computed on the server at sync. Learner sees content and answers; adaptive next-step confirmed on reconnect. | Low | **Pilot 1 (Wi-Fi supervised)** — PILOT_PLAN says offline-lite suffices |
| **B — Port the pure runtime to TypeScript** | Re-implement the *pure, deterministic* decision engine + templated runtime client-side, driven by the packaged `LessonView`. Full offline adaptivity; server re-derives on sync (evidence is SoR, so results converge). | High (new code, but mirrors existing pure logic — **not** a redesign) | Pilot 2+ full at-home offline |
| **C — Pre-compute decision tree per lesson** | Bake the bounded branching per lesson into the pack. | Medium; brittle for rich adaptivity | Narrow lessons only |

**Recommendation:** **Option A for Pilot 1** (matches PILOT_PLAN's Wi-Fi-supervised offline-lite),
**Option B as the 6.2B/fast-follow** for full at-home offline (Pilot 2). Option B is the single largest
new-code item; it is a faithful port of existing pure functions, kept deterministic and LLM-free, so it
does **not** redesign the learning domain — it mirrors it. Recorded as gap **G2**.

---

## 12. Architectural gaps (separate from the design)

These are gaps in the **current implementation** that this design depends on. None is a redesign of a
completed system; each is either net-new or an extension, and the ones that would touch completed
systems are framed as recommendations.

| ID | Gap | Nature | Touches completed system? | Recommendation |
| --- | --- | --- | --- | --- |
| **G1** | `offline_package` is only a string — no builder/manifest/checksum/signing pipeline | Net-new build-time component (Curriculum Studio / media) | No | Build the package builder + signed manifest (§3) |
| **G2** | Full offline session needs the runtime on-device (server-side today) | Net-new client port (Option B) | No (mirrors pure logic) | Offline-lite for Pilot 1; port for Pilot 2 (§11) |
| **G3** | Sync engine is an in-memory **synthetic** prototype, not wired to durable evidence/outbox | Net-new **sync consumer** translating `SyncDelta` → `AssessmentEvidence` via `LearningUnitOfWork` | Extends sync + adds a learning-side idempotent consumer; does **not** change the learning domain | Design + build the durable sync consumer (see [OFFLINE_SYNC_SPEC.md](OFFLINE_SYNC_SPEC.md) §5) |
| **G4** | Server sessions are **in-memory** (not durable) | Reconciliation is easier with durable sessions | Yes — but already planned as WS15/H1 | **Recommendation**, not required (evidence is SoR); align to WS15 |
| **G5** | Durable server-side idempotency for `client_event_id` (prototype dedupes in memory only) | Small net-new: persist seen `client_event_id` + sync cursor | Extends sync store | Persist the idempotency ledger + cursor so replays survive restarts |
| **G6** | Child-safe auth + device-bound offline token spec'd but **governance-gated** | Blocked by Phase-1.5 gate; only dev stub exists | No (net-new, gated) | **Dependency/blocker** — cannot build until M-Gov; use dev stub for internal only |
| **G7** | SW registration wiring + IndexedDB layer + Background Sync absent (scaffold only) | Net-new frontend | No | Bulk of 6.2A/B |
| **G8** | Web manifest icons empty; no `Save-Data`/`persist` handling | Minor net-new | No | Complete in 6.2A |

---

## 13. Phased implementation plan (6.2A / 6.2B / 6.2C)

Effort bands: S ≤ ~1 wk-team, M ~2–4, L ~4–8 (indicative, staffing-dependent). Nothing here is
implemented in this phase — this is the plan awaiting approval.

### Phase 6.2A — Offline foundations (read + durable local store) — **offline-lite**

- **Scope:** SW registration + robust versioned caching (§4, §6); IndexedDB layer + stores
  ([OFFLINE_STORAGE_SPEC.md](OFFLINE_STORAGE_SPEC.md)); **package builder + signed manifest (G1)**;
  download manager + low-storage handling (§5, §7); cache student read models for offline viewing;
  connectivity recovery (§8); manifest icons + Save-Data/persist (G8).
- **Outcome:** a learner browses today/lessons/content **offline** from cache; attempts are captured
  locally (queued) but adaptivity/mastery confirm on reconnect (Option A). Satisfies Pilot-1 offline-lite.
- **Effort:** M–L. **Dependencies:** WS4/WS5 packaged content + audio (packs to build); object storage
  for blobs.

### Phase 6.2B — Offline sessions + real sync (the hard core)

- **Scope:** client **session saga + checkpointing** ([OFFLINE_SYNC_SPEC.md](OFFLINE_SYNC_SPEC.md) §2);
  local **evidence/attempt queue**; **durable sync consumer (G3)** wiring `POST /v1/sync/batch` →
  `AssessmentEvidence` via `LearningUnitOfWork` idempotently; **Background Sync** + conflict resolution
  (sync spec §3–4); durable idempotency ledger (G5); **Option B runtime port (G2)** for full offline
  adaptivity.
- **Outcome:** a **full session runs offline and syncs with no double-counting** (WS13 exit).
- **Effort:** L. **Dependencies:** 6.2A; durable sync consumer design sign-off; runtime-port decision
  (§11); **recommended** WS15 durable sessions (G4).

### Phase 6.2C — Hardening, security, safety, telemetry

- **Scope:** end-to-end **signing/integrity** verification ([OFFLINE_SECURITY_REVIEW.md](OFFLINE_SECURITY_REVIEW.md)
  §2); **at-rest encryption** of C2 data in IndexedDB (§3 of the security review); **device-bound offline
  auth token (G6)** — governance-gated; **telemetry/diagnostics** (§9); **offline safety crisis flag**
  (queue + priority sync, doc 33 §8, doc 15); eviction polish; **device matrix + chaos tests**
  ([OFFLINE_TEST_PLAN.md](OFFLINE_TEST_PLAN.md)).
- **Outcome:** offline is secure, safe, observable, and proven on low-end devices and flaky networks.
- **Effort:** M. **Dependencies:** 6.2A/B; **M-Gov** governance gate (auth token); **M-Safe** (crisis
  flag routing); consent for telemetry.

---

## 14. GO / NO-GO — implementation readiness

**Design verdict: GO.** The offline design is fully expressible within the existing architecture,
naming, APIs, and bounded contexts; the conflict/idempotency contract already exists and is tested
(`test_sync_engine.py`); evidence being append-only + server-derived makes offline learning provably
convergent (no data loss, no double-count). No completed system is redesigned.

**Implementation readiness — phased:**

- **Phase 6.2A — GO to implement.** No blocking dependency beyond WS4/WS5 content (already in progress).
  Offline-lite satisfies Pilot 1 (Wi-Fi supervised). Recommend starting here.
- **Phase 6.2B — CONDITIONAL GO.** Proceed once: (1) the **durable sync consumer** design (G3) is signed
  off; (2) the **Option A vs B** decision (§11) is confirmed (recommend A for Pilot 1, B as fast-follow);
  (3) ideally **WS15 durable sessions** (G4) is scheduled. None is a blocker for *correctness* of the
  pilot; all are blockers for *full at-home offline*.
- **Phase 6.2C — NO-GO until gates clear.** The device-bound offline auth token (G6) is **blocked by the
  Phase-1.5 governance gate (M-Gov)**; the safety crisis-flag routing depends on **M-Safe**; telemetry
  depends on **consent**. Build behind these gates only.

**Recommended path:** approve **6.2A now** (build offline-lite foundations + package builder + durable
local store) and the **6.2B durable sync consumer design**; hold 6.2C for M-Gov/M-Safe. This lands
Pilot-1 offline-lite on the critical path without waiting on governance, and stages full at-home
offline for Pilot 2.
