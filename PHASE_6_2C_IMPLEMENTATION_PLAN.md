# Phase 6.2C — Implementation Plan (Offline Hardening, Security, Safety, Telemetry)

Status: **Plan only. No code, no commits, no redesign.** This document plans Phase 6.2C — the offline
subsystem's hardening phase — as scoped in [OFFLINE_ARCHITECTURE.md](OFFLINE_ARCHITECTURE.md) §13 and
gated in §14. It reviews the existing architecture, security, child-safety, governance, and offline
design before proposing any work, and cites the exact components to reuse and the gaps/gates to honor.

**6.2C scope anchor (already deferred there):** end-to-end Ed25519 signing/integrity; at-rest
encryption of C2 data in IndexedDB; device-bound offline auth token (governance-gated); telemetry
upload (consent-gated); offline safety crisis-flag routing (M-Safe-gated); low-storage eviction polish;
device-matrix + chaos test hardening. 6.2B explicitly did **not** implement offline auth, device-bound
credentials, governance-gated identity, child-safety escalation workflows, or consent-gated telemetry
(see [PHASE_6_2B_REPORT.md](PHASE_6_2B_REPORT.md) §7).

---

## 0. Documents + code reviewed

- Offline design: [OFFLINE_ARCHITECTURE.md](OFFLINE_ARCHITECTURE.md) (§3, §9 gaps G1–G8, §11, §13, §14),
  [OFFLINE_SECURITY_REVIEW.md](OFFLINE_SECURITY_REVIEW.md) (§2 signing, §3 at-rest, §4 offline auth,
  §5 residency/retention, §6 child-safety, §8 SG-1…SG-7), [OFFLINE_STORAGE_SPEC.md](OFFLINE_STORAGE_SPEC.md)
  (§0 PII classes, §3 eviction), [OFFLINE_SYNC_SPEC.md](OFFLINE_SYNC_SPEC.md) (§7 G5),
  [OFFLINE_TEST_PLAN.md](OFFLINE_TEST_PLAN.md) (T-SIG/T-AU/T-SAFE/T-TM, chaos CX-1…8, device matrix).
- Security/privacy/safety: `docs/03-security-privacy/{11-authentication-strategy,13-security-model,
  14-privacy-model,15-child-safety-framework,52-safeguarding-crisis-protocol,57-data-retention-schedule}.md`;
  `docs/02-architecture/33-offline-architecture.md §8`.
- Governance: [MASTER_EXECUTION_PLAN.md](MASTER_EXECUTION_PLAN.md) WS1/WS2/WS14, [PILOT_PLAN.md](PILOT_PLAN.md)
  Pilot 0/1, `FOUNDER_DECISIONS.md` FD-14 (KMS) / FD-02 (residency host).
- Code reuse points: `contexts/learning/domain/offline_package.py`, `application/offline_service.py`,
  `adapters/offline_api.py`, `contexts/sync/{domain.py,service.py}`, `auth/{jwt_verifier,pdp,dependencies}.py`,
  and `apps/web/lib/offline/{kv,sha256,packages,syncQueue,diagnostics,types}.ts`, `public/sw.js`,
  `lib/student/config.ts`, `vitest.config.ts`.

---

## 1. Immovable constraints (every 6.2C item must honor)

- **No new child-data tables**; **pseudonymous `student_ref` only, no child PII** in stores, tokens,
  telemetry, or logs (OFFLINE_ARCHITECTURE §0; storage spec §0).
- **Deny-by-default PDP re-checks on sync**; role from the verified token, never the body.
- **No generative AI offline, ever** (audit AR-C-06) — any offline safety text is deterministic,
  pre-authored, served outside the model path (crisis protocol §3).
- **Queued writes + checkpoints are never evicted before sync** (storage spec §3).
- **Do not redesign** the sync contract, evidence model, package builder, or auth seam — extend them.

---

## 2. Gate status — buildable now vs blocked

