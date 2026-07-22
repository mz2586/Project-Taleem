# Phase 6.2B — Offline Synchronization Engine Report

Status: **Complete.** Implements Phase 6.2B of the approved offline architecture — the durable sync
engine that drains offline attempts into server-recorded evidence. Builds on 6.2A
([PHASE_6_2A_REPORT.md](PHASE_6_2A_REPORT.md)); design in [OFFLINE_SYNC_SPEC.md](OFFLINE_SYNC_SPEC.md).
No architecture redesign. Local commit + `phase-6.2B` tag.

---

## 1. Scope delivered (6.2B checklist)

| Deliverable | Where |
| --- | --- |
| ✓ Background synchronization | `apps/web/lib/offline/backgroundSync.ts` (Background Sync tag + `online`/visibility fallback); `sw.js` `sync` event nudges clients |
| ✓ Sync queue | `apps/web/lib/offline/syncQueue.ts` — durable `evidence_queue` IndexedDB store, ordered by `(clientSeq, clientEventId)` |
| ✓ Idempotent uploads | client `clientEventId` + `evidence_id`; server dedupes on the **evidence table** (durable) |
| ✓ Conflict detection | server `DurableSyncCoordinator` routes by delta type; per-item `ItemResult` status |
| ✓ Conflict resolution | attempts = append-only union (evidence); progress = monotonic-max; completion = idempotent set; preference = server-order (unchanged engine) |
| ✓ Durable retry strategy | `syncClient.ts` keep-on-failure + attempts counter + dead-letter past cap; `backoffMs` full-jitter |
| ✓ Session reconciliation | `apps/web/lib/offline/reconcile.ts` — replays local progress into the queue idempotently (stable `evidence_id`) |
| ✓ Automatic resume after reconnect | `startAutoDrain` (online/visibility/SW message) → `SyncClient.drain` |
| ✓ Sync diagnostics | `apps/web/lib/offline/diagnostics.ts` — **local** counters (no upload) |
| ✓ Sync status UI integration | `SyncStatusBadge` + `useSyncStatus` hook wired into `AppShell` (live pending count) |

### Not implemented (deferred, per instruction)

Offline authentication · device-bound credentials · governance-gated identity · child-safety
escalation workflows · consent-gated telemetry upload · production deployment changes.

---

## 2. Backend — durable sync consumer (gap G3 closed)

The prototype `/v1/sync/batch` was in-memory + synthetic. 6.2B makes **`attempt.submitted` durable**
while reusing every existing primitive (no domain redesign, no new child-data table):

- **`contexts/learning/application/sync_consumer.py` — `SyncEvidenceConsumer`.** Session-less grading:
  loads the published lesson's `ItemView`, scores it with the existing pure `evaluate` scorer, applies
  it through the existing `StudentKnowledge.apply_attempt` + `LearningUnitOfWork` (evidence + outbox,
  atomic). **Idempotency reuses the existing model** — the aggregate hydrates every recorded
  `evidence_id`, so a replay is detected and skipped **before** any mastery mutation. This is durable:
  a replay after a **server restart** is still a `DUPLICATE` because the evidence table is the ledger.
- **`contexts/sync/service.py` — `DurableSyncCoordinator`.** Orders the batch, routes
  `attempt.submitted` to the durable sink and every other type to the existing `SyncEngine` (monotonic
  progress / idempotent completion / server-order preference). Returns the same `ItemResult` contract +
  server-incremented cursor (no client wall-clock). `SyncEngine.apply(delta)` was added as the public
  single-delta entry point.
- **`main.py`** wires the consumer + coordinator into `POST /v1/sync/batch` (replacing the per-request
  in-memory engine). No auth/PDP/governance change — the endpoint keeps its existing `(system, write,
  sync.batch)` policy.

**Non-negotiable enforced:** a **summative** item is never auto-graded by sync (only practice /
homework / formative are gradable; summative/unknown → `ignored`).

Reused exactly as required: **Sync bounded context · `POST /v1/sync/batch` · `SyncDelta` · `DeltaType`
· `client_event_id` · `client_seq` · `AssessmentEvidence` · `LearningUnitOfWork` · existing idempotency
model.**

---

## 3. Frontend — sync engine

`apps/web/lib/offline/` additions (all behind the `KVStore` interface, testable with `MemoryStore` /
`fake-indexeddb`):

