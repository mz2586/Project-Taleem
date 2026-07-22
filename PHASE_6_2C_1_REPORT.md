# Phase 6.2C-1 — Engineering Hardening Report

Status: **Complete.** Implements the gate-free "Category A/B engineering hardening" subset of the
approved [PHASE_6_2C_IMPLEMENTATION_PLAN.md](PHASE_6_2C_IMPLEMENTATION_PLAN.md). **No governance-gated
work** (no offline auth token, no device-bound credentials, no governance-gated identity, no
child-safety escalation workflows, no consent-gated telemetry upload). Local commit + `phase-6.2C-1`
tag. Backward-compatible with 6.2A/6.2B.

---

## 1. Scope delivered

| # | Item | Where |
| --- | --- | --- |
| 1 | **Ed25519 package signing** | `platform/ed25519.py` (pure-stdlib RFC 8032), `adapters/package_signer.py`, `domain/offline_package.py` (`signer` hook), `application/offline_service.py`, `GET /v1/offline/signing-keys` |
| 2 | **Client signature verification** | `apps/web/lib/offline/signature.ts` (WebCrypto Ed25519), `packages.ts` `DownloadManager` verify-before-trust |
| 3 | **Chaos / fault-injection framework** | `apps/web/lib/offline/chaos.ts` (`FaultyStore`, `faultyPostBatch`) + chaos tests |
| 4 | **Cache purge / de-enrolment mechanism** | `apps/web/lib/offline/purge.ts` (`PurgeService`), `syncClient` honors an optional server `purge` signal |
| 5 | **Offline diagnostics enhancements** | `diagnostics.ts` (+signature/integrity/eviction/purge counters, old-shape hydration) |
| 6 | **Cache eviction improvements** | `packages.ts` `ensureSpace` + `evictLRU` (LRU over disposable packages; never touches the un-synced queue/checkpoints) |

---

## 2. Ed25519 signing — the interop story (the crux)

Python has no `cryptography` dependency and the domain is pure-stdlib, so the signer is a **vendored
pure-stdlib RFC 8032 Ed25519** (`platform/ed25519.py`). The client verifies with **WebCrypto**
(`crypto.subtle` `{ name: "Ed25519" }`). To guarantee these interoperate, a **cross-language interop
vector is locked in both test suites**: the backend signs a fixed (seed → message) and the exact
resulting public key + signature are asserted to verify under Node/browser WebCrypto
(`tests/test_ed25519.py` and `apps/web/lib/offline/__tests__/signature.test.ts` share the vector). A
change that breaks interop fails both suites.

- **What is signed:** a canonicalization-free payload `${package_id}\n${version}\n${content_hash}` —
  no JSON key-ordering dependency, and binding `package_id` + `version` (not just the hash) makes it
  **downgrade/pointer-swap resistant**.
- **Keys:** the private **seed never leaves the server** (dev seed from config, production supplies a
  real seed — ideally KMS-held per FD-14; production boot fails closed on the default seed, mirroring
  the JWT-secret guard). Clients hold only the 32-byte public key, fetched from `/v1/offline/signing-keys`
  (public keys are not secret) or pinned in the bundle.
- **Backward compatible:** `signature`/`signing_key_id` default to empty; an unsigned manifest still
  installs unless the client sets `requireSignature`.

**Client enforcement** (`DownloadManager`): verify the signature against a pinned key **before** the
content-hash check; reject on bad/absent/unknown-key signature when `requireSignature` is set; record
`signature_ok` on the stored package.

---

## 3. Purge, eviction, diagnostics, chaos

- **Purge (SG-5 mechanism):** `PurgeService.purgeStudent(ref)` clears the four C2 stores (`read_cache`,
  `progress_local`, `checkpoints`, `evidence_queue`) for one learner, learner-scoped, with an
  `includeUnsynced` policy option (default erase). C0 curriculum stays. The **trigger is governance-gated
  and out of scope** — the client also honors an optional `purge` field on the sync response for when
  a server later delivers it. Whether un-synced-but-withdrawn data is discarded vs synced-then-erased
  is decision **D-5** (not decided here).