| Item | State | Gate |
| --- | --- | --- |
| Ed25519 package signing (SG-1 / G1) | **Buildable now** | none (KMS key ideally per FD-14, but a build-time key can bootstrap) |
| At-rest AES-GCM for C2 stores (SG-2) | **Mechanism buildable now** | production keys → **FD-14** |
| Low-storage eviction polish | **Buildable now** | none |
| Chaos / fault-injection tests | **Buildable now** | none |
| Device-matrix automation | **Buildable now** | none (new E2E track) |
| De-enrolment / consent-withdrawal purge (SG-5) | **Mechanism buildable now** | trigger → consent model (**M-Gov**/WS8) |
| Durable idempotency ledger (G5 / SG-7) | **Buildable now** | none (optional) |
| Device-bound offline auth token (G6 / SG-3) | **Blocked** | **M-Gov** + **FD-14** |
| Automated crisis-flag routing (safety.flag sink) | **Blocked** | **M-Safe** (SLAs + reporting channels DECISION REQUIRED) |
| Consent-gated telemetry upload | **Blocked** | **consent** + residency pin (**FD-02**) |

---

## A. Required for pilot launch

Pilot 1 is **on-site, supervised, on provided (MDM-managed) devices, on guaranteed Wi-Fi**, with a
safeguarding lead physically present (PILOT_PLAN §Pilot 1). That supervision is the compensating control
for offline safety (security review §6). The A-items are what a real child pilot still needs from 6.2C.

### A1 — Ed25519 package signing + client verification (SG-1 / G1)

- **Purpose:** guarantee the exact, approved content leaves the build pipeline and reaches the child
  unmodified — a **child-safety** control (a tampered pack could put unapproved content before a child),
  not merely data integrity. Completes the design's §3 acceptance ("a tampered or truncated asset is
  rejected").
- **Existing components to reuse:** backend `offline_package.py` `build_manifest()` (attach a
  `signature` and `signing_key_id` after `content_hash`; `canonical_json` is the deterministic serializer);
  `OfflinePackageManifest.to_dict()`; `offline_service.py` / `offline_api.py` emit the signed manifest.
  Frontend `sha256.ts` `verifyContent` (add a sibling `verifySignature` via `crypto.subtle.verify`);
  `packages.ts` `DownloadManager.download()` integrity gate (verify signature **before** the existing
  SHA-256 check); the existing `IntegrityError`. `types.ts` `PackageManifest`/`StoredPackage` gain
  `signature`/`signing_key_id`/`signature_ok` in lockstep.
- **Dependencies:** 6.2A package pipeline. Signing key: ideally KMS per **FD-14**, but a build-time
  Ed25519 key (public key pinned in the app bundle) can bootstrap the pilot without waiting on FD-14.
- **Risks:** cross-build canonicalization drift (already a noted 6.2A risk — mitigated by the shared
  `canonical_json`); key-rotation handling; pinning the wrong key blocks all installs.
- **Privacy implications:** none new — packages are C0 curriculum, no child data. Signing adds no PII.
- **Child-safety implications:** strong positive — enforces "approved content only reaches a child"; no
  unverified asset is ever rendered.
- **Data flow:** build → compute per-asset SHA-256 → sign the canonical manifest (private key) →
  publish manifest + assets → client fetches manifest → **verify signature against the pinned key for
  `signing_key_id`** → download assets → verify each SHA-256 → atomic install; any failure → discard,
  do not install, honest error.
- **Failure modes:** invalid signature (tampered/forged); unknown/revoked `signing_key_id`; downgrade to
  an older/unsigned pack; asset hash mismatch. Each → reject + refetch (bounded).
- **Acceptance criteria (OFFLINE_TEST_PLAN T-SIG-1…5):** altered byte fails + not installed; unsigned/
  unknown-key rejected; downgrade refused; key rotation installs via a pinned key set; **no unverified
  asset ever rendered to a child** (T-SIG-5, critical).
- **Estimated effort:** **S–M** (backend signer + manifest field: S; client verify + types: S; key
  pinning/rotation + tests: M).
