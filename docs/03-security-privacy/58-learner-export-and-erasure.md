# 58 · Learner Data Export, Erasure and the Retention Schedule (implementation)

| | |
|---|---|
| **Document ID** | 58 |
| **Owner** | Data Protection Officer (policy) · Engineering (implementation) |
| **Status** | Implemented in code; **retained set and every retention period are PENDING M-Gov approval** |
| **Last updated** | 2026-10-22 |
| **Related** | [14 Privacy](./14-privacy-model.md) §6 · [57 Retention schedule](./57-data-retention-schedule.md) · contract `packages/contracts/privacy.openapi.yaml` |

## Purpose

Records what the `contexts/privacy` bounded context does today for a learner's guardian: export,
erasure, and the retention dry-run. It states plainly what is kept after an erasure, so the DPO
and counsel can approve or change it. It does not set legal periods.

## 1. Who may act

- A guardian may export or erase only a learner the identity context records as theirs.
- Anyone else, an unknown ref, or an already-erased learner gets the same `404`, so the response
  never confirms that a ref names a real child.
- A learner token, or any other role, gets `403`.
- The retention dry-run is an operator control (`system`).

## 2. Stores covered

Each store holding learner data has one `LearnerDataPort` adapter. Every table in every schema must
be either covered or listed in `contexts/privacy/adapters/coverage.py` with a reason. A test
introspects the ORM metadata (and the live PostgreSQL catalog) and fails on any table that is in
neither list.

| Store | Covered |
| --- | --- |
| identity | `learner_account`, `consent_record`, `refresh_token`, `audit_event` |
| learning | `student_knowledge`, `objective_mastery`, `assessment_evidence`, `learning_outbox`, `ai_usage_ledger` (migration 0007), live in-process sessions |
| sync | in-process entity state whose key carries the `student:<ref>` component |
| AI usage ledger (SQLite dev default) | the process-local ledger used when there is no PostgreSQL; on PostgreSQL the ledger is `learning.ai_usage_ledger` |
| guardian portal | nothing stored; every view is derived on read |

Exempt with reasons: `identity.guardian_account` (a separate data subject),
`identity.rate_limit_bucket` (hashed network identifiers), `ops.kill_switch`, and the authored
curriculum tables.

## 3. Export

`GET /v1/privacy/learners/{studentRef}/export` returns one JSON bundle
(`taleem.learner-export/1`) with a section per store. Credential digests (the PIN hash and
refresh-token hashes) are withheld and listed as withheld. Sync "seen" event ids are opaque device
ids with no learner reference, so they cannot be attributed to a learner.

## 4. Erasure (two-step, irreversible)

1. `POST …/erasure-requests` erases nothing. It returns a confirmation token: an HMAC over the
   request id, the learner, the guardian, and an expiry (default 15 minutes). No server-side state
   is kept.
2. `POST …/erasure:confirm` with the token erases the stores in a fixed order: every
   non-identity store first, identity last. The learner-account deletion and the tombstone commit
   in one transaction. A verification sweep then re-scans every store, and the request fails
   loudly if anything still references the learner.

Before anything is touched, every store must report no blockers; otherwise the request is refused
with `503 ERASURE_BLOCKED` and nothing is erased.

### 4.1 What is retained — PENDING M-Gov approval

The retained set is configurable. Nothing it keeps carries the `student_ref`: both kept records are
keyed by a tombstone ref, `tomb_` plus a salted SHA-256 of the ref. A guardian who still holds the
ref can prove the erasure happened; no one can reverse the tombstone ref.

| Kept | Default fields | Setting |
| --- | --- | --- |
| Consent decisions | `consent_id`, `guardian_ref`, `action`, `scopes`, `policy_version`, `recorded_at`, `evidence.method`, `evidence.attestation` (IP and user-agent hashes dropped) | `TALEEM_PRIVACY_KEEP_CONSENT_EVIDENCE`, `TALEEM_PRIVACY_CONSENT_TOMBSTONE_FIELDS` |
| One erasure event (`identity.audit_event`, action `privacy.learner_erased`) | `tombstone_ref`, `guardian_ref`, `requested_at`, `confirmed_at`, `scope`, `retained` | `TALEEM_PRIVACY_KEEP_ERASURE_EVENT` |

Other settings: `TALEEM_PRIVACY_TOMBSTONE_SALT`, `TALEEM_PRIVACY_CONFIRMATION_KEY` (at least 32
bytes) and `TALEEM_PRIVACY_CONFIRMATION_TTL_S`. In production, erasure stays disabled (`503`) until a
confirmation key is set. Outside production, each process gets a random key.

### 4.2 Known limits

- **PostgreSQL:** migration 0002 makes `learning.assessment_evidence` append-only with a trigger
  that refuses every DELETE. Until a migration lets `learning.forbid_mutation()` admit a DELETE in
  a transaction that has run `SET LOCAL taleem.privacy_erasure = 'on'` (the adapter already sets
  it), erasure on PostgreSQL is **blocked** and fails closed. Export works.
- **Process-local stores:** the sync store, live sessions and (on SQLite only) the AI cost ledger are erased in the
  serving process only. Multi-instance erasure needs their planned durable tables.
- **Out of reach:** backups, device caches and processors (doc 57 §3, crypto-shredding) are not
  reached yet. An access token issued before the erasure stays valid until it expires, although
  the account behind it no longer exists.
- **Dev seed links:** the `TALEEM_GUARDIAN_LINKS` dev seed is configuration, not data. Production
  ignores it, and erasure does not rewrite it.

## 5. Retention schedule

Retention is set by `TALEEM_RETENTION_PERIODS`: a JSON object mapping a data class to seconds. The
classes are `learning_records`, `learning_events`, `security_audit`, `session_credentials` and
`ai_usage`.

- By default, every class is **not set, so purge is disabled**.
- Unknown classes and non-positive periods are refused at start-up.
- `GET /v1/privacy/retention:dry-run` reports, per class, what a configured period would purge.
  This phase never deletes.

## Change log

| Date | Change | Author |
| --- | --- | --- |
| 2026-10-22 | First implementation: guardian export, two-step erasure with tombstone, retention dry-run, cross-schema completeness test. | Engineering |
