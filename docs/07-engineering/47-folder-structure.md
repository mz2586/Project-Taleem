# 47 · Folder Structure

| | |
|---|---|
| **Document ID** | 47 |
| **Owner** | Principal Engineer |
| **Status** | Draft (Phase 1) |
| **Last updated** | 2026-07-19 |
| **Related** | [08 System Architecture](../02-architecture/08-system-architecture.md) · [41 Coding Standards](./41-coding-standards.md) · [48 Repository Standards](./48-repository-standards.md) · [ADR-0002 DB-per-Context](../02-architecture/adr/ADR-0002-database-per-context.md) |

## Purpose

This document defines the **repository/folder structure** for Taleem's code (Phase 1+), so the
modulith's bounded-context boundaries and hexagonal layering are visible in the file tree and enforceable
in CI. Structure mirrors architecture ([08](../02-architecture/08-system-architecture.md)).

## Scope

In scope: proposed monorepo layout, per-context module layout, and shared/infra placement. Out of scope:
the current docs-only tree (see the [README](../../README.md) layout) and coding conventions ([41](./41-coding-standards.md)).
This is the **target structure for when code begins** ([02 PRD phase gate](../01-product/02-prd.md)).

---

## 1. Principles

1. **Structure mirrors bounded contexts** — each context is a self-contained module ([08 §5](../02-architecture/08-system-architecture.md)).
2. **Hexagonal layers are folders** — domain/application/adapters are visible and dependency-checked
   ([08 §2.3](../02-architecture/08-system-architecture.md)).
3. **No cross-context reach** — the tree makes a cross-context import obvious and CI-blockable ([ADR-0002](../02-architecture/adr/ADR-0002-database-per-context.md)).
4. **Frontend and backend co-located** in a monorepo with shared contracts.

## 2. Top-level (target)

```text
taleem/
├── docs/                      # this blueprint (current)
├── apps/
│   ├── web/                   # Next.js PWA (student/guardian/portals)
│   └── ...                    # (future) admin surfaces if split
├── services/
│   ├── core-api/              # FastAPI modulith (14 context modules)
│   ├── ai-teacher/            # AI Teacher orchestrator (carved out)
│   ├── realtime-gateway/      # WebSocket service
│   └── media/                 # Media + transcode workers
├── packages/
│   ├── contracts/             # OpenAPI specs + event schemas (shared)
│   ├── ui/                    # design-system component library (19)
│   └── config/                # shared lint/ts/tokens config (18)
├── infra/                     # Terraform IaC (36)
└── .github/workflows/         # CI (37)
```

## 3. Per-context module (core-api)

```text
services/core-api/src/contexts/<context>/
├── domain/          # aggregates, entities, value objects, domain events (pure)
├── application/     # use cases, commands/queries, transactions, outbox writes
├── adapters/
│   ├── inbound/     # REST controllers, event consumers
│   └── outbound/    # repositories, event publisher, ports impl
└── module.py        # facade wiring the hexagon
```

Contexts: `identity`, `enrolment`, `curriculum`, `lesson`, `assessment`, `grading`, `engagement`,
`trust_safety`, `search`, `analytics`, `payments`, `platform_admin` ([08 §5](../02-architecture/08-system-architecture.md)).
(`ai_teacher`, `media`, realtime are separate services, [08 §2.2](../02-architecture/08-system-architecture.md).)

## 4. Enforcement

- **Fitness functions** assert domain purity (no framework imports), no cross-context imports, and no
  cross-schema SQL ([41 §3](./41-coding-standards.md), [ADR-0002](../02-architecture/adr/ADR-0002-database-per-context.md)).
- **Contracts package** is the single home for OpenAPI/event schemas ([10](../02-architecture/10-api-design.md)).
- Extraction of a context to its own service moves a folder, not a rewrite ([08 §9.5](../02-architecture/08-system-architecture.md)).

## Open questions

- **Monorepo tool** (Nx/Turborepo/uv workspaces) for TS+Python ([48](./48-repository-standards.md)).
- **Whether portals split** into separate apps or stay one PWA with route groups.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial folder structure: target monorepo layout, per-context hexagonal module layout, CI enforcement of boundaries. | Principal Engineer |
