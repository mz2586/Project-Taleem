# Offline Subsystem — Security Review (Design Review)

Status: **Design review only (Phase 6.2). No code, no source changes, no commits.** Covers subsystem
**(11) Package signing / integrity** in full, plus the **cross-cutting security review** of all 14
offline subsystems. Companion to [OFFLINE_ARCHITECTURE.md](OFFLINE_ARCHITECTURE.md),
[OFFLINE_SYNC_SPEC.md](OFFLINE_SYNC_SPEC.md), [OFFLINE_STORAGE_SPEC.md](OFFLINE_STORAGE_SPEC.md),
[OFFLINE_TEST_PLAN.md](OFFLINE_TEST_PLAN.md).

Extends the existing security posture: `docs/03-security-privacy/{11-authentication-strategy,
13-security-model,14-privacy-model,15-child-safety-framework,51-threat-model,57-data-retention-schedule}.md`.
The offline subsystem must **not** weaken any invariant that holds online: deny-by-default PDP,
IDOR-guarded learner scoping, no child PII outside Identity, append-only evidence, and **child safety
first**.

---

## 0. Security invariants inherited (must still hold offline)

| Invariant | Online mechanism | Offline obligation |
| --- | --- | --- |
| Deny-by-default authorization | `auth/pdp.py` fail-closed | offline token is **capability-scoped**; server re-checks on sync |
| Learner isolation (IDOR) | `require_owner_or(...)` | per-profile namespacing; a device never reads another child's data |
| No child PII outside Identity | pseudonymous `student_ref` (C1) | **no PII** in IndexedDB/Cache/token/telemetry |
| Evidence integrity | append-only, idempotent by `evidence_id` | offline queue is append-only; server dedupes on sync |
| Role from token, never body | `bearer_claims` (CTO B1) | offline token carries role/`sub`; body never trusted |
| No generative AI to children | templated runtime (AR-C-06) | **no LLM offline, ever**; only packaged approved content |
| Content approved before a child sees it | editorial + QA gate | **signed** packages guarantee integrity build→device |

---

## 1. Threat model (STRIDE-lite, offline-specific)

Extends `docs/03-security-privacy/51-threat-model.md` for the offline surface (device + package host +
sync channel).

| Threat | Vector | Mitigation | Subsystems |
| --- | --- | --- | --- |
| **Tampering** | modified/forged lesson package delivers unapproved content to a child | **Ed25519-signed manifest + per-asset SHA-256**, verified before install (§2) | packages, download, cache versioning |
| **Info disclosure** | another user / attacker reads C2 learning data on a shared/lost device | at-rest encryption of C2 stores; per-profile namespacing; no PII stored (§3) | storage, checkpoints, progress |
| **Spoofing** | stolen offline token used elsewhere | **device-bound**, short-TTL offline token (`Claims.device_id`); server re-validates + can revoke on sync (§4) | offline auth, connectivity recovery |
| **Elevation of privilege** | client forces mastery/promotion or cross-child access | mastery **derived server-side** from evidence; PDP + IDOR server-side; summative stays **mentor-mediated** (§4) | sync, resolution |
| **Repudiation / double-count** | replays or multi-device sync inflate results | append-only evidence, idempotent by `evidence_id` + `client_event_id` (§ sync spec) | sync, conflict detection |
| **DoS** | reconnect storm; oversized packs exhaust storage | jittered backoff; storage pre-flight; lite packs (§6) | connectivity, low-storage, download |
| **Safety bypass** | a child in distress offline cannot reach a human | offline crisis affordance + **priority safety flag** queued; supervised pilot mitigation (§6) | safety-offline |

---

## 2. Subsystem — Package signing / integrity (full spec)

- **Purpose:** guarantee that the exact, approved, unmodified content leaves the build pipeline and
  reaches the child's device — a **child-safety** control, not merely a data-integrity one (a tampered
  pack could put unapproved content in front of a child; AR-C-06 requires approved content only).
- **Components:** a **build-time signer** (server/CI, KMS-held Ed25519 key, aligned to FD-14 asymmetric
  keys); the **signed manifest** (`{package_id, lesson_ids, version, content_hash, assets[{ref, kind,
  sha256, bytes}], signature, signing_key_id}`); a **client verifier** in the download manager /
  installer; **pinned public keys** shipped in the app bundle (supporting rotation via `signing_key_id`).
- **Data flow:** build resolves a published lesson → computes each asset's SHA-256 → builds the manifest
  → signs the canonicalized manifest with the private key (KMS) → publishes manifest + assets to in-region
  object storage/CDN. Client: fetch manifest → **verify signature** against the pinned key for
  `signing_key_id` → download assets → **verify each SHA-256** → only then install atomically (state →
  `ready`). Any failure → discard, do not install, surface an honest error.
