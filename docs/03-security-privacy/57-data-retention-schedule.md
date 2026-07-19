# 57 · Data Retention & Deletion Schedule

| | |
|---|---|
| **Document ID** | 57 (Phase 1.5 remediation) |
| **Owner** | Data Protection Officer |
| **Status** | Draft — periods are planning assumptions, need legal sign-off |
| **Last updated** | 2026-07-19 |
| **Closes** | AR-H-20, AR-H-21 (and AR-C-24 in part) |
| **Related** | [14 Privacy](./14-privacy-model.md) · [39 Logging](../07-engineering/39-logging.md) · [56 BC/DR](../02-architecture/56-bcdr-plan.md) · [31 Analytics](../06-portals/31-analytics-platform.md) |

## Purpose

[14 §6](./14-privacy-model.md) described retention only qualitatively ("short", "a defined period"). This
provides concrete per-class periods, the legal basis, the enforcement mechanism, and the erasure design
across backups and processors.

## Scope

In scope: retention periods by data class, automated enforcement, crypto-shred erasure. Out of scope:
consent lifecycle ([14 §3](./14-privacy-model.md)).

---

## 1. Retention schedule (planning assumptions — legal sign-off required)

| Data class | Example | Retention (default) | Legal basis | Enforcement |
|---|---|---|---|---|
| **C4 Safeguarding** | Cases, disclosures | Per legal obligation (may be long); access-restricted throughout | Legal obligation | Partition + access control |
| **C3 Child PII** | Name, guardian phone | While enrolled + defined tail, then erase/anonymise | Consent/obligation | Crypto-shred on erasure |
| **C2 Learning records** | Attempts, grades, report cards | While enrolled + tail (credential value); then anonymise | Legitimate learning purpose | Partition drop + anonymise |
| **AI transcripts** | Tutoring turns | **Short** — e.g. 30 days for safety review, then auto-expire; distress-flagged turns follow C4 | Safety purpose | Time-partition drop |
| **Security/audit logs** | Auth, privileged actions | Per security policy, PII-minimised | Security obligation | WORM + lifecycle |
| **Analytics events** | Pseudonymous telemetry | Bounded; pseudonymous only | Legitimate interest | Warehouse TTL |
| **C1 Operational** | Device IDs, rate counters | Short (Redis TTL) | Operational | Native TTL |

Numbers are planning assumptions; the DPO + Counsel confirm each period and legal basis (DECISION
REQUIRED).

## 2. Automated enforcement

- **Retention-aligned partitioning** ([09 §7](../02-architecture/09-database-design.md)) makes expiry a
  partition **drop**, not a mass delete.
- Object-storage **lifecycle policies** expire media/renditions.
- A scheduled **retention job** verifies expiry and alerts on drift.

## 3. Erasure across everything (crypto-shredding)

Right-to-erasure must reach primary stores, caches, search, warehouse, **backups**, and device caches.
Mechanism:

- Each erasable subject's PII is encrypted under a **per-subject data key** in KMS.
- **Erasure = destroy the key** → data (including in immutable backups) is unrecoverable without editing
  snapshots.
- An **erasure-orchestration saga** fans out to every store holding `student_ref` (all shards, search,
  warehouse, object storage) with per-target confirmation and a reconciliation sweep for orphans; device
  caches invalidate on next sync ([33 Offline](../02-architecture/33-offline-architecture.md)).
- LLM-provider copies are prevented by **zero-retention inference** ([24](../05-education/24-ai-teacher-specification.md), DECISION REQUIRED),
  not erased after the fact.

## Open questions

- Confirmed numeric periods + legal basis per class (DECISION REQUIRED, legal).
- Safeguarding retention vs. erasure-right tension (legal).
- Backup retention window after which residual crypto-shredded ciphertext ages out.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial retention & deletion schedule (Phase 1.5): per-class periods, automated partition-drop enforcement, crypto-shred erasure across backups/processors/devices. | DPO |
