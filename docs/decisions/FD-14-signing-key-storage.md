# Decision Brief FD-14 — Signing-Key Storage and Key Management

**Status:** Open — owner decision required · **Owners:** Founder + Security ·
**Prepared:** 2026-10-22 · **Register entry:** [`FOUNDER_DECISIONS.md` § FD-14](../../FOUNDER_DECISIONS.md)

## The decision

Where the private keys that sign learner and guardian access tokens and offline lesson packages
live, who can use them, and how they are rotated and destroyed.

## Current state (evidence)

- Tokens: Ed25519 / EdDSA, kid-addressed, rotating JWKS, issuer/audience bound
  (`services/core-api/src/taleem_core/auth/keys.py`, `test_auth_asymmetric.py`).
- The private seeds are supplied as **environment variables** (`TALEEM_JWT_SIGNING_SEED`,
  `TALEEM_OFFLINE_SIGNING_SEED`). Production refuses to start with the well-known dev seed
  (`platform/config.py`).
- Risk: anyone who can read the deployment's environment can mint a token for any learner. This is
  Production Blocker #16.

## What is not blocked

The code is being changed so that signing goes through a **signer port**: callers ask for a
signature over bytes and never touch key material. The environment-seed signer remains the
development and test implementation. A KMS-backed signer can then be added without touching any
caller. No production key is generated or deployed by engineering under an unapproved arrangement.

## Options

| | (a) Cloud KMS asymmetric signing (key never leaves KMS) | (b) Dedicated / cloud HSM | (c) Platform-managed signing service on the hosting provider | (d) Secrets manager holding the seed (status quo, hardened) |
| --- | --- | --- | --- | --- |
| **Key exposure** | Non-exportable; app gets signatures only | Non-exportable, FIPS 140-2/3 L3 | Non-exportable (provider-managed) | Seed loaded into app memory |
| **Algorithm** | Ed25519 support varies by provider and must be confirmed at decision time; ES256 is universally available and would need a verifier change | Broad | Provider-defined | Any |
| **Residency** | Region-bound; follows FD-02 | Follows FD-02 | Follows the hosting region | Follows the hosting region |
| **Latency / cost** | One network call per token (tokens are short-lived but issued often); low cost | Highest cost | Low | Lowest |
| **Audit** | Every signature logged by the KMS | Same | Provider-dependent | None at the key level |
| **Crypto-shred erasure (per-subject data keys)** | Supported via envelope encryption | Supported | Usually not | No |

## Recommendation

**(a) Cloud KMS, in the FD-02 region, for both token and package signing**, with a separate key per
purpose and per environment. Add envelope-encryption data keys for crypto-shred erasure (needed by
Phase G). Choose the algorithm at decision time: keep Ed25519 if the chosen KMS supports it; else
move to ES256. The verifier already supports a kid-addressed key *set*, so this is an overlap
rotation, not a flag day. **(b)** is reserved for C4 safeguarding keys if the safeguarding review
(EV-02) requires it. **(d)** is acceptable only for development and the synthetic pilot.

## What approval must include

1. The KMS provider and region (resolve with FD-02).
2. The key inventory: purpose, algorithm, rotation period, and who may administer each key.
3. Break-glass and key-compromise procedure, linked from [`INCIDENT_RESPONSE.md`](../../INCIDENT_RESPONSE.md).
4. Who holds production cloud credentials (an account-owner action; engineering does not create them).
