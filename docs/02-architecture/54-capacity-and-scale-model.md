# 54 · Capacity & Scale Model

| | |
|---|---|
| **Document ID** | 54 (Phase 1.5 remediation) |
| **Owner** | Principal Software Architect / SRE Lead |
| **Status** | Draft — planning assumptions, needs infra sizing sign-off |
| **Last updated** | 2026-07-19 |
| **Closes** | AR-C-11, AR-H-25, AR-H-26, AR-H-27, AR-H-32 (see [ARCHITECTURE_REVIEW.md](../../ARCHITECTURE_REVIEW.md)) |
| **Related** | [08 System Architecture](./08-system-architecture.md) · [09 Database](./09-database-design.md) · [35 Deployment](./35-deployment-architecture.md) · [55 Cost Model](../08-delivery/55-cost-model.md) · [56 BC/DR](./56-bcdr-plan.md) |

## Purpose

This document quantifies "1,000,000 students" into a concrete capacity model — the numbers every scaling
claim in the blueprint must trace to — and commits the **sharding strategy** that removes the single
biggest scaling ceiling (a single Postgres write primary). It replaces the deferred "capacity model
documented" placeholders in [08 §9](./08-system-architecture.md) and [35 §5](./35-deployment-architecture.md).

## Scope

In scope: the enrolled-vs-concurrent model, derived load numbers, per-tier sizing, the sharding plan, and
the synchronized-load (bell-time) strategy. Out of scope: cost (owned by [55](../08-delivery/55-cost-model.md))
and DR (owned by [56](./56-bcdr-plan.md)). **All numbers below are planning assumptions** to be validated
by staged load tests; they exist so sizing is falsifiable, not to assert measured fact.

---

## 1. Enrolled vs. concurrent (the disambiguation)

The authoring brief's "1,000,000 concurrent-capable enrolled students" conflated two very different
numbers. We fix definitions:

| Metric | Planning value | Basis |
|---|---|---|
| **Enrolled** | 1,000,000 | The scale target |
| **Daily active (DAU)** | ~40% = 400,000 | Assumption; school-day cadence |
| **Peak concurrent** | ~25% of DAU in the evening bell window = **~100,000–150,000** | Load-shedding concentrates study into evening power windows; NOT a flat 10% of enrolled |
| **Bell-time arrival burst** | up to 100k logins within ~15 min | Synchronized timetables |

Design target: **150,000 peak concurrent** with headroom to 250k. This is the number the tiers below are
sized against.

## 2. Derived load (per second, at 150k concurrent)

| Load | Estimate | Notes |
|---|---|---|
| Read RPS | ~75,000 | ~0.5 req/s per concurrent user (browse, resume, poll) |
| Write TPS | ~8,000–15,000 | progress, attempts, transcripts, outbox, delivery logs (write-amplified) |
| WebSocket connections | ~150,000 concurrent | ≈ peak concurrent |
| Domain events/sec | ~20,000 | lesson/AI/attempt/notification events |
| AI turns/day | ~2–4M | DAU × avg turns; drives cost ([55](../08-delivery/55-cost-model.md)) |
| Storage growth | ~1–3 GB/student/year aggregate hot; transcripts dominate | retention-bounded ([57](../03-security-privacy/57-data-retention-schedule.md)) |

## 3. Tier sizing (planning)

| Tier | Strategy | Sizing target |
|---|---|---|
| **Core API** | Stateless, HPA on in-flight requests | ~75k RPS ÷ ~500 RPS/pod ≈ 150 pods peak |
| **PostgreSQL** | **Sharded** (see §4) + read replicas | Reads to replicas; writes split across shards |
| **Realtime gateway** | Connection-dense gateway (Go/Elixir evaluated over Python) | ~25k conns/pod → ~6–10 pods; L4 passthrough LB; per-conn memory budget documented |
| **Realtime backplane** | **Durable, partitioned** (broker, keyed per connection/topic) — replaces Redis Pub/Sub | Each pod consumes only its partition, not all messages |
| **Broker/event bus** | Log-based (Kafka/Redpanda) — feeds analytics directly | ~20k events/sec with retention |
| **Redis** | **Split by workload**: cache (LRU cluster) · sessions+rate-limit (persistent) · streams/presence | Removes single-Redis blast radius |
| **Meilisearch** | Low-churn content index; PII/admin search re-evaluated vs OpenSearch at 1M docs | Index RAM budgeted; live PDP filter on child-PII search |
| **Warehouse** | Broker → ClickHouse **directly** (delete the OLTP `analytics_ingest` hop) | Analytics never competes with OLTP |

## 4. Sharding strategy (removes the write ceiling)

**Decision:** shard the high-volume, per-student contexts — **Lesson progress, Assessment attempts, AI
transcripts, delivery logs, event/outbox** — by a hash of `student_ref` (co-locating a child's data),
across N Postgres shards; keep low-volume contexts (Curriculum, Platform/Admin) unsharded. Recorded as an
ADR (proposed): app-level shard routing in the persistence adapter, or Citus.

| Item | Decision |
|---|---|
| Shard key | `hash(student_ref)` (a child's records co-locate; avoids `school_id` skew if tenants are few/large) |
| Shard count | Start 8, sized so per-shard write-TPS ≤ ~30% of a single primary's ceiling; documented resharding runbook (split by consistent-hash range) |
| Cross-shard queries | Discouraged; per-student flows are single-shard; cross-shard analytics go via the warehouse, not live joins |
| Outbox relay | **CDC/logical-decoding** (Debezium/`pgoutput`) per shard, batched mark-published — replaces the single polling relay |
| Erasure | Crypto-shredding per `student_ref` key ([57](../03-security-privacy/57-data-retention-schedule.md)) makes cross-shard + backup erasure tractable |

## 5. Synchronized load (bell-time thundering herd)

Queue-leveling does not help the *synchronous* login/lesson-open/WS-connect storm at bell times.
Mitigations:

- **Scheduled pre-scaling** (KEDA cron / scheduled HPA) warms Core API, realtime, and caches *before*
  each timetable window.
- **Pre-warm read-model caches** (timetable, roster) ahead of the window.
- **Request coalescing / singleflight** on hot cache keys to prevent stampede to the primary.
- Model the arrival curve per region/timezone; size to the burst, not the average.

## 6. Load-test plan (staged)

| Milestone | Target | Tests |
|---|---|---|
| L1 | 10k concurrent | Baseline, correctness under load |
| L2 | 100k concurrent | Bell-time burst, sync/offline flush, WS density |
| L3 | 150k+ concurrent | Soak (sustained), spike (burst), breakpoint (find the ceiling) |
| L4 | 1M enrolled dataset | Migration lock/duration on realistic skew; shard rebalance; erasure fan-out |

## Open questions

- Real peak-concurrency ratio (validate the 25%-of-DAU evening assumption with pilot telemetry).
- Shard count and rebalance thresholds under real write distribution.
- Realtime gateway language/runtime decision (connection density vs. team skills).
- Whether live-class realtime belongs in the 3G/low-power reference budget at all.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial capacity & scale model (Phase 1.5): enrolled-vs-concurrent disambiguation, derived load, tier sizing, sharding strategy, bell-time pre-scaling, staged load-test plan. | Principal Architect / SRE |
