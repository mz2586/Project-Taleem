# Offline Sync Specification (Design Review)

Status: **Design review only (Phase 6.2). No code, no source changes, no commits.** Covers subsystems
**(6) Session checkpointing, (7) Background synchronization, (8) Conflict detection, (9) Conflict
resolution**. Companion to [OFFLINE_ARCHITECTURE.md](OFFLINE_ARCHITECTURE.md),
[OFFLINE_STORAGE_SPEC.md](OFFLINE_STORAGE_SPEC.md),
[OFFLINE_SECURITY_REVIEW.md](OFFLINE_SECURITY_REVIEW.md), [OFFLINE_TEST_PLAN.md](OFFLINE_TEST_PLAN.md).

**This spec conforms to an existing, tested contract — it does not invent one.** The delta types,
batch shape, ordering, and conflict rules are already implemented as a synthetic prototype in
`services/core-api/src/taleem_core/contexts/sync/domain.py` (endpoint `POST /v1/sync/batch`, tested in
`services/core-api/tests/test_sync_engine.py`). The job of Phase 6.2 is to **wire that contract to the
durable learning evidence/outbox path** (gap **G3**) and add the **client-side** checkpointing + drain.

---

## 0. The existing contract (reused verbatim)

From `contexts/sync/domain.py`:

- **`DeltaType`** — `progress.updated`, `lesson.completed`, `attempt.submitted`, `preference.set`.
- **`SyncDelta(client_event_id, type, entity_key, payload, client_seq)`** — `client_event_id` is a
  `uuid7` idempotency key (`platform/ids.py`); `client_seq` is a **Lamport** sequence, **not wall-clock**
  (audit AR-H-28).
- **`apply_batch`** orders by `(client_seq, client_event_id)`, dedupes on seen `client_event_id`, and
  returns per-item **`ItemResult(client_event_id, status, server_version)`** where **`Status`** ∈
  `applied | duplicate | ignored | conflict`.
- **Server version** (`server_cursor` / `version`) is **server-incremented** — the clock-skew fix.
- **Conflict rules (already coded + tested):** progress = monotonic max (never regress);
  `lesson.completed` = idempotent set; `attempt.submitted` = append-only union (dedupe on `attempt_id`);
  `preference.set` = server-order-wins.
- **PDP** already grants `(system, write, sync.batch)` (`auth/pdp.py:54`).

The batch envelope (from `docs/02-architecture/10-api-design.md §6`): `POST /v1/sync/batch` with
`{cursor, deltas:[{clientEventId, type, payload}]}` → per-item results + a new `cursor`.

---

## 1. What syncs, and why it converges

| DeltaType | Client source | Server destination (durable) | Convergence property |
| --- | --- | --- | --- |
| `attempt.submitted` | an answered practice/homework/assessment item (mirrors session `:answer`) | **`AssessmentEvidence`** append-only via `LearningUnitOfWork` | grow-only set, dedupe on `evidence_id` → **CRDT-like**, no loss/double-count |
| `progress.updated` | optimistic local mastery snapshot (derived) | recomputed server-side from evidence; stored `objective_mastery` | monotonic max; server re-derivation is authoritative |
| `lesson.completed` | a finished lesson/objective | derived from evidence + outbox events | idempotent set union |
| `preference.set` | client-only prefs (e.g. locale, notification read-state) | **no new child-data table** — device-local; server-order-wins if ever server-side | LWW by server order, never client clock |

**The key correctness argument.** `attempt.submitted` carries exactly the fields of an
`AssessmentEvidence` row (`evidence_id`, `student_ref`, `objective_code`, `item_ref`, `session_id`,
`outcome`, `misconception_hits`, `hints_used`, `response_time_ms`, `occurred_at`). Because evidence is
**append-only and idempotent by `evidence_id`** (`repository.py:69` inserts only ids `not in
stored_ids`) and mastery is **re-derived** by the pure decision engine, syncing offline attempts is a
**set union of immutable facts**. `progress.updated` and `lesson.completed` are *derived* and therefore
never authoritative on the client — the server recomputes them. This is the "evidence is append-only
and never conflicts; derived state recomputed server-side; mirrors the platform's outbox/idempotent-
consumer design" property from `STUDENT_PORTAL_ARCHITECTURE.md §4`.

