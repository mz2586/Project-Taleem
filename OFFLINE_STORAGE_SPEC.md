# Offline Storage Specification (Design Review)

Status: **Design review only (Phase 6.2). No code, no source changes, no commits.** Covers subsystems
**(3) IndexedDB schema** and **(5) Local progress storage**. Companion to
[OFFLINE_ARCHITECTURE.md](OFFLINE_ARCHITECTURE.md), [OFFLINE_SYNC_SPEC.md](OFFLINE_SYNC_SPEC.md),
[OFFLINE_SECURITY_REVIEW.md](OFFLINE_SECURITY_REVIEW.md), [OFFLINE_TEST_PLAN.md](OFFLINE_TEST_PLAN.md).

Conforms to `docs/02-architecture/33-offline-architecture.md §5` (the local-persistence table) and
`docs/12-student-experience/STUDENT_PORTAL_ARCHITECTURE.md §4`. **No new child-data tables on the
server**; on-device stores are either **disposable caches** (re-fetchable) or a **durable outbound
queue** of immutable facts (never lost before sync). Pseudonymous `student_ref` only; **no child PII**.

---

## 0. Storage division (which API holds what — from doc 33 §5)

| Data | Store | API | Durability | PII class |
| --- | --- | --- | --- | --- |
| App shell (HTML/CSS/JS) | `taleem-shell-v{appVersion}` | **Cache Storage** | disposable | C0 |
| Audio segments, images, package blobs | content caches (content-hash keyed) | **Cache Storage** | disposable | C0 |
| Lesson content JSON (`LessonView`/`ItemView`) | `content` | **IndexedDB** | disposable | C0 |
| Cached read-model responses (today/homework/…) | `read_cache` | **IndexedDB** | disposable | C2 (learning) |
| **Outbound write queue** (attempts/deltas) | `evidence_queue` | **IndexedDB** | **durable — never evict before sync** | C2 |
| **Session checkpoints** | `checkpoints` | **IndexedDB** | **durable — never evict before sync** | C2 |
| Local derived progress snapshot | `progress_local` | **IndexedDB** | disposable (re-derived on sync) | C2 |
| Sync metadata (cursor, seen ids, device id) | `sync_meta` | **IndexedDB** | durable | C1 |
| Dead-lettered deltas | `dead_letter` | **IndexedDB** | durable (until support-cleared) | C2 |
| Client-only preferences (locale, notif read-state) | `prefs` | **IndexedDB** | durable, device-local | C1 |
| Package install registry | `packages` | **IndexedDB** | durable | C0 |
| Offline auth/session token (6.2C, gated) | `auth` | **IndexedDB (encrypted)** | durable, short-TTL | C1 |

Rule of thumb: **Cache Storage for bytes, IndexedDB for structured data.** Anything the server can
re-derive is disposable; only the **queue + checkpoints** are irreplaceable and therefore protected from
eviction (`OFFLINE_ARCHITECTURE.md` §7).

---

## 1. Subsystem — IndexedDB schema

- **Purpose:** a single versioned IndexedDB database (`taleem-offline`) holding all structured offline
  state, with object stores + indexes that make sync draining, checkpoint resume, and offline reads
  efficient and correct.
- **Components:** the database `taleem-offline` at schema `version = N`; object stores below; an
  `onupgradeneeded` migration routine (additive, per cache-versioning §6 of the architecture).

### Object stores (keyPath + indexes)

