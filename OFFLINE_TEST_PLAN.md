# Offline Subsystem — Test Plan (Design Review)

Status: **Design review only (Phase 6.2). No code, no source changes, no commits.** Consolidates the
**acceptance criteria** of all 14 offline subsystems into a verifiable test plan. Companion to
[OFFLINE_ARCHITECTURE.md](OFFLINE_ARCHITECTURE.md), [OFFLINE_SYNC_SPEC.md](OFFLINE_SYNC_SPEC.md),
[OFFLINE_STORAGE_SPEC.md](OFFLINE_STORAGE_SPEC.md),
[OFFLINE_SECURITY_REVIEW.md](OFFLINE_SECURITY_REVIEW.md).

Aligns to the repo's existing quality gates (ruff, black, mypy --strict, pytest + coverage ≥85,
redocly, markdownlint) and builds on the **already-passing** `services/core-api/tests/test_sync_engine.py`
(idempotent replay, monotonic progress, append-only attempts, idempotent completion, preference
server-order). Offline correctness is a **high-risk** area (WS13: data loss / sync correctness) — the
bar is **no data loss and no double-count, ever**.

---

## 1. Test levels + scope

| Level | Where | Focus |
| --- | --- | --- |
| **Unit (server)** | `services/core-api/tests/` | sync consumer (G3), idempotency ledger (G5), package manifest verify |
| **Unit (client)** | `apps/web` (test runner TBD) | IndexedDB layer, queue ordering, checkpoint resume, conflict handling |
| **Integration** | server + PG | `POST /v1/sync/batch` → durable `AssessmentEvidence` via UoW, idempotent |
| **E2E (browser)** | PWA + SW + IndexedDB | full offline session → reconnect → sync; offline reads; install/verify |
| **Chaos / fault-injection** | E2E harness | interrupted downloads, mid-drain kills, flapping network, quota exhaustion |
| **Device matrix** | real/low-end devices | low storage, weak network, shared-device profiles, Save-Data |
| **Security** | server + client | signature/hash tampering, at-rest, offline-token scope, no-PII, no-LLM-offline |
| **Accessibility** | client | offline status is perceivable; honest degraded-mode UX (WCAG 2.2 AA) |

Existing test to extend, not duplicate: **`test_sync_engine.py`** already proves the conflict/idempotency
rules on the prototype — the new integration tests prove the **same rules against durable evidence**.

---

## 2. Acceptance-criteria → test-case matrix

Each row is a subsystem acceptance criterion (from the design docs) mapped to a concrete test.

### Offline lesson packages (architecture §3)

- **T-PKG-1** publish → signed manifest + per-asset SHA-256 produced. *(unit, server)*
- **T-PKG-2** client installs a pack atomically; a half-install never shows `ready`. *(E2E + chaos)*
- **T-PKG-3** a truncated/altered asset is rejected and refetched. *(security + chaos)*
- **T-PKG-4** an installed pack runs a lesson end-to-end with **network disabled**. *(E2E)*
- **T-PKG-5** pack size is shown before download. *(E2E)*

### Service Worker (architecture §4)

- **T-SW-1** app loads fully offline after first visit. *(E2E)*
- **T-SW-2** shell updates without hard refresh but never mid-session without consent. *(E2E)*
- **T-SW-3** no token / no error response / no non-GET is ever cached. *(security)*
- **T-SW-4** old cache versions purged on `activate`. *(unit client + E2E)*

### Download manager (architecture §5)

- **T-DL-1** a download interrupted at any point **resumes** without re-fetching completed assets. *(chaos)*
- **T-DL-2** a corrupted asset is detected + refetched. *(security + chaos)*
- **T-DL-3** a pack exceeding available storage is **refused** with a clear message. *(device matrix)*
- **T-DL-4** progress is visible + cancellable. *(E2E)*

### Cache versioning (architecture §6)

- **T-CV-1** app upgrade purges old shell caches, still works offline. *(E2E)*
- **T-CV-2** a content update installs as a new `package_id` without disturbing an in-progress session. *(E2E)*
- **T-CV-3** IndexedDB version bump migrates N-1 → N with no data loss. *(unit client)*
- **T-CV-4** no un-synced write is evicted by a version change. *(chaos)*

### Low-storage handling (architecture §7)