- **Eviction:** `ensureSpace(bytes)` LRU-evicts disposable **packages/content** (C0, re-downloadable)
  until a download fits, then refuses with `QuotaExceededError`. It **never** touches the un-synced
  `evidence_queue`/`checkpoints` (they live in other stores) — the never-evict-before-sync invariant
  holds by construction.
- **Diagnostics:** added local counters `signatureFailures`, `integrityFailures`, `evictions`,
  `evictedBytes`, `purges`, wired from the download path. Still **local-only** (no upload — that is the
  consent-gated B3, deferred). Old 6.2B-shaped records hydrate with the new fields defaulted.
- **Chaos framework:** `FaultyStore` (injects throw / quota / crash-after-N-ops faults over any
  `KVStore`) and `faultyPostBatch` (flapping/offline network) — a reusable, typed harness that proves
  the sync engine survives faults with no data loss.

---

## 4. Reuse + compatibility

- **No redesign.** Signing attaches to the existing `build_manifest`; verification slots into the
  existing `DownloadManager.download` before the existing content-hash check; purge/eviction operate
  over the existing `KVStore`; diagnostics extend the existing 6.2B store. Every consumer of the
  offline lib is unchanged.
- **Constraints honored:** no new child-data tables; pseudonymous `student_ref` only, no child PII in
  stores/keys/diagnostics; deny-by-default PDP unchanged (signing-keys endpoint reuses the existing
  `read learning.knowledge` grant — no new PDP rule); no generative AI offline.
- **Backward compatible:** unsigned packages still install; older diagnostics records hydrate;
  `BatchResult.purge` and the manifest signature fields are optional.

---

## 5. Testing

| Suite | Added | Covers |
| --- | --- | --- |
| Backend `tests/test_ed25519.py` | 8 | locked interop vector (public key + signature), sign/verify roundtrip, tamper, wrong-key, malformed inputs, seed-length |
| Backend `tests/test_offline_packages.py` | +5 | unsigned-by-default (compat), signed manifest verifies against the public key, signature binds content+version (downgrade guard), `/signing-keys` endpoint + auth, bad-seed rejected |
| Frontend `signature.test.ts` | 6 | **Python↔WebCrypto interop vector**, generated-key roundtrip, tamper (hash/version/package_id), absent signature, `pinnedKeyResolver` |
| Frontend `packagesHardening.test.ts` | 9 | signed install + `signature_ok`, tampered/unknown-key/unsigned rejection, backward-compat unsigned install, LRU eviction order + refuse-when-full |
| Frontend `purge.test.ts` | 4 | scoped C2 purge, `includeUnsynced` option, diagnostics, purge-on-sync signal |
| Frontend `chaos.test.ts` | 5 | `FaultyStore` faults (throw/quota/disabled), flapping + toggle-offline network drains with no loss |
| Frontend `diagnosticsHardening.test.ts` | 2 | new counters (no PII), old-shape hydration |

Backend PostgreSQL-gated tests run in CI (`CS_DATABASE_URL`); locally they skip.

---

## 6. Quality gate summary

| Gate | Result |
| --- | --- |
| Ruff | ✅ All checks passed |
| Black (`--check`) | ✅ 115 files unchanged |
| mypy `--strict` | ✅ no issues in 93 source files |
| pytest | ✅ **159 passed, 6 skipped** (6 = PostgreSQL-gated) |
| OpenAPI (redocly 1.25.11) | ✅ all contracts valid (offline contract updated) |
| Frontend typecheck (`tsc --noEmit`) | ✅ clean |
| Frontend tests (`vitest run`) | ✅ **78 passed** (19 files) |
| Frontend build (`next build`) | ✅ compiled + 12 static pages |

---

## 7. Deferred (still gated — not in 6.2C-1)

Device-bound offline auth token (M-Gov + FD-14) · automated crisis-flag routing (M-Safe) ·
consent-gated telemetry upload (consent + residency) · at-rest AES-GCM production keys (FD-14) ·
real-device matrix automation · residency pinning (FD-02). See
[PHASE_6_2C_IMPLEMENTATION_PLAN.md](PHASE_6_2C_IMPLEMENTATION_PLAN.md) §A5/§B/§3.
