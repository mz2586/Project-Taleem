# ADR-0001 · Architecture style: modular monolith with carved-out services

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-19 |
| **Deciders** | Principal Software Architect, CTO, Head of Platform Engineering |
| **Related** | [08 System Architecture](../08-system-architecture.md) · [ADR-0002 Database-per-Context](./ADR-0002-database-per-context.md) · [Authoring Brief §4](../../_meta/authoring-brief.md) |

## Context

Project Taleem must serve up to **1,000,000 students** ([Authoring Brief §1](../../_meta/authoring-brief.md))
while, in Phase 1, being built by one-to-few teams at low cost and with boundaries that are still being
learned. Two failure modes threaten us: (a) premature microservices — paying distributed-systems tax
(14+ deployables, sagas everywhere, mandatory distributed tracing) before we have the teams or traffic,
and getting network boundaries *wrong* while they are expensive to move; and (b) a big-ball-of-mud
monolith with no internal boundaries that cannot later be decomposed. We need an architecture that is
cheap and fast now, correct about boundaries, and able to scale to 1M without a rewrite.

## Decision

Adopt a **modular monolith ("modulith")** with **strictly enforced bounded-context modules**, a
**message broker with the transactional outbox pattern** for asynchronous integration, and a **small
number of services carved out from day one for failure-isolation reasons (not scale)** — the **AI
Teacher orchestrator**, the **Realtime gateway**, and **Media/async workers**.

- Each of the 14 bounded contexts ([Authoring Brief §5](../../_meta/authoring-brief.md)) is a module
  with a hard facade, its own schema ([ADR-0002](./ADR-0002-database-per-context.md)), and published
  events; internally each is a hexagon (Clean/Hexagonal + DDD).
- Cross-context integration is **async events via outbox** by default; synchronous coupling is a
  justified exception.
- Modules are extracted to independent services only when a **concrete trigger** fires
  ([08 §9.5](../08-system-architecture.md)).

## Consequences

**Positive:** low operational surface and cost at low load; boundaries are compile-time (a wrong one is
a refactor, not a re-platform); in-process transactions where a use case spans modules; the outbox +
event contracts make boundaries "network-shaped" so extraction is containerise-and-deploy; scales
horizontally because compute is stateless ([08 §9](../08-system-architecture.md)).

**Negative / costs:** requires **discipline** to keep module boundaries from eroding (mitigated by
per-schema DB grants and CI architecture-fitness functions); a single deployable means a bad change can
affect multiple contexts until extraction (mitigated by canary + feature flags, [35 §4](../35-deployment-architecture.md)); developers must learn the outbox/idempotency pattern.

**Neutral:** three services exist from day one, so we operate a small (not zero) distributed system
immediately.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| **Full microservices from day one** | Distributed tax before teams/traffic justify it; high risk of wrong, expensive-to-move boundaries; costly at low load. |
| **Unstructured monolith** | Fast initially but boundaries erode; cannot decompose later; violates DDD/1M-scale goals. |
| **Serverless-first** | Cold starts and per-invocation limits fit the low-latency, long-lived-connection (WebSocket) and heavy-transcode profiles poorly; portability/residency harder. |

## Compliance & enforcement

- **CI architecture-fitness functions** assert no cross-module internal imports and no cross-schema
  access ([37 CI/CD](../../07-engineering/37-cicd-pipeline.md), [ADR-0002](./ADR-0002-database-per-context.md)).
- Extraction of a module requires a recorded trigger ([08 §9.5](../08-system-architecture.md)); a new
  always-on service requires a superseding ADR.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Accepted: modulith + outbox + three day-one carve-outs. | Principal Software Architect |