---

## 2. Subsystem — Session checkpointing

- **Purpose:** let a learner pause/resume/recover a session offline with zero loss, given that
  **server-side sessions are in-memory** (`contexts/learning/adapters/memory.py`) and thus not durable.
  The **client** is the durability layer for an in-flight session (by design, doc 33 / portal arch).
- **Components:** a client-side **session saga** in IndexedDB (`checkpoints` store,
  [OFFLINE_STORAGE_SPEC.md](OFFLINE_STORAGE_SPEC.md) §3); a checkpointer that writes after each state
  transition; a resumer that rehydrates on app open.
- **Data flow:** start a session offline → generate `session_id = uuid7()` client-side → after **every**
  interaction (teach → answer → outcome), write a checkpoint `{session_id, student_ref, state,
  current_objective, current_item, interactions[], hints_used, client_seq}` mirroring the server
  `Session`/`Interaction` aggregate shape (`domain/session.py`) → each answered item also enqueues an
  `attempt.submitted` delta (§3). On resume, load the latest checkpoint and continue from `state`.
- **APIs used:** IndexedDB (transactional write per interaction); `uuid7()` for `session_id` +
  `evidence_id` + `client_event_id`; on reconnect, `POST /v1/sync/batch` to drain the enqueued attempts.
- **Failure modes:** app killed mid-interaction; a checkpoint partially written; the server never saw
  this session (in-memory, lost) so there is no server session to "resume"; two devices resume the same
  session.
- **Recovery strategy:** checkpoints are written in a **single IndexedDB transaction** per interaction
  (atomic — either the interaction + its queued delta both commit or neither); resume replays from the
  last committed checkpoint; **the server does not need the session** because the *evidence* deltas carry
  everything to reconstruct `AssessmentEvidence` idempotently — a lost server session is not data loss;
  a second device replays the same `evidence_id`s → deduped to a no-op. Durable server sessions (WS15/H1,
  gap G4) would make live cross-device handoff cleaner — **recommended, not required**.
- **Security considerations:** checkpoints hold C2 learning data → encrypted at rest (security review
  §3); `student_ref` only, no PII; per-profile namespaced on shared devices.
- **Performance considerations:** a checkpoint is small structured JSON; one IndexedDB write per
  interaction is cheap; no media in checkpoints.
- **Acceptance criteria:** killing the app mid-session and reopening resumes at the exact last completed
  interaction with no lost or duplicated attempts; a session started fully offline syncs its attempts on
  reconnect with the server recording each exactly once; resuming the same session on a second device
  does not double-count.

---

## 3. Subsystem — Background synchronization

- **Purpose:** drain the local write queue to the server reliably, in order, exactly-once-effect, in the
  background where the platform allows it.
- **Components:** the **outbound queue** (`evidence_queue` store); a **drain worker** (Background Sync in
  the SW where available, foreground fallback otherwise); a batch builder; a cursor/idempotency tracker
  (`sync_meta` store).
- **Data flow:** each offline write appends a `SyncDelta` to the queue with `client_event_id = uuid7()`
  and a monotonically increasing `client_seq` → on connectivity (§ connectivity recovery) the drain
  worker builds a batch **ordered by `(client_seq, client_event_id)`**, includes the last `cursor`, and
  `POST /v1/sync/batch` → server `apply_batch` returns `ItemResult[]` + new `cursor` → the worker marks
  each delta by status (`applied`/`duplicate` → remove; `ignored` → remove with a note; `conflict` →
  apply resolution §4) → persists the new `cursor` → repeats until the queue is empty.
- **APIs used:** Background Sync API (`ServiceWorkerRegistration.sync.register('sync-evidence')`) with a
  foreground fallback on `online`/`visibilitychange`; `POST /v1/sync/batch`; IndexedDB queue/cursor.
- **Failure modes:** partial batch success then network drop; server 5xx; the tab closed mid-drain;
  Background Sync unsupported (fallback needed); token expired mid-drain; a poison delta that always
  errors.