- **Note (fallback):** if signing slips, 6.2A's SHA-256 content-hash verification on MDM-managed devices
  with an operator-controlled in-region content host is an acceptable interim posture — so A1 is
  "required with a documented fallback," not a hard blocker for a supervised pilot.

### A2 — Chaos / fault-injection test hardening + run on the actual pilot device

- **Purpose:** prove the WS13 "no data loss / no double-count" guarantee under real failure, and
  validate on the exact Pilot-1 device model as part of Pilot 0 QA.
- **Existing components to reuse:** the vitest + `fake-indexeddb` harness (`vitest.config.ts`, 14 files /
  52 tests); the `KVStore`/`MemoryStore` seam; the 6.2B crash-recovery + long-session tests as the
  pattern; backend PG-gated pattern (`CS_DATABASE_URL`).
- **Dependencies:** 6.2A/6.2B. A physical Pilot-1 device for the Pilot-0 manual pass.
- **Risks:** simulated chaos not matching real device behavior (mitigated by the Pilot-0 device run);
  flaky async tests.
- **Privacy implications:** tests use synthetic `student_ref` only.
- **Child-safety implications:** indirect — hardens the correctness a supervised pilot depends on.
- **Data flow:** n/a (test harness).
- **Failure modes covered (OFFLINE_TEST_PLAN §3):** CX-1 kill mid-interaction, CX-2 kill mid-drain,
  CX-3 flapping network, CX-4 quota exhaustion, CX-5 two-device replay, CX-7 server restart mid-sync
  (needs G5 for the non-attempt case — see C1), CX-8 clock skew.
- **Acceptance criteria:** all automatable data-loss chaos scenarios green; the suite passes on the
  actual Pilot-1 device model (Pilot 0 exit).
- **Estimated effort:** **S–M** (extend the existing suite; the device run is manual QA).

### A3 — De-enrolment / consent-withdrawal cache purge (SG-5)

