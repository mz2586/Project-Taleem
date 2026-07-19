# 55 · Cost Model & FinOps

| | |
|---|---|
| **Document ID** | 55 (Phase 1.5 remediation) |
| **Owner** | CFO / Head of Platform Engineering |
| **Status** | Draft — planning assumptions, needs pricing validation |
| **Last updated** | 2026-07-19 |
| **Closes** | AR-C-12, AR-H-29, AR-H-31 |
| **Related** | [54 Capacity Model](../02-architecture/54-capacity-and-scale-model.md) · [24 AI Teacher](../05-education/24-ai-teacher-specification.md) · [30 Notifications](../06-portals/30-notification-system.md) · [01 Vision](../00-overview/01-vision.md) |

## Purpose

The blueprint claimed "marginal cost approaching zero" while leaving the dominant variable cost (LLM
inference) an open question. For a sponsorship-funded platform, cost-per-student is the existential unit
economic. This document models it and sets **hard cost constraints** — especially on AI — with a spend
circuit-breaker.

## Scope

In scope: per-student cost envelope (AI, infra, media, SMS), AI tier-mix + caching assumptions, spend
guardrails. Out of scope: fundraising strategy. **All figures are planning assumptions** to be validated
against real provider pricing and pilot telemetry.

---

## 1. Vision language correction

[01 Vision §2](../00-overview/01-vision.md) "marginal cost approaching zero" is corrected to **"bounded
and sponsorship-viable marginal cost."** AI inference is a real, non-zero variable cost that must be
capped by design.

## 2. Per-student monthly envelope (planning assumption)

| Component | Driver | Cost lever |
|---|---|---|
| **AI Teacher** | Turns/student/month × tokens × tier price | Tier mix + cache hit rate (the primary lever) |
| **Infra (compute/DB/realtime/warehouse)** | Concurrency + storage | Autoscale, sharding, elastic scale-down |
| **Media/storage** | Assets + renditions + report cards | Optimisation + lifecycle tiering |
| **Messaging (SMS/WA)** | OTP + transactional + safety | Provider routing + spend cap |

A **hard per-student AI budget** is set as a design constraint on the AI Teacher service; the service
degrades to cached/hint content when a student's budget is exhausted, never silently overspends.

## 3. AI cost control (the make-or-break lever)

| Control | Target (planning assumption) |
|---|---|
| **Tier mix** | ≥ 85% Haiku, ~13% Sonnet, < 2% Opus (Opus only for hard explanations) |
| **RAG-chunk cache** | High hit rate on repeated curriculum retrieval |
| **Identical-prompt cache** | Formative-feedback responses cached and reused |
| **Per-student cap** | Monthly token ceiling enforced in the gateway `token_cost_ledger` |
| **Safety exception** | Distress-adjacent turns route to the strongest tier regardless of cost ([24](../05-education/24-ai-teacher-specification.md)) — safety never yields to cost |

## 4. Messaging cost & fraud guardrails

- **Aggregate spend circuit-breaker** — auto-throttle/halt on a cost-per-window threshold (defends
  SMS-pumping / toll fraud, AR-H-31).
- **Per-prefix allow-listing** and artificially-inflated-traffic detection with the provider.
- A **monthly SMS cost envelope** with alerting.

## 5. FinOps guardrails

- **Marginal-cost-per-WAL** is a guardrail metric ([31 Analytics §3](../06-portals/31-analytics-platform.md));
  alert on regression.
- Utilisation dashboards; no idle over-provisioning ([04 NFR COST-03](../01-product/04-non-functional-requirements.md)).
- Storage lifecycle policies bound media/warehouse cost.
- The cost model is reviewed against actuals each cycle and drives the sponsorship ask.

## Open questions

- Real per-token provider pricing and negotiated rates (zero-retention endpoints may price differently).
- Achievable cache hit rates from pilot data.
- Infra unit economics per concurrent user once the capacity model is load-validated ([54](../02-architecture/54-capacity-and-scale-model.md)).
- The sponsorship-viable ceiling per student (business).

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial cost model (Phase 1.5): per-student envelope, AI tier-mix + caching targets, per-student AI cap with safety exception, SMS spend circuit-breaker, FinOps guardrails; corrected Vision cost language. | CFO / Head of Platform Eng |