- **Recovery strategy:** the queue is the source of truth — nothing is removed until its `ItemResult`
  confirms `applied`/`duplicate`; **idempotency makes re-sending safe** (server dedupes on
  `client_event_id` + `evidence_id`); **exponential backoff with jitter**; Background Sync retries
  automatically, foreground fallback drains on next `online`/visibility; a delta that fails N times is
  **dead-lettered** (`dead_letter` store) and surfaced honestly to support/mentor rather than blocking
  the queue.
- **Security considerations:** the drain is authenticated (bearer / offline token); the server enforces
  PDP `(system, write, sync.batch)` and re-validates the token (revocation on reconnect); no PII in
  deltas.
- **Performance considerations:** **one batch call per cycle**, not one per delta; cap batch size and
  page large queues; jitter prevents reconnect storms; deltas are tiny.
- **Acceptance criteria:** replaying a batch (same `client_event_id`s) yields `duplicate` and changes
  nothing (matches `test_sync_engine.py`); a drain interrupted mid-batch resumes without loss or
  double-apply; a poison delta is dead-lettered without stalling the rest; the queue reaches empty after
  connectivity returns.

---

## 4. Subsystem — Conflict detection

- **Purpose:** identify, deterministically and server-side, when a synced delta collides with existing
  state — without relying on client wall-clock.
- **Components:** the server `apply_batch` (existing); the `client_event_id` dedupe set; the type-specific
  comparators; the server version counter.
- **Data flow:** for each delta in `(client_seq, client_event_id)` order: **seen `client_event_id`?** →
  `duplicate`. Else evaluate by type — progress lower-or-equal than stored → `ignored` (monotonic
  regression); completion already set → `duplicate`/idempotent; attempt `evidence_id`/`attempt_id`
  already present → `duplicate`; preference concurrent with a newer server version → `conflict`
  (server-order-wins). Emit `ItemResult{status, server_version}`.
- **APIs used:** `apply_batch` return values; `server_version` counters; `evidence_id`/`client_event_id`
  ledgers.
- **Failure modes:** a client that reuses a `client_event_id` for different content (would be wrongly
  deduped); clock-skew-based ordering (avoided — Lamport `client_seq` only); the in-memory prototype
  losing its seen-set on restart (gap **G5**).
- **Recovery strategy:** `client_event_id` must be a fresh `uuid7` per logical write (client invariant,
  test-enforced); ordering uses `client_seq` + server tiebreak, never wall-clock; **persist the
  idempotency ledger + cursor** (G5) so detection survives server restarts.
- **Security considerations:** detection is server-authoritative (deny-by-default); a malicious client
  cannot force acceptance of a regressed or unauthorized state (server recomputes; PDP + IDOR still
  apply upstream on the read/session paths).
- **Performance considerations:** detection is O(batch) with hash-set lookups; the ledger is indexed by
  `client_event_id`; sharded by `hash(student_ref)` in line with the existing partitioning (doc 09).
- **Acceptance criteria:** a duplicate `client_event_id` is detected as `duplicate` every time; a
  regressed progress delta is `ignored`, not applied; detection is identical regardless of device clock;
  after a simulated server restart, previously-seen deltas are still detected (once G5 lands).

---

## 5. Subsystem — Conflict resolution

- **Purpose:** resolve detected collisions deterministically, preserving learner effort and never
  double-counting — using the **already-defined** rules, extended to the durable evidence path.
- **Components:** the type-specific resolvers in `apply_batch` (existing); the **new durable sync
  consumer** (gap **G3**) that translates a resolved `attempt.submitted` into an `AssessmentEvidence`
  insert via `LearningUnitOfWork`.
- **Data flow + rules (verbatim from `contexts/sync/domain.py`):**
  - **`attempt.submitted` → append-only union.** Dedupe on `evidence_id`; insert new evidence via the
    UoW (atomic with the outbox); the pure engine **re-derives** mastery. This is the authoritative
    resolution for learning — collisions are impossible because facts are immutable and keyed.
  - **`progress.updated` → monotonic max.** Never regress; the server value derived from evidence wins.
  - **`lesson.completed` → idempotent set.** Union; re-completion is a no-op.
  - **`preference.set` → server-order-wins.** LWW by **server receive order** (server version), never
    client clock; client adopts the server value on the next read.
  - **notification read-state** — **client-only** (no server table by design,
    `student_queries.py:152`); resolved device-locally, no server conflict.
