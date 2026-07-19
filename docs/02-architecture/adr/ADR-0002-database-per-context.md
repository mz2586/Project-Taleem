# ADR-0002 · Database-per-context (schema-per-context in Phase 1)

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-19 |
| **Deciders** | Principal Software Architect, Head of Data, CISO |
| **Related** | [08 System Architecture](../08-system-architecture.md) · [09 Database Design](../09-database-design.md) · [ADR-0001 Architecture Style](./ADR-0001-architecture-style.md) · [14 Privacy](../../03-security-privacy/14-privacy-model.md) |

## Context

The modulith ([ADR-0001](./ADR-0001-architecture-style.md)) only stays modular if data ownership is
enforced, not merely encouraged. If contexts share tables or reach across boundaries with SQL/foreign
keys, boundaries erode, extraction becomes a rewrite, and a breach in one context exposes all child
data. We also concentrate child PII to shrink the breach and erasure surface ([14 Privacy](../../03-security-privacy/14-privacy-model.md)).

## Decision

Each bounded context **owns its own database schema and is the sole writer of its data**. In Phase 1
this is **separate schemas in one PostgreSQL cluster**, each with its **own DB role and grants** and
**no cross-schema foreign keys**. A context reads another context's data **only** via that context's
API or via subscribed events projected into its own read model. Child/guardian **PII is concentrated in
the Identity context**; other contexts hold opaque `student_ref`/`guardian_ref` and only explicitly
granted attributes.

## Consequences

**Positive:** boundaries are enforced by the database (grants), not convention; extraction to a
separate database is a config change, not a re-model; the breach surface shrinks (PII concentrated);
right-to-erasure becomes a targeted operation ([14 §6](../../03-security-privacy/14-privacy-model.md));
tenancy isolation is reinforced by RLS ([09 §6](../09-database-design.md)).

**Negative / costs:** no cross-context JOINs — some read models must be **projected** from events
(eventual consistency, extra storage); cross-context integrity is maintained by events + idempotent
consumers, not FK constraints, requiring discipline and monitoring; more schemas to migrate/own.

**Neutral:** one physical cluster in Phase 1 keeps ops simple while preserving the logical boundary.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| **Single shared schema** | Boundaries erode instantly; cannot extract; blast radius = all data. |
| **Database-per-context (separate clusters) now** | Operational cost/complexity unjustified at Phase 1 scale; schema-per-context gives the same logical guarantee cheaper. |
| **Shared tables with app-level discipline** | Not enforceable; a single query bug crosses the boundary. |

## Compliance & enforcement

- **Per-schema DB roles/grants** prevent cross-schema access at the database layer.
- **CI fitness function** fails a build that issues SQL against another context's schema or adds a
  cross-context FK ([37 CI/CD](../../07-engineering/37-cicd-pipeline.md)).
- **Row-level security** enforces the School tenancy boundary as defence in depth ([09 §6](../09-database-design.md)).

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Accepted: schema-per-context with per-schema grants, no cross-context FKs, PII concentrated in Identity. | Principal Architect / Head of Data |
