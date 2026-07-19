# 56 · Business Continuity & Disaster Recovery Plan

| | |
|---|---|
| **Document ID** | 56 (Phase 1.5 remediation) |
| **Owner** | Head of Platform Engineering / SRE Lead |
| **Status** | Draft — DR region is DECISION REQUIRED (tied to residency) |
| **Last updated** | 2026-07-19 |
| **Closes** | AR-C-13, AR-H-34 |
| **Related** | [35 Deployment](./35-deployment-architecture.md) · [36 Infrastructure](./36-infrastructure-architecture.md) · [09 Database](./09-database-design.md) · [54 Capacity](./54-capacity-and-scale-model.md) · [14 Privacy](../03-security-privacy/14-privacy-model.md) |

## Purpose

The blueprint asserted RPO ≤5m / RTO ≤30m against a single-region topology that cannot honor them, with
no tested backup/restore — despite report-card and attempt data being "sacrosanct." This plan makes the
DR posture honest and testable, and separates the survivable case (AZ loss) from the unsurvivable one
(region loss).

## Scope

In scope: RPO/RTO by failure class, backup/PITR + crypto-shred, DR region, failover runbook, and
mandatory restore drills. Out of scope: routine deploy/rollback ([35 §4](./35-deployment-architecture.md)).

---

## 1. Honest RPO/RTO by failure class

| Failure | RPO (target) | RTO (target) | Mechanism |
|---|---|---|---|
| **Single AZ loss** | ≤ 5 min | ≤ 30 min | Multi-AZ managed Postgres auto-failover; stateless compute reschedules |
| **Region loss** | ≤ 15 min | ≤ 4 h (initial) → improve | **Warm cross-region replica** (streaming replication) + failover runbook |
| **Data corruption / bad migration** | to last good PITR point | hours (scale-dependent) | PITR restore + timed rehearsal (§4) |

The original single-region "≤30 min for region loss" claim is withdrawn as unachievable; a multi-TB
restore is hours, and a single region has no failover target. **A DR region is required.**

## 2. Backups

- Continuous WAL archiving + periodic snapshots; **PITR** across all shards ([09 §10](./09-database-design.md)).
- Encrypted, region-redundant object storage; **crypto-shreddable** (per-subject keys) so right-to-erasure
  reaches backups without editing snapshots ([57 Retention](../03-security-privacy/57-data-retention-schedule.md)).
- Backups of the immutable audit log and safeguarding (C4) zone with their access controls preserved.

## 3. DR region & residency dependency

The DR region choice is **coupled to the residency decision** (D-01): if Pakistani law mandates
in-country data, the DR target must also comply. This is DECISION REQUIRED (infra + legal) and is a
Phase-2 blocker ([RISK_REMEDIATION_PLAN.md](../../RISK_REMEDIATION_PLAN.md)).

## 4. Mandatory restore drills (the key change)

> A backup you have never restored is not a backup.

- **Timed, production-scale restore drill** on a representative dataset — proves RTO empirically, not by
  assertion. Added to the testing strategy as a readiness gate ([40 Testing](../07-engineering/40-testing-strategy.md)).
- **Region-failover game-day** validates the failover runbook.
- **Distribution-faithful data** (realistic skew/cardinality) used for restore and migration rehearsals,
  since uniform synthetic data hides lock/duration surprises (AR-M migration realism).

## 5. Continuity for offline learners

A deploy or regional incident must not disrupt offline learners: backward-compatible APIs + the offline
queue tolerate N-version skew ([33 Offline](./33-offline-architecture.md)); learners downloaded content
keeps working through an incident.

## Open questions

- DR region selection (DECISION REQUIRED, residency-coupled).
- Achievable region-loss RTO after the first drills.
- Cross-region replication cost vs. RPO trade-off ([55 Cost](../08-delivery/55-cost-model.md)).

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial BC/DR plan (Phase 1.5): honest RPO/RTO by AZ-vs-region, PITR + crypto-shred backups, DR-region dependency, mandatory timed restore drills, offline-learner continuity. | Head of Platform Eng / SRE |