- **APIs used:** Web Crypto (`crypto.subtle.verify` for Ed25519, `digest` for SHA-256), with a
  lazily loaded `@noble/ed25519` fallback where WebCrypto Ed25519 is missing (§8.2); Cache
  Storage/IndexedDB for staging; the manifest fetched over HTTPS.
- **Failure modes:** signature invalid (tampered/forged); asset hash mismatch (corruption/MITM); unknown
  or revoked `signing_key_id`; downgrade to an older/unsigned pack; key compromise.
- **Recovery strategy:** reject and re-fetch on any mismatch (bounded retry); refuse unsigned or
  unknown-key packs; **downgrade protection** via `version` + signature; **key rotation** by pinning
  multiple current keys and retiring compromised ones in an app update; a compromised key triggers a
  server-side pack re-sign + client re-verify on next connect.
- **Security considerations:** private key **never leaves KMS**; public keys pinned client-side (no TLS-
  only trust); HTTPS in-region transport; the verifier runs before content is ever rendered to a child.
- **Performance considerations:** SHA-256 is fast; verify per asset as it lands (streamed); signature
  verification is one cheap operation per pack; caching is content-hash-addressed so re-verification is
  avoided for unchanged assets.
- **Acceptance criteria:** a pack with any altered byte fails verification and is not installed; an
  unsigned or unknown-key pack is rejected; a downgrade attempt is refused; key rotation installs cleanly
  via a pinned key set; no unverified asset is ever rendered to a child.

---

## 3. At-rest protection of child learning data (C2)

- **Scope:** `evidence_queue`, `checkpoints`, `read_cache`, `progress_local` — all C2 learning data
  (`docs/14-privacy-model.md §4-5`). **No C3 child PII is ever stored offline** (only `student_ref`, C1).
- **Mechanism:** encrypt C2 records at rest with **Web Crypto AES-GCM**; keys managed per profile and
  held in a non-extractable `CryptoKey` where the platform allows; sealed attempts are append-only +
  encrypted (doc 33 §5).
- **Honest limitation (documented, not hidden):** a browser is **not a secure enclave** — a fully
  compromised device can, in principle, reach IndexedDB and in-memory keys. This is mitigated, not
  eliminated, by: **(a)** storing **no PII** (pseudonymous `student_ref` only, so exposure is bounded to
  de-identified learning facts), **(b)** short retention + prompt sync + queue clearing, **(c)** per-
  profile namespacing and **clear-on-switch**, **(d)** reliance on OS/device-level security for
  at-rest confidentiality. **Recommendation:** treat device at-rest confidentiality as a residual risk in
  the risk register and prefer managed/kiosk devices for the pilot (Pilot 1 uses provided devices —
  PILOT_PLAN), where MDM enforces device encryption.
- **Acceptance criteria:** C2 stores are encrypted; no C3 PII is present; keys are per-profile and
  cleared on learner switch; the residual device-compromise risk is documented and carried in the risk
  register.

---

## 4. Offline authentication + authorization (subsystem-gated, 6.2C)

- **Design (from `docs/03-security-privacy/11-authentication-strategy.md`, doc 33 §7):** a **device-bound,
  time-boxed offline session token** — the `Claims.device_id` field already exists in
  `auth/jwt_verifier.py`. It is **capability-scoped**: it may read cached lessons and queue submissions;
  it **cannot** mutate grades, cannot read cross-child data, and cannot escalate privilege. It is
  **short-TTL**, re-validated on reconnect, and a **revoked session drops on the next sync**.
- **Server enforcement is unchanged and authoritative:** on sync, the server applies PDP `(system, write,
  sync.batch)`, re-validates the token, and re-derives all state — a client can never self-grant. IDOR
  scoping and role-from-token (never body) still hold.
- **Governance gate:** issuing real child tokens is **blocked by the Phase-1.5 governance gate (M-Gov)**;
  only the HS256 **dev stub** exists today (`NEXT_PUBLIC_DEV_STUDENT_TOKEN`, `sub == student_ref`, role
  `student`). **Build the offline token only after M-Gov** (gap G6); use the dev stub for internal Pilot 0
  only.
- **Failure modes / recovery:** token expiry mid-offline → allow cached read + continued queueing under a
  grace window, force a refresh on reconnect (never lose queued writes); stolen token → device binding +
  short TTL + server revocation limit blast radius.