| Module | Responsibility |
| --- | --- |
| `syncQueue.ts` | Durable outbound queue: monotonic `clientSeq`, enqueue (+`enqueueAttempt`), ordered `pending`, `remove`/`markFailed`/`deadLetter`, counts |
| `syncClient.ts` | Drain worker: deterministic order, idempotent status handling (applied/duplicate/ignored → removed; conflict → dead-lettered; network fail → kept + retried), cursor persistence, re-entrancy guard, `backoffMs` full-jitter |
| `backgroundSync.ts` | Background Sync registration + `startAutoDrain` (online/visibility/SW-message) |
| `reconcile.ts` | `reconcileAndResume` — replays local progress into the queue idempotently, then drains |
| `diagnostics.ts` | Local sync counters (no upload) |

Wiring: `kv.ts` bumped to **DB v2** (adds the `evidence_queue` store, created on upgrade);
`index.ts` composes an `OfflineClient.sync` (queue/client/diagnostics/drain/reconcile/auto-drain);
`lib/student/api.ts` adds `syncApi.batch`; `lib/student/offlineClient.ts` is the browser singleton;
`useSyncStatus` + `SyncStatusBadge` surface live status in `AppShell`; `sw.js` gains a `sync` handler.

---

## 4. Correctness argument (no data loss, no double-count)

- **Every write is a client-keyed immutable fact.** `attempt.submitted` carries a client `evidence_id`
  (uuid7). The server records evidence append-only and skips a known `evidence_id`. So re-sends,
  batch-replays, reconnect-retries, reconcile re-queues, and post-restart replays all reduce to
  `DUPLICATE`.
- **Derived state is re-derived server-side** (mastery from evidence); the client never holds
  authoritative learning state.
- **The queue is the source of truth on the device** and is only removed on a settled `ItemResult`;
  a network failure keeps it for retry (bounded, then dead-lettered so it never blocks the queue).

---

## 5. Testing

| Suite | Count | Covers |
| --- | --- | --- |
| Backend `tests/test_sync_evidence.py` | 1 SQLite integration (+1 PG-gated) | attempt→durable evidence + mastery; **duplicate upload** (same clientEventId+evidence_id) no double-count; **crash recovery** (new clientEventId, same evidence_id → duplicate); append-only union of distinct attempts; wrong-answer misconception; non-attempt conflict policy (progress monotonic, preference); **summative never auto-graded** |
| Frontend `apps/web/lib/offline/__tests__/` | +21 (52 total) | queue durability/ordering/dead-letter (`syncQueue`); drain idempotency + conflict dead-letter + **retry on offline then reconnect** + diagnostics + backoff (`syncClient`); **auto-drain on reconnect** incl. captive-portal guard (`backgroundSync`); **session reconciliation** idempotent (`reconcile`); **crash recovery** + **long offline session (120 attempts)** + partial-drain-then-reopen over IndexedDB (`syncCrashRecovery`) |

Requested test categories — all present: sync integration, conflict resolution, duplicate upload,
retry, reconnect, crash recovery, long offline session. The pre-existing prototype test
(`test_integration.py::TestSyncEndpoint`) was updated to use the still-in-memory delta types, since
`attempt.submitted` now routes to the durable consumer (covered by `test_sync_evidence.py`).

---

## 6. Quality gate summary

| Gate | Result |
| --- | --- |
| Ruff | ✅ All checks passed |
| Black (`--check`) | ✅ 112 files unchanged |
| mypy `--strict` | ✅ no issues in 91 source files |
| pytest | ✅ **147 passed, 6 skipped** (6 = PostgreSQL-gated) |
| OpenAPI (redocly 1.25.11) | ✅ all contracts valid (sync contract updated) |
| Frontend typecheck (`tsc --noEmit`) | ✅ clean |
| Frontend tests (`vitest run`) | ✅ **52 passed** (14 files) |
| Frontend build (`next build`) | ✅ compiled + 12 static pages |

---

## 7. Follow-ups (not in 6.2B)

6.2C: Ed25519 package signing, at-rest encryption of C2 IndexedDB stores, device-bound offline auth
token (governance-gated), consent-gated telemetry upload, offline safety crisis-flag routing. A
durable server-side `client_event_id` cursor ledger (G5) remains optional — attempt idempotency is
already durable via the evidence table.