```text
DB: taleem-offline (version N)  — one DB per device; per-profile namespacing on shared devices (§4)

store  packages          keyPath: package_id
        indexes: by_lesson (lesson_ids, multiEntry), by_state (state), by_version (content_hash)
        record: { package_id, lesson_ids[], content_hash, version, state('downloading'|'ready'|'superseded'),
                  total_bytes, signing_key_id, signature_ok(bool), installed_at, last_used_at }

store  content           keyPath: [lesson_id, version]
        indexes: by_lesson (lesson_id)
        record: { lesson_id, version, objective_code, lesson_view(JSON: explanation, worked_examples,
                  items[ItemView incl hints, option_misconceptions, corrections], homework, misconceptions },
                  audio_index[], visual_index[] }   // bytes live in Cache Storage, keyed by ref

store  read_cache        keyPath: cache_key            // e.g. "today:{student_ref}"
        indexes: by_student (student_ref), by_fetched_at (fetched_at)
        record: { cache_key, student_ref, endpoint, body(JSON), etag?, fetched_at, ttl_ms }

store  evidence_queue    keyPath: client_event_id       // uuid7
        indexes: by_seq (client_seq), by_state (sync_state), by_session (session_id)
        record: { client_event_id, client_seq, type(DeltaType), entity_key, payload(JSON: evidence fields),
                  session_id, sync_state('pending'|'sent'|'applied'|'failed'), attempts, created_at }

store  checkpoints       keyPath: session_id            // uuid7 (client-generated)
        indexes: by_student (student_ref), by_updated (updated_at)
        record: { session_id, student_ref, state, current_objective, current_item, interactions[],
                  hints_used, client_seq, updated_at }

store  progress_local    keyPath: [student_ref, objective_code]
        record: { student_ref, objective_code, mastery, state, updated_at }   // disposable; re-derived

store  sync_meta         keyPath: key                   // e.g. "cursor", "device_id", "last_sync_at"
        record: { key, value }

store  dead_letter       keyPath: client_event_id
        record: { client_event_id, type, payload, attempts, last_error, created_at }

store  prefs             keyPath: key                   // "locale", "notif_read:{id}", ...
        record: { key, value, updated_at }

store  auth (6.2C, encrypted, governance-gated)   keyPath: "session"
        record: { ciphertext, iv, expires_at }         // device-bound offline token, C1, short TTL
```

- **Data flow:** writes land in `evidence_queue` + `checkpoints` (durable); reads hydrate from
  `read_cache`/`content`; the sync drain reads `evidence_queue` ordered by `by_seq`; migrations run in
  `onupgradeneeded`.
- **APIs used:** IndexedDB (transactions, indexes, cursors, versioned upgrades); Cache Storage for the
  byte assets referenced by `content.audio_index`/`visual_index`/`packages`.
- **Failure modes:** IndexedDB unavailable/blocked (private mode, storage disabled); an aborted upgrade
  transaction; a version mismatch across tabs; quota exceeded on write; a corrupt record.
- **Recovery strategy:** feature-detect IndexedDB and degrade to **online-only** with an honest banner if
  absent (never silently fail); **additive, transactional migrations** (abort → keep old version intact);
  coordinate multi-tab upgrades via the `versionchange`/`blocked` events; on `QuotaExceededError` invoke
  low-storage handling (architecture §7) — **never** dropping `evidence_queue`/`checkpoints`; validate
  records on read and quarantine corrupt ones to `dead_letter`.
- **Security considerations:** C2 stores (`evidence_queue`, `checkpoints`, `read_cache`, `progress_local`)
  hold learning data → **encrypted at rest** (Web Crypto AES-GCM, security review §3); **no C3 child
  PII** is ever stored (only `student_ref`); per-profile namespacing + clear-on-switch for shared devices.
- **Performance considerations:** indexes chosen for the hot paths (drain by `client_seq`, resume by
  `session_id`, cache lookup by `cache_key`); structured records are small; bytes are offloaded to Cache
  Storage; avoid large single transactions.
- **Acceptance criteria:** all stores + indexes create cleanly at version N; an upgrade from N-1 migrates
  without data loss; the drain reads deltas in `client_seq` order; a resume finds the latest checkpoint
  by `session_id`; a corrupt record is quarantined, not fatal; with IndexedDB unavailable the app runs
  online-only with a clear message.

---

## 2. Subsystem — Local progress storage

- **Purpose:** show the learner their progress, today's plan, homework, reviews, and achievements
  **offline**, while keeping the server the **system of record** — the device never becomes an
  authoritative store of child learning state.
- **Components:** the **disposable read caches** (`read_cache` — mirrors of `/v1/learning/students/{ref}/*`
  GET responses); the **disposable local progress snapshot** (`progress_local`); the **durable outbound
  queue** (`evidence_queue`) which is the only local *source of truth*, and only for un-synced immutable
  facts.
- **Data flow:**
  - **Reads (offline):** the app serves `today`, `homework`, `assessments`, `reviews`, `timetable`,
    `notifications`, `achievements`, `history`, `recommendations` from `read_cache` when offline (SW
    network-first → cache fallback). These are **snapshots**, labelled with `fetched_at`, and refreshed
    on reconnect.
  - **Optimistic local progress (Option A/B, architecture §11):** as the learner answers offline, the app
    updates `progress_local` optimistically for a responsive UI, and enqueues the underlying
    `attempt.submitted` fact. On sync, the server **re-derives** mastery and the client **replaces**
    `progress_local` with the server-derived values — the optimistic snapshot is never authoritative.
  - **Read-state (notifications):** tracked in `prefs` (`notif_read:{id}`) because the server keeps **no
    read-state table** (`student_queries.py:152`); the `POST …/notifications/{id}:read` is a server no-op,
    so read-state is legitimately device-local.