- **T-LS-1** with the queue non-empty, no low-storage condition deletes a queued write. *(chaos — critical)*
- **T-LS-2** an over-quota download is refused with actionable UI. *(device matrix)*
- **T-LS-3** persistent storage is requested (`persist()`). *(unit client)*
- **T-LS-4** eviction to free space removes only fully-synced disposable data. *(chaos)*

### Connectivity recovery (architecture §8)

- **T-CR-1** the queue drains within a bounded time of **real** connectivity returning. *(E2E)*
- **T-CR-2** a captive-portal false-positive (`onLine` true, no reachability) does not corrupt state. *(chaos)*
- **T-CR-3** simulated simultaneous reconnects apply jittered backoff (no thundering herd). *(load)*
- **T-CR-4** an expired token triggers a clean refresh, not data loss. *(security + chaos)*

### Telemetry / diagnostics (architecture §9)

- **T-TM-1** telemetry payloads never contain child PII, content, or `student_ref`. *(security)*
- **T-TM-2** diagnostics are suppressed without consent. *(unit + security)*
- **T-TM-3** counters reconcile with observed download/sync events. *(integration)*
- **T-TM-4** the diagnostic ring buffer is bounded. *(unit client)*

### IndexedDB schema (storage §1)

- **T-DB-1** all stores + indexes create at version N. *(unit client)*
- **T-DB-2** N-1 → N upgrade migrates with no data loss. *(unit client)*
- **T-DB-3** drain reads deltas in `client_seq` order. *(unit client)*
- **T-DB-4** resume finds the latest checkpoint by `session_id`. *(unit client)*
- **T-DB-5** a corrupt record is quarantined, not fatal. *(chaos)*
- **T-DB-6** with IndexedDB unavailable, the app runs online-only with a clear banner. *(E2E)*

### Local progress storage (storage §2)

- **T-LP-1** every student read screen renders offline from cache with an "as of" timestamp. *(E2E)*
- **T-LP-2** optimistic progress updates immediately, then is replaced by server-derived values on sync
  with **no visible regression**. *(E2E + integration)*
- **T-LP-3** switching learners on a shared device clears the prior cached view. *(security + E2E)*
- **T-LP-4** caches contain no child PII; cleared on de-enrolment at next connect. *(security)*

### Session checkpointing (sync §2)

- **T-CK-1** killing the app mid-session and reopening **resumes at the exact last completed
  interaction** with no lost/duplicated attempts. *(chaos — critical)*
- **T-CK-2** a fully-offline session syncs each attempt **exactly once**. *(integration — critical)*
- **T-CK-3** resuming the same session on a second device does **not** double-count. *(integration — critical)*

### Background synchronization (sync §3)

- **T-BS-1** replaying a batch (same `client_event_id`s) → all `duplicate`, no state change (mirrors
  `test_sync_engine.py`, now against durable evidence). *(integration — critical)*
- **T-BS-2** a drain interrupted mid-batch resumes with no loss or double-apply. *(chaos — critical)*
- **T-BS-3** a poison delta is dead-lettered without stalling the rest. *(chaos)*
- **T-BS-4** the queue reaches empty after connectivity returns. *(E2E)*
- **T-BS-5** one batch call per drain cycle (not per delta). *(integration)*

### Conflict detection (sync §4)

- **T-CD-1** a duplicate `client_event_id` → `duplicate` every time. *(integration)*
- **T-CD-2** a regressed `progress.updated` → `ignored`, not applied. *(integration)*
- **T-CD-3** detection identical regardless of device clock (Lamport `client_seq` only). *(integration)*
- **T-CD-4** after a simulated server restart, previously-seen deltas are still detected (needs G5). *(integration)*

### Conflict resolution (sync §5)

- **T-CFR-1** offline attempts merge as a **union with exactly-once** evidence + correct re-derived
  mastery. *(integration — critical)*
- **T-CFR-2** progress never regresses via sync (monotonic max). *(integration)*
- **T-CFR-3** re-completion and re-send are no-ops. *(integration)*
- **T-CFR-4** a preference conflict resolves to the **server** value deterministically. *(integration)*
- **T-CFR-5** **no summative is ever auto-graded by sync** (stays mentor-mediated). *(integration — critical)*

### Package signing / integrity (security §2)

- **T-SIG-1** a pack with any altered byte fails verification and is not installed. *(security — critical)*
- **T-SIG-2** an unsigned or unknown-key pack is rejected. *(security)*
- **T-SIG-3** a downgrade attempt is refused. *(security)*
- **T-SIG-4** key rotation installs cleanly via a pinned key set. *(security)*
- **T-SIG-5** no unverified asset is ever rendered to a child. *(security — critical)*