- **Purpose:** honor right-to-erasure / consent withdrawal down to device caches — a data-protection
  obligation that must hold during the pilot (retention schedule §: "erasure must reach device caches;
  caches invalidate on next sync").
- **Existing components to reuse:** a small server→client **purge instruction** (no new child-data
  table); frontend `kv.ts` `KVStore.clear(store)` + the existing `ReadCache.clearStudent` /
  clear-on-switch pattern; the sync response as the delivery channel.
- **Dependencies:** the consent/enrolment model (**M-Gov** / WS1 + WS8) supplies the trigger; the
  mechanism itself is gate-free.
- **Risks:** a device that never reconnects retains caches (mitigated by MDM wipe on managed devices +
  no-PII + short retention); racing a purge with an in-flight drain.
- **Privacy implications:** strongly positive — completes the erasure path to the device; purge clears
  all C2 stores (`read_cache`, `progress_local`, `checkpoints`, and drained `evidence_queue`).
- **Child-safety implications:** neutral/positive (respects guardian withdrawal).
- **Data flow:** guardian/admin withdraws consent (server) → server marks the learner purge-pending →
  on the learner's next authenticated sync, the response carries a purge instruction → client clears all
  C2 stores for that `student_ref` and stops queueing → acknowledges.
- **Failure modes:** offline device (purge deferred to next connect — documented); partial clear
  (idempotent — re-issued until acknowledged).
- **Acceptance criteria:** a withdrawn learner's C2 offline stores are cleared at next connect; no child
  data remains; unsynced-but-withdrawn data handling is per policy (see Decision D-5).
- **Estimated effort:** **S** (mechanism) — but do not ship until the consent model defines the trigger.

### A4 — Offline crisis affordance (static, packaged) — the reachable part

- **Purpose:** ensure a child in distress **offline** can always reach help — the always-available
  affordance showing deterministic, pre-authored self-help + local crisis information and a clear
  "a person will be reached" message. Meets the "reachable with no network" bar (T-SAFE-2).
- **Existing components to reuse:** the offline package pipeline (ship the pre-authored crisis template
  as packaged C0 content — never generated); the student UI shell; the "no generative AI offline"
  invariant. **Reuses content packaging, not the sync path.**
- **Dependencies:** the **deterministic crisis template** must be clinician + legal reviewed (crisis
  protocol §3) — a content/policy input, not the automated routing (that is B2 / M-Safe).
- **Risks:** presenting stale/wrong crisis info; over-promising immediate remote help while offline
  (mitigated by honest wording + Pilot-1 on-site supervision).
- **Privacy implications:** the affordance itself collects nothing; it must not ask a child to enter
  personal data.
- **Child-safety implications:** core — a distressed offline child is not left without a route; in
  Pilot 1 that route is "raise your hand to the present mentor/safeguarding lead," reinforced by the
  packaged message. **This is the affordance only**; the automated remote flag is B2.
- **Data flow:** child triggers the affordance offline → app shows packaged, pre-authored help + local
  crisis contacts + "tell your mentor now" → (when B2 lands) also queues a priority safety flag.
- **Failure modes:** template missing from the pack (fail loud, show a hard-coded minimal fallback);
  affordance not reachable from a screen (a11y/route audit).
- **Acceptance criteria (T-SAFE-1/2):** no LLM path exists offline; the crisis affordance is reachable
  with **no network** from the child surfaces; wording is honest about the supervised-pilot route.
- **Estimated effort:** **S** for the affordance UI + packaged template wiring (template authoring +
  clinician/legal review is a separate content/policy track).

### A5 — Device-bound offline auth token (G6 / SG-3) — **REQUIRED for Pilot 1, BLOCKED by M-Gov + FD-14**

- **Purpose:** an attributable, revocable, device-bound, time-boxed offline session so a child's offline
  work is authenticated (auth strategy Principle 6: "offline must still be authenticated"). Part of
  child-safe auth (WS3) — Pilot 1 uses real child sessions, not the Pilot-0 dev stub.
- **Existing components to reuse:** `Claims.device_id` (already present in `jwt_verifier.py`); the
  `auth` IndexedDB store shape (`{ciphertext, iv, expires_at}`, storage spec §1 — not yet in `STORES`);
  the HS256→JWKS/KMS seam (FD-14); the sync path's re-validation on reconnect.
- **Dependencies (HARD GATES):** **M-Gov** (DPIA, consent, child-identity model, residency); **FD-14**
  (asymmetric keys / KMS for signing + at-rest); a **capability-scoping** mechanism in the PDP (none
  exists today — `pdp.py` authorizes by role only) so the token grants **only** cached-lesson +
  queued-submission scope; a **revocation registry** (auth strategy: Redis) so a revoked session drops
  on next sync.
- **Risks:** stolen bound device (mitigated by device binding + short TTL + revocation); building ahead
  of the governance decisions and having to rework identity.
- **Privacy implications:** token carries **no child PII** (only `student_ref` / `device_id`); encrypted
  at rest on device; short TTL (auth strategy: 24–72h configurable per cohort — Decision D-3).
- **Child-safety implications:** enables attributable, revocable child sessions — a safeguarding
  prerequisite; must not read cross-child data or mutate grades (IDOR + capability scope).
- **Data flow:** online sign-in (child-safe auth) issues a device-bound offline token → stored encrypted
  in the `auth` store → offline reads/queues use it → on reconnect it is re-validated + refreshed;
  revocation drops it on next sync.
- **Failure modes:** token expiry mid-offline (grace window + queue kept, refresh on reconnect — never
  lose queued writes); revoked token (server rejects on sync).
- **Acceptance criteria (T-AU-1…4):** cannot read another child's data or mutate grades; expiry refreshes
  without losing queued writes; server-side revocation takes effect on next sync; no token cached by the
  SW or logged.
- **Estimated effort:** **L** (identity, PDP capability scoping, revocation registry, device binding,
  and the encrypted store) — **cannot start until M-Gov + FD-14 land.**

---

## B. Recommended before public launch

For at-home / unmanaged devices and larger, less-supervised scale (Pilot 2+), these become necessary.

### B1 — At-rest AES-GCM encryption of C2 IndexedDB stores (SG-2)

- **Purpose:** protect child learning data (C2) at rest on a device that is **not** a secure enclave —
  primarily for at-home/unmanaged devices where OS/MDM full-disk encryption cannot be assumed.
- **Existing components to reuse:** wrap the `KVStore` interface (`kv.ts`) with an AES-GCM decorator that
  encrypts on `put` / decrypts on `get` for exactly the four C2 stores (`read_cache`, `progress_local`,
  `checkpoints`, `evidence_queue`), leaving C0/C1 stores plaintext — **every consumer unchanged**
  (`packages.ts`, `syncQueue.ts`, `checkpoint.ts`, `progress.ts`, `readCache.ts`, `diagnostics.ts`).
  Web Crypto AES-GCM; per-profile non-extractable `CryptoKey`.
- **Dependencies:** **FD-14** for production key management (per-data-class keys, offline-cache keys —
  currently undecided); per-profile key derivation strategy (Decision D-2).
- **Risks (honest limitation, security review §3):** a browser is not a secure enclave — a fully
  compromised device can reach IndexedDB + in-memory keys. Mitigated, not eliminated, by: no PII stored,
  short retention + prompt sync, per-profile namespacing + clear-on-switch, and OS/device security.
  **Recommendation: carry device at-rest confidentiality as a residual risk in the register and prefer
  managed devices** (which Pilot 1 already does).
- **Privacy implications:** raises the bar for C2 confidentiality on lost/shared devices; no change to
  what is stored (still `student_ref`-only, no PII).
- **Child-safety implications:** reduces exposure of a child's learning record on a shared home device.
- **Data flow:** `put(store, key, value)` → if C2, AES-GCM encrypt → store `{ciphertext, iv}`; `get` →
  decrypt. Keys per profile; cleared on learner switch.
- **Failure modes:** key unavailable/rotated (data unreadable — treat as cache-miss + re-fetch for
  disposable stores; for the durable queue, key loss = a real risk → Decision D-2 on key durability);
  corrupt ciphertext (quarantine).
- **Acceptance criteria (OFFLINE_TEST_PLAN DoD 6.2C):** C2 stores are encrypted; no C3 PII present; keys
  per-profile + cleared on switch; residual device-compromise risk documented in the register.
- **Estimated effort:** **M** (decorator + key lifecycle + tests) — the mechanism can prototype now;
  production keys wait on FD-14.

### B2 — Automated offline safety-flag routing (`safety.flag`) — **BLOCKED by M-Safe**

- **Purpose:** when a child triggers the offline crisis affordance (A4), queue a **highest-priority**
  safety flag that syncs **first** on reconnect and routes to a human within SLA — required for
  unsupervised at-home offline (Pilot 2+); Pilot 1 relies on on-site supervision instead.
- **Existing components to reuse:** the durable `SyncQueue` + the 6.2B durable-consumer routing pattern
  (`DurableSyncCoordinator` + a new sink, exactly as `SyncEvidenceConsumer` was added). **New, gated:**
  a `safety.flag` value on the closed `DeltaType` enum (`contexts/sync/domain.py`) + a server **safety
  sink**; client **priority ordering** in `syncQueue.pending()` (currently strict `(clientSeq,
  clientEventId)` FIFO — add a priority field or head-of-queue insert) + a high-priority drain.
- **Dependencies (HARD GATE — M-Safe):** crisis **SLA values** (T0 ≤5 min … T3 ≤24 h) and
  **mandatory-reporting channels + external-referral authorizer** are **DECISION REQUIRED** (crisis
  protocol §2/§5 — clinical + legal sign-off). Also: where the flag persists — safeguarding is a **C4**
  record, but the constraint is **no new child-data tables** → Decision D-6 (reconcile C4 safeguarding
  persistence with the no-new-table rule).
- **Risks:** a missed/mis-routed flag is a safeguarding failure; false negatives; building routing before
  the reporting policy exists.
- **Privacy implications:** safeguarding data is the **most sensitive (C4)** — strictest handling, no
  logging, least-privilege; the offline flag must carry only what safeguarding needs (no free-text that
  could leak PII).
- **Child-safety implications:** the core of offline safety at scale — this is the M-Safe substance; must
  never be silently dropped (contrast the current `CONFLICT`-for-unknown-type behavior, which would
  dead-letter an unrecognized safety delta — so a real type + sink is mandatory).
- **Data flow:** offline trigger → enqueue `safety.flag` at highest priority → on reconnect drain sends
  it **first** → server safety sink records it (C4) + routes to a human within SLA → acknowledgement.
- **Failure modes:** device never reconnects (Pilot-1 on-site supervision covers this; at-home requires
  the fuller SG-6 design in C3); flag lost in the queue (priority + never-evict + never-conflict-drop).
- **Acceptance criteria (T-SAFE-3, release-blocking for at-home):** a triggered flag queues at highest
  priority and syncs **first** on reconnect; routes to a human within SLA; T-SAFE-4: unsupervised at-home
  offline stays **disabled** until this + M-Safe land.
- **Estimated effort:** **M–L** engineering **after** M-Safe policy decisions (which are the long pole).

### B3 — Consent-gated telemetry / diagnostics upload — **BLOCKED by consent + residency**

- **Purpose:** measure offline health at scale (download/sync/integrity/storage counters) to run the
  service — without any child PII.
- **Existing components to reuse:** the 6.2B local `SyncDiagnosticsStore` (counters already C1-only, no
  `student_ref`); add a consent gate + a `device_id`-keyed payload builder + an in-region sink.
- **Dependencies:** **consent** (privacy model) + **residency pin** (FD-02) for the sink; a consent
  signal surfaced to the client.
- **Risks:** accidentally including content or `student_ref`; egress out of region; upload without
  consent.
- **Privacy implications:** **C1/C0 only, no C2/C3, no `student_ref`** (use `device_id`); in-region
  egress; suppressed without consent (drop silently).
- **Child-safety implications:** none directly (no child content); must not become a covert data channel.
- **Data flow:** local counters accrue → on sync, **if consent granted**, aggregated counters (device_id
  only) go to the in-region diagnostics sink; else nothing leaves the device.
- **Failure modes:** consent absent/revoked (no upload); sink unreachable (retain locally, bounded).
- **Acceptance criteria (T-TM-1…4):** telemetry never contains child PII/content/`student_ref`;
  suppressed without consent; counters reconcile with observed events; the local ring buffer is bounded.
- **Estimated effort:** **S–M** engineering — but blocked on the consent model + residency decision.

### B4 — Low-storage eviction polish

- **Purpose:** operate on low-end/near-full devices without ever losing learner writes.
- **Existing components to reuse:** `packages.ts` `DownloadManager.remove()` + `last_used_at`;
  StorageManager `estimate`/`persist` (already used); the storage-spec eviction order.
- **Dependencies:** none.
- **Risks:** evicting something still needed; **must never** evict `evidence_queue`/`checkpoints`/
  dead-letters before sync (already invariant).
- **Privacy implications:** eviction respects per-profile namespacing (no cross-profile leak on cleanup).
- **Child-safety implications:** neutral.
- **Data flow:** pre-download `estimate()` → if insufficient, LRU-evict **disposable** data only
  (app-shell → content bytes → `read_cache`/`progress_local`) → if still insufficient, refuse with clear
  UI.
- **Failure modes:** browser evicts under pressure (request `persist()`; re-fetch disposable on reconnect).
- **Acceptance criteria (T-LS-1…4):** no low-storage condition deletes a queued write; over-quota
  download refused with actionable UI; persistent storage requested; eviction removes only fully-synced
  disposable data.
- **Estimated effort:** **S**.

### B5 — Real-device matrix automation

- **Purpose:** validate on the real matrix (low-end Android/mid/desktop × storage/network/profile/browser
  × Urdu-RTL) beyond the `fake-indexeddb` node harness.
- **Existing components to reuse:** the vitest suites as the logic oracle; a new browser/E2E track (none
  in-repo yet).
- **Dependencies:** device lab / cloud device farm (product/ops decision).
- **Risks:** flaky E2E; maintenance cost.
- **Privacy implications / child-safety implications:** synthetic data only.
- **Data flow:** n/a.
- **Failure modes:** matrix gaps (documented coverage).
- **Acceptance criteria (OFFLINE_TEST_PLAN §4):** the matrix runs on representative pilot hardware,
  including captive-portal and Save-Data.
- **Estimated effort:** **M** (new harness).

### B6 — Data-residency pinning (SG-4)

- **Purpose:** ensure the sync endpoint, package host/CDN, and telemetry sink are in-region (Pakistan
  PDPB/PECA + GDPR-K).
- **Existing components to reuse:** deployment config (no hard region string in code today).
- **Dependencies:** **FD-02** host decision + WS1 residency decision.
- **Risks:** cross-border data flow non-compliance.
- **Privacy implications:** central to lawful processing of child data.
- **Child-safety implications:** indirect (compliance).
- **Data flow:** all offline egress targets resolve to in-region hosts.
- **Failure modes:** misconfiguration (add to release checklist + risk register).
- **Acceptance criteria:** residency targets configurable + defaulting in-region; verified at deploy.
- **Estimated effort:** **S** engineering — governance/config decision is the gate.

---

## C. Future enhancements

### C1 — Durable server-side idempotency ledger + cursor (G5 / SG-7)

- **Purpose:** persist seen `client_event_id` + cursor (sharded by `hash(student_ref)`) so detection for
  **non-attempt** delta types survives a server restart (CX-7). **Attempt idempotency is already durable
  via the evidence table** (6.2B), so this is optional.
- **Reuse:** the sync store; existing partitioning (`hash(student_ref)`). **Dependencies:** none.
  **Effort:** **S–M**. **Privacy/child-safety:** C1 keys only, no PII. **Acceptance:** after a simulated
  server restart, previously-seen non-attempt deltas are still `duplicate`/`ignored`.

### C2 — Option B: ported deterministic TS runtime for full offline adaptivity (G2)

- **Purpose:** full offline adaptive sessions (decisions on-device) for at-home Pilot 2+. **Must remain
  LLM-free and deterministic** (a faithful port of the existing pure engine — not a redesign).
  **Effort:** **L**. **Child-safety:** no generative AI offline (AR-C-06) preserved. **Dependency:**
  Option A/B decision (Decision D-1).

### C3 — Full offline-safety design for unsupervised at-home use (SG-6)

- **Purpose:** the comprehensive offline-safety model beyond B2 that M-Safe requires before **unsupervised
  at-home offline** is enabled (Pilot 2+). **Dependency:** M-Safe + B2. **Effort:** **L** (design-led).
  Until it lands, unsupervised at-home offline stays **disabled** (T-SAFE-4).

### C4 — Hardware-backed key storage / WebAuthn device binding

- **Purpose:** stronger device binding + key protection for the offline token beyond the FD-14 baseline.
  **Dependency:** FD-14 + platform support. **Effort:** **M–L**. **Future.**

---

## 3. Decisions required before implementation (product / policy)

| # | Decision | Blocks | Owner | Source |
| --- | --- | --- | --- | --- |
| **D-1** | Option A (offline-lite) vs Option B (ported runtime) for full offline | C2, at-home scope | Product + Eng | OFFLINE_ARCHITECTURE §11 (G2) |
| **D-2** | Per-profile offline key derivation + **key durability** (losing the key must not lose the un-synced queue) | B1 | Security + Eng | Security review §3 |
| **D-3** | Offline token TTL per cohort (24–72h) + revocation registry (Redis) placement | A5 | Security + Product | Auth strategy §; O-3 |
| **D-4** | **FD-14** KMS/HSM topology + offline-cache key strategy (currently undecided, Phase-1.5) | A5, B1, A1(prod key) | Founder + Security | FOUNDER_DECISIONS FD-14 |
| **D-5** | Unsynced-but-withdrawn data: discard locally vs sync-then-erase | A3 | Legal + Product | Retention §; SG-5 |
| **D-6** | Where a `safety.flag` persists (C4 safeguarding record) given "no new child-data tables" | B2 | Architecture + Safety | Crisis protocol §5; constraint |
| **D-7** | Crisis **SLA values** (T0–T3) + **mandatory-reporting channels + external-referral authorizer** (DECISION REQUIRED) | A4 template, B2 | Legal + Clinical + Safeguarding | Crisis protocol §2/§5 (M-Safe) |
| **D-8** | Consent model: what offline telemetry is permitted + how consent is surfaced to the client | B3 | Legal + Product | Privacy model; consent |
| **D-9** | **FD-02** data-residency host (in-region) | B6, B3 sink, A5 residency | Founder + Ops | FD-02; WS1 residency |
| **D-10** | M-Gov closure (DPIA, consent, child-identity, mandatory-reporting, residency) | A5 (and all child data) | Governance | MASTER_EXECUTION_PLAN WS1 |

---

## 4. Recommended build order + effort roll-up

**Gate-free, start now (hardens the pilot, no decisions needed):**

1. **A1** Ed25519 signing (S–M) · **A2** chaos tests (S–M) · **B4** eviction polish (S) — pure engineering
   over existing seams; land these first.
2. **A4** offline crisis affordance UI + packaged-template wiring (S) — reachable-part only; the template
   content awaits D-7.
3. **B1** at-rest AES-GCM **mechanism** (M) — prototype the `KVStore` decorator now; wire production keys
   after **D-4 (FD-14)**.
4. **C1** durable idempotency ledger (S–M) — optional; do if CX-7 coverage is wanted.
5. **B5** device-matrix automation (M) · **B6** residency pinning config (S).

**Gated — do not start until the gate clears:**

- **A5** offline auth token → **D-10 (M-Gov)** + **D-4 (FD-14)** (L).
- **A3** purge trigger → consent model (M-Gov/WS8) (mechanism S, ship on trigger).
- **B2** crisis-flag routing → **D-7 (M-Safe)** (M–L after policy).
- **B3** telemetry upload → **D-8 (consent)** + **D-9 (residency)** (S–M).
- **C2/C3/C4** → Pilot 2+ scope.

Rough roll-up: gate-free A/B engineering ≈ **M total**; gated items are governance-bound, not
engineering-bound — their long pole is the **decisions (D-4, D-7, D-10)**, not the code.

---

## 5. GO / NO-GO by feature (readiness)

| Feature | Verdict |
| --- | --- |
| A1 signing, A2 chaos, A4 affordance-UI, B4 eviction, C1 ledger, B5 matrix, B6 config | **GO to implement** (gate-free; A1/A2/A4 recommended before any child) |
| B1 at-rest encryption (mechanism) | **GO to prototype**; **NO-GO for production keys** until D-4 (FD-14) |
| A3 purge mechanism | **GO to build**; **do not ship** until the consent trigger (M-Gov/WS8) exists |
| A5 offline auth token | **NO-GO** until **D-10 (M-Gov)** + **D-4 (FD-14)** |
| B2 crisis-flag routing | **NO-GO** until **D-7 (M-Safe)** (SLAs + reporting channels DECISION REQUIRED) |
| B3 telemetry upload | **NO-GO** until **D-8 (consent)** + **D-9 (residency)** |
| A4 crisis template content | **NO-GO** until **D-7** (clinician + legal sign-off) |

**Bottom line:** 6.2C splits cleanly into **gate-free hardening that can begin immediately** (signing,
chaos tests, eviction, the reachable crisis affordance, the at-rest mechanism, the optional ledger) and
**governance-bound work whose blocker is a decision, not code** (offline auth token → M-Gov+FD-14;
crisis-flag routing → M-Safe; telemetry → consent; residency → FD-02). For a **supervised Pilot 1 on
managed devices**, the on-site safeguarding lead is the compensating control for the offline-safety
items that remain gated (security review §6, PILOT_PLAN Pilot 1). No architecture is redesigned; every
item extends an existing seam. **Awaiting approval before any 6.2C implementation.**