- **Acceptance criteria:** the offline token cannot read another child's data or mutate grades; it expires
  and refreshes without losing queued writes; server-side revocation takes effect on next sync; no token
  is cached by the service worker or logged.

---

## 5. Privacy, residency, retention (offline-specific)

- **No child PII offline.** Enforced by schema (only `student_ref`), by telemetry restriction (C1/C0
  only), and by never placing PII in tokens/logs (inherited invariant).
- **Data residency (governance requirement, `docs/14-privacy-model.md §2`):** the sync endpoint, package
  host/CDN, and telemetry sink must be **in-region** (Pakistan PDPB/PECA + GDPR-K best-interests). No hard
  region string exists in code — treated as a governance/config dependency, **recommendation** to pin at
  deployment.
- **Retention + right-to-erasure (`docs/57-data-retention-schedule.md`):** disposable caches carry TTLs;
  the durable queue clears on `applied`; on **de-enrolment or consent withdrawal**, the client clears all
  C2 offline stores at next connect on a **server purge signal** (recommendation — a small server→client
  purge instruction; no new child-data table needed). Synced evidence follows existing server retention
  (hash-sharded, partition-aligned) — offline changes nothing there.
- **Acceptance criteria:** no offline store or telemetry payload contains child PII; residency targets are
  configurable and default in-region; a de-enrolment/consent-withdrawal clears offline C2 data at next
  connect; disposable caches honor TTLs.

---

## 6. Child safety offline (non-negotiable)

- **No generative AI offline, ever (AR-C-06).** The teaching runtime is templated/pure; offline serves
  only packaged, pre-moderated content. This is already the platform's design and must not regress —
  Option B (runtime port, architecture §11) **must remain LLM-free and deterministic**.
- **Content pre-moderated at packaging** (doc 33 §8); **signing** (§2) guarantees the child sees exactly
  the approved bytes.
- **Offline crisis affordance:** a distress/help affordance is **always present offline**; when triggered
  it (a) shows immediate, packaged self-help + local crisis information, and (b) **queues a priority
  safety-flag delta** synced with highest priority on reconnect (doc 33 §8, `docs/15-child-safety-
  framework.md`).
- **Documented limitation + pilot mitigation:** offline, a distress signal **cannot reach a remote human
  immediately** — this is a real safeguarding gap. **Mitigation for Pilot 1:** sessions are **on-site,
  Wi-Fi-supervised, with mentors + a safeguarding lead physically present** (PILOT_PLAN) — so an offline
  child in distress still reaches a **present** human, and the queued flag reaches the remote
  safeguarding record on reconnect. At-home offline (Pilot 2+) **requires** a stronger offline-safety
  design before enabling — **NO-GO for unsupervised offline until that lands** (M-Safe dependency).
- **Acceptance criteria:** no LLM path exists offline; the crisis affordance is reachable with no
  network; a triggered flag queues at highest priority and syncs first on reconnect; the offline-safety
  limitation is documented and gated to supervised use.

---

## 7. Per-subsystem security summary (all 14)

| # | Subsystem | Primary security control |
| --- | --- | --- |
| 1 | Offline lesson packages | signed manifest + per-asset hash; pre-moderated content |
| 2 | Service Worker | never cache tokens/errors/non-GET; scoped to origin + trusted host |
| 3 | IndexedDB schema | at-rest encryption of C2; no C3 PII; per-profile namespacing |
| 4 | Download manager | verify signature before trusting bytes; in-region host only |
| 5 | Local progress storage | disposable; server authoritative; clear-on-switch/de-enrolment |
| 6 | Session checkpointing | encrypted C2; `student_ref` only; atomic writes |
| 7 | Background sync | authenticated; PDP-enforced server-side; idempotent |
| 8 | Conflict detection | server-authoritative; client cannot force acceptance |
| 9 | Conflict resolution | mastery derived server-side; summative stays mentor-mediated |
| 10 | Cache versioning | integrity via signed manifest; downgrade protection |
| 11 | Package signing/integrity | Ed25519 + SHA-256; KMS key; pinned public keys (§2) |
| 12 | Low-storage handling | never evict un-synced C2; per-profile isolation on cleanup |
| 13 | Connectivity recovery | authenticated probe; token re-validation/revocation on reconnect |
| 14 | Telemetry/diagnostics | C1/C0 only; consent + residency gated; no `student_ref` in payload |

---

## 8. Security gaps + recommendations