- **APIs used (read, cacheable):** the derived GET endpoints in
  `contexts/learning/adapters/student_api.py`; on reconnect, refreshed via the same endpoints; writes via
  `POST /v1/sync/batch`.
- **Failure modes:** stale cache shown as if live; an optimistic local mastery diverging from the server;
  a shared device showing one child's progress to another; unbounded cache growth.
- **Recovery strategy:** always **label** cached reads with age (`fetched_at`) and show honest "as of …"
  status (the `OfflineBadge` ethos); on reconnect **refresh then reconcile** — server-derived progress
  replaces optimistic values (monotonic-max ensures no visible regression from a genuine gain); per-
  profile namespacing + **clear cached view on learner switch** (portal arch §6); TTL + LRU on
  `read_cache`.
- **Security considerations:** caches are C2 → encrypted at rest; scoped by `student_ref`; **cleared on
  learner switch and on de-enrolment/consent-withdrawal signal** at next connect (retention, security
  review §5); no PII cached.
- **Performance considerations:** read caches are small JSON; serve instantly offline; refresh in the
  background on reconnect; prefer the aggregated `dashboard.today` (portal arch §5) to minimize cache
  entries.
- **Acceptance criteria:** every student read screen renders offline from cache with a visible "as of"
  timestamp; optimistic progress updates immediately and is replaced by server-derived values on sync
  with no visible regression; switching learners on a shared device clears the prior cached view; caches
  never contain child PII and are cleared on de-enrolment at next connect.

---

## 3. Quotas, retention, and eviction (cross-cutting)

- **Quota:** use `navigator.storage.estimate()` before downloads; request `navigator.storage.persist()`
  to reduce eviction risk; honor `Save-Data` with lite packs (architecture §5, §7).
- **Eviction order (LRU over disposable only):** app-shell (re-fetchable) → content byte assets →
  `read_cache`/`progress_local` → **never** `evidence_queue`/`checkpoints`/`dead_letter` until drained
  (doc 33 §5).
- **Retention (align to `docs/57-data-retention-schedule.md`):** disposable caches carry a TTL;
  `evidence_queue` entries are removed **only** once `applied`/`duplicate`; on **de-enrolment or consent
  withdrawal**, the server signals a purge and the client clears all C2 stores at next connect
  (recommendation — see security review §5). Server-side, synced evidence lands through the existing
  `hash(student_ref)`-sharded, retention-partitioned tables (doc 09, audit AR-C-11) — offline changes
  nothing about server retention.
- **Shared devices:** namespace every store by profile; **encrypt** C2 data; clear the active profile's
  cached view on "switch learner" (portal arch §6).

---

## 4. Cross-reference (storage decision → existing implementation)

| Storage decision | Conforms to | Evidence |
| --- | --- | --- |
| Cache Storage (bytes) + IndexedDB (structured) split | doc 33 §5 local-persistence table | `docs/02-architecture/33-offline-architecture.md` |
| Queue/checkpoints never evicted before sync | doc 33 §5 "queued writes never evicted" | same |
| No new child-data tables; read-state device-local | `student_queries.py:152` no-op `:read` | `contexts/learning/adapters/student_api.py` |
| Server re-derives progress; local is disposable | evidence append-only + derived read models | `persistence/repository.py:69`, portal arch §4 |
| `student_ref` only, no PII; class C1/C2/C3 handling | `docs/14-privacy-model.md §4-5` | privacy model |
| Client-generated ids (`session_id`, `evidence_id`, `client_event_id`) | `uuid7()` client-safe | `platform/ids.py` |
| Cacheable read endpoints | GET derived student APIs | `contexts/learning/adapters/student_api.py` |
| Per-profile namespacing + clear-on-switch | portal arch §6 shared-device | `STUDENT_PORTAL_ARCHITECTURE.md` |

**Gaps referenced:** the IndexedDB layer + these stores do not exist yet (scaffold only, gap **G7**) —
net-new frontend work in 6.2A/B; at-rest encryption + de-enrolment purge are 6.2C (security review §3,
§5). No completed server system is modified by this storage design.