### Offline auth (security §4) — 6.2C, governance-gated

- **T-AU-1** the offline token cannot read another child's data or mutate grades. *(security — critical)*
- **T-AU-2** token expiry refreshes without losing queued writes. *(chaos)*
- **T-AU-3** server-side revocation takes effect on next sync. *(security)*
- **T-AU-4** no token is cached by the SW or logged. *(security)*

### Child safety offline (security §6) — non-negotiable

- **T-SAFE-1** **no LLM path exists offline** (static + runtime assertion). *(security — critical)*
- **T-SAFE-2** the crisis affordance is reachable with **no network**. *(E2E — critical)*
- **T-SAFE-3** a triggered safety flag queues at **highest priority** and syncs **first** on reconnect. *(integration — critical)*
- **T-SAFE-4** unsupervised at-home offline is **disabled** until the offline-safety design + M-Safe land. *(config/gate check)*

---

## 3. Chaos / fault-injection scenarios (the high-risk core)

Because WS13 risk is data loss / sync correctness, these are mandatory before any offline GO beyond
Pilot 0:

- **CX-1 Kill mid-interaction:** hard-kill the tab between answer and checkpoint commit → reopen → no
  lost/duplicated attempt (atomic IndexedDB txn). *(T-CK-1)*
- **CX-2 Kill mid-drain:** kill during a `sync.batch` round-trip → reopen/reconnect → exactly-once
  evidence (T-BS-2, T-CK-2).
- **CX-3 Flapping network:** rapidly toggle offline/online during a session + drain → convergent, no
  duplicates (T-CR-1/2).
- **CX-4 Quota exhaustion:** fill storage with the queue non-empty → no queued write evicted; download
  refused (T-LS-1/2).
- **CX-5 Two-device replay:** same session/attempts synced from two devices → deduped, single evidence
  set (T-CK-3, T-CFR-1).
- **CX-6 Tampered pack:** flip a byte in an asset / manifest → rejected, not installed, not rendered
  (T-SIG-1/5).
- **CX-7 Server restart mid-sync:** restart the API between batches → idempotency ledger still detects
  seen deltas (T-CD-4, needs G5).
- **CX-8 Clock skew:** set device clock far forward/back → ordering + resolution unaffected (T-CD-3).

---

## 4. Device + network matrix

| Dimension | Values to cover |
| --- | --- |
| Device tier | low-end Android (representative of pilot devices), mid, desktop |
| Storage | near-full, moderate, ample; persistent + non-persistent origin |
| Network | offline, 2G/3G, flaky/intermittent, Save-Data on, captive portal |
| Sharing | single profile, **shared device with profile switch** |
| Browser | Chromium (primary, Background Sync), a non-Background-Sync fallback engine |
| Locale | Urdu (RTL) primary, English support |

---

## 5. Definition of Done (offline, per phase)

- **6.2A (offline-lite):** T-SW-*, T-PKG-1..5, T-DL-*, T-CV-*, T-LS-*, T-CR-*, T-DB-*, T-LP-* green;
  offline reads + install proven on the device matrix; **no data-loss** chaos (CX-4) green.
- **6.2B (offline sessions + sync):** all **critical** sync/checkpoint/resolution tests green
  (T-CK-*, T-BS-1/2, T-CD-*, T-CFR-1/5), CX-1/2/3/5/7/8 green; integration against **durable evidence**
  matches `test_sync_engine.py` semantics; **exactly-once, no double-count** proven.
- **6.2C (hardening/security/safety):** T-SIG-*, T-AU-*, T-SAFE-*, T-TM-* green; at-rest encryption
  verified; **T-SAFE-1/2/3 (no-LLM-offline, crisis reachable, flag priority) are release-blocking**.

---

## 6. Exit gate for offline in Pilot 1

**Offline-lite (6.2A) with all data-loss chaos scenarios green** is the minimum for Pilot 1, which is
**Wi-Fi-supervised** (compensating control for the offline-safety limitation, security review §6).
Full offline sessions (6.2B) and unsupervised at-home offline (needs 6.2C + M-Safe) are **not** required
for Pilot 1 and are **gated** for Pilot 2. This matches the phased GO/NO-GO in
[OFFLINE_ARCHITECTURE.md](OFFLINE_ARCHITECTURE.md) §14: **GO to build 6.2A now; conditional/NO-GO for
6.2B/6.2C pending the named dependencies.**