| ID | Item | Status | Recommendation |
| --- | --- | --- | --- |
| SG-1 | Package signing pipeline (KMS Ed25519) | not built (part of G1) | Build with the package builder (6.2A/C) |
| SG-2 | At-rest encryption of C2 IndexedDB stores | not built | 6.2C; document residual device-compromise risk |
| SG-3 | Device-bound offline token | spec'd, **governance-gated** (G6) | Build after M-Gov only |
| SG-4 | Data-residency pinning (endpoint/CDN/telemetry) | governance/config | Pin in-region at deploy; add to risk register |
| SG-5 | De-enrolment/consent-withdrawal purge signal | not built | Small server→client purge instruction (no new child table) |
| SG-6 | Offline safety for **unsupervised** at-home use | limitation | **NO-GO** until a stronger offline-safety design + M-Safe |
| SG-7 | Durable server-side idempotency ledger | in-memory prototype (G5) | Persist `client_event_id` + cursor, sharded by `hash(student_ref)` |

### 8.1 Change: package signatures are mandatory on every install path (2026-10-23)

**Finding.** The shared web offline client (`apps/web/lib/student/offlineClient.ts`) was built with
no pinned keys and `requireSignature` off. Through it, an unsigned package — or a signed one whose
key the client could not resolve — installed unverified (the 6.2A/6.2B compatibility path). Only the
offline library screen forced verification, with its own second download-manager configuration.

**Change (fail closed).**

- `DownloadManager` (`apps/web/lib/offline/packages.ts`) always requires a signature. An unsigned
  manifest, a missing key resolver, an unknown `signing_key_id`, or a signature that does not verify
  throws `SignatureError`; nothing is written and `signatureFailures` is counted. `requireSignature`
  can no longer be set to `false`.
- The only opt-out is `allowUnsignedForTests: true`, honoured only when `process.env.VITEST === "true"`
  — set by the Vitest runner and defined by no Next.js build, server or browser bundle. A test proves
  the flag is ignored outside Vitest and that it never accepts a signature that fails to verify.
- One configuration: `createDownloadManager` (`lib/offline/index.ts`) is used by `createOfflineClient`,
  and the offline library screen now uses the shared client's manager instead of building its own.
- Keys (`lib/offline/keys.ts`): build-time `NEXT_PUBLIC_OFFLINE_SIGNING_KEYS` (`{key_id: hex}`) is the
  preferred source. Without it, trust-on-first-use from `GET /v1/offline/signing-keys`, remembered
  per device; a later answer with a different key for a known `key_id` is refused and that `key_id`
  is dropped. A **production build without pinned keys** logs `OFFLINE_SIGNING_KEYS_NOT_PINNED` to the
  console and records `signingKeysPinned: false` in the local sync diagnostics (tested).
- Fixed alongside: the storage pre-flight treated an unknown quota (`{usage: 0, quota: 0}` where
  `navigator.storage` is missing) as "no space" and refused every install on such devices. Unknown
  quota now defers to the browser's own quota error.

**Residual risk.** Trust-on-first-use trusts the first key a device sees. Set
`NEXT_PUBLIC_OFFLINE_SIGNING_KEYS` in every production deployment to close it (SG-1 key custody
remains open).

### 8.2 Change: fallback Ed25519 verifier for browsers without WebCrypto Ed25519 (2026-10-23)

**Finding.** Package signatures were verified only with WebCrypto Ed25519 (`crypto.subtle`,
`{ name: "Ed25519" }`). That exists in Chromium 137+, Safari 17+ and Firefox 129+. The browser
journey on Chromium 131 failed to save a lesson ("This lesson could not be checked"). Many of
Taleem's users have low-end Android phones with older WebViews, so they could not save lessons for
offline use. Verification stayed mandatory and fail closed, so this was an availability failure,
not a security one.

**Change.** `apps/web/lib/offline/signature.ts` now picks one of two verifiers per device. The check
stays mandatory and fail closed on both.

- **Selection.** `detectSignatureVerifier` runs once per `SubtleCrypto` and caches the answer. It
  imports the RFC 8032 §7.1 TEST 1 public key with WebCrypto, then checks that the TEST 1 signature
  verifies and that a copy with one bit flipped does not. If that works, the device uses
  `"webcrypto"`. If it throws (`NotSupportedError` on Chromium < 137) or gives a wrong answer, the
  device uses `"noble"`.
- **The choice is fixed on the key.** `importPublicKey` returns a `CryptoKey` on the WebCrypto path
  and a `NobleEd25519Key` (the raw 32 bytes) on the fallback path. `verifyManifestSignature` sends
  each key to its own verifier. If WebCrypto rejects a signature, or throws while verifying it, the
  result is a failure. The fallback is used only when WebCrypto Ed25519 is *unavailable*. It never
  re-checks a signature that WebCrypto rejected (tested with a pass-through spy on the library).