- **APIs used:** `apply_batch` resolvers; the new consumer → `LearningUnitOfWork` (`.knowledge` +
  `.events`) atomic commit; evidence idempotent insert (`repository.py:69`).
- **Failure modes:** a resolved attempt that violates the learner's optimistic lock
  (`StudentKnowledgeRow.lock_version`) under concurrent server writes; a preference oscillating between
  devices; a client that ignores the server's resolved value.
- **Recovery strategy:** on `StaleDataError` (optimistic lock, `flag_modified(root,"updated_at")`, CTO
  H6), the consumer retries the derivation on fresh state — safe because evidence insert is idempotent;
  the client **always adopts** the server's resolved `preference`/`progress` on the next read
  (server authoritative); dead-letter only on repeated non-transient failure.
- **Security considerations:** resolution runs server-side under PDP; a client cannot self-promote
  mastery (derived server-side from evidence only); summative remains **mentor-mediated** — sync never
  auto-grades a summative (assessments API marks `mentor_mediated`).
- **Performance considerations:** union/idempotent resolution is O(1) per delta; mastery re-derivation
  reuses the existing engine; optimistic-lock retries are rare and bounded.
- **Acceptance criteria:** offline attempts merge as a union with **exactly-once** evidence and correct
  re-derived mastery; progress never regresses via sync; re-completion and re-send are no-ops; a
  preference conflict resolves to the server value deterministically; **no summative is ever auto-graded
  by sync**; behavior matches `test_sync_engine.py` and extends cleanly to durable evidence.

---

## 6. End-to-end sequence (offline session → sync)

```text
1. Offline: startSession → session_id=uuid7()
2. Offline: teach(objective) from cached LessonView (templated, no LLM)
3. Offline: answer(item) → outcome (Option A: recorded; Option B: engine re-derived locally)
   → write checkpoint (IndexedDB txn)
   → enqueue attempt.submitted{ client_event_id=uuid7(), client_seq++,
                                payload=AssessmentEvidence fields incl evidence_id=uuid7() }
4. …repeat 2–3 for the session…
5. Connectivity returns (probe-confirmed) → Background Sync fires
6. Drain: POST /v1/sync/batch { cursor, deltas ordered by (client_seq, client_event_id) }
7. Server apply_batch → durable consumer inserts AssessmentEvidence idempotently via UoW
   → outbox event emitted atomically → mastery re-derived
8. ItemResult[] returned: applied/duplicate/ignored/conflict + new cursor
9. Client removes applied/duplicate deltas, applies resolutions, persists cursor
10. Client refreshes derived read-model caches (today/reviews/progress) from server
```

Double-count safety holds at every step: retries in 6, replays in 7, and second-device syncs all reduce
to `duplicate` via `client_event_id` + `evidence_id`.

---

## 7. Dependencies + gaps (this spec)

- **G3 (net-new, required for 6.2B):** the **durable sync consumer** — translate `attempt.submitted`
  deltas into `AssessmentEvidence` via `LearningUnitOfWork`, idempotently. Extends the `sync` context +
  adds a learning-side consumer; **does not change the learning domain**.
- **G5 (net-new, recommended):** persist the `client_event_id` idempotency ledger + `cursor` (the
  prototype dedupes in memory only) so detection/resolution survive server restarts. Shard by
  `hash(student_ref)` per doc 09.
- **G4 (recommendation):** durable server sessions (WS15/H1) improve live reconciliation but are **not
  required** — evidence is the system of record.
- **G2 (decision):** Option A (offline-lite, Pilot 1) vs Option B (ported runtime, Pilot 2) — see
  [OFFLINE_ARCHITECTURE.md](OFFLINE_ARCHITECTURE.md) §11.

**Readiness:** the contract and its tests already exist; 6.2B is a **CONDITIONAL GO** pending G3 design
sign-off and the Option A/B decision (full GO/NO-GO in [OFFLINE_ARCHITECTURE.md](OFFLINE_ARCHITECTURE.md)
§14).