- **Library.** `@noble/ed25519` **3.2.0** is pinned exactly in `apps/web/package.json` (released
  2026-08-27; audited; no dependencies; MIT). It is called through `verifyAsync`, which hashes with
  WebCrypto SHA-512 (`crypto.subtle.digest`), so no second dependency is needed. It lives in
  `lib/offline/ed25519Fallback.ts` and is loaded with a dynamic `import()`. Webpack puts it in its
  own async chunk (7.1 kB raw, 3.2 kB gzip), so devices with WebCrypto Ed25519 never download it.
  The always-loaded offline code grew by about 1.1 kB gzip: `/student/offline` First Load JS went
  from 154 kB to 155 kB in the `next build` output.
- **Diagnostics.** The local sync diagnostics record `signatureVerifier: "webcrypto" | "noble"`
  (`null` until probed). This holds no PII and does not leave the device.

**Semantics (strictness parity).** Before either verifier runs, the same encoding checks apply on
both paths, so the two paths do not depend on how each library treats edge cases:

| Check | Both paths (`signature.ts`) |
| --- | --- |
| Hex | strict: an odd length or a non-hex character is rejected (it used to parse silently as `0`) |
| Lengths | public key exactly 32 bytes, signature exactly 64 bytes |
| Public key A | canonical encoding (y < p), and not a small-order point (all 8, plus the x = 0 encodings with the sign bit set) |
| R | canonical encoding (y < p) |
| S | canonical: **S < L** (rejects S + L malleability) |

After these checks, each verifier uses its own equation:

- **WebCrypto:** the platform's RFC 8032 verifier (BoringSSL in Chromium, the cofactorless equation
  `[S]B = R + [k]A`).
- **noble:** `verifyAsync(..., { zip215: false })`, the library's strict RFC 8032 / FIPS 186-5
  branch. This is **not** ZIP-215. It rejects non-canonical A and R and small-order A, enforces
  S < L, and uses the cofactored equation `[8][S]B = [8]R + [8][k]A`.

The two equations can differ only for a signature whose R has a small-order component. An honest
signer never produces one, and only the holder of the private key could make one. Every
attacker-supplied malformation is rejected identically on both paths. Tests cover RFC 8032 TEST 1–3,
tampered message, signature and key, wrong lengths, non-hex input, S + L, y = p, and small-order keys
(including the identity-key forgery), each on both paths
(`lib/offline/__tests__/signatureFallback.test.ts`).

**Minimum supported browsers for saving lessons offline.**

- **WebCrypto path:** Chromium / Android WebView 137+, Safari 17+, Firefox 129+.
- **Fallback path:** any browser with WebCrypto SHA-512 in a secure context (HTTPS), IndexedDB and
  a service worker. The library chunk is transpiled to the app's browser target
  (`transpilePackages` in `next.config.mjs`; the built chunk contains no optional chaining), so
  BigInt is its remaining requirement: Chromium / Android WebView 67+, Safari 14+, Firefox 68+.
  Verified through the real UI on Chromium 131; the lower floor follows from the BigInt requirement
  and has not yet been tested on a physical Chromium 67–79 device.

On an older engine the fallback chunk fails to load, and saving fails closed with the honest "could
not be checked" message. Nothing is installed unverified. The always-loaded offline module uses no
BigInt literals, so it still parses on the Next.js build target (Chrome 64). Verified in Node 20
(both paths, the fallback forced by a WebCrypto stub). Also verified in a real browser: the
`make e2e-web` journey on Playwright 1.49.1's Chromium 131.0.6778.33, which has no WebCrypto
Ed25519 (`NotSupportedError`). There the pinned-key package saved, played offline from the service
worker, and synced (10 answers, server `total_attempts` 5 → 15).

**Residual risk.** The fallback uses JavaScript BigInt arithmetic, which is not constant time.
Verification handles only public data (public key, signature, message), so there is no secret to
leak through timing.

**Security verdict:** the offline design **preserves every online security invariant** and adds
integrity (signing) and confidentiality (at-rest encryption) controls. It is **safe to implement 6.2A
foundations** now. **6.2C security items and unsupervised at-home offline are NO-GO until M-Gov
(offline token) and M-Safe (offline safety) clear** — consistent with the phased GO/NO-GO in
[OFFLINE_ARCHITECTURE.md](OFFLINE_ARCHITECTURE.md) §14. For Pilot 1, on-site supervision is the
compensating control that makes offline-lite acceptable.
