# 41 · Coding Standards

| | |
|---|---|
| **Document ID** | 41 |
| **Owner** | Principal Engineer |
| **Status** | Draft (Phase 1) |
| **Last updated** | 2026-07-19 |
| **Related** | [08 System Architecture](../02-architecture/08-system-architecture.md) · [47 Folder Structure](./47-folder-structure.md) · [48 Repository Standards](./48-repository-standards.md) · [40 Testing](./40-testing-strategy.md) · [13 Security](../03-security-privacy/13-security-model.md) · [Authoring Brief §4](../_meta/authoring-brief.md) |

## Purpose

This document defines the **coding standards** that keep Taleem's codebase clean, safe, and evolvable at
enterprise quality: language conventions (TypeScript, Python), architecture-in-code (SOLID, Clean/
Hexagonal, DDD), and the safety/privacy/accessibility rules that are non-negotiable in code.

## Scope

In scope: language standards, architectural coding rules, and cross-cutting code mandates. Out of scope:
folder layout ([47](./47-folder-structure.md)), repo/PR process ([48](./48-repository-standards.md), [49](./49-development-workflow.md)),
and test detail ([40](./40-testing-strategy.md)).

---

## 1. Principles

1. **SOLID, Clean/Hexagonal, DDD, 12-Factor** — the architecture is expressed in code, not just docs
   ([08](../02-architecture/08-system-architecture.md), [Authoring Brief §4](../_meta/authoring-brief.md)).
2. **Readable like the surrounding code** — consistency over cleverness.
3. **Safety, privacy, accessibility are code rules**, enforced in lint/CI, not left to reviewers'
   memory ([15](../03-security-privacy/15-child-safety-framework.md), [14](../03-security-privacy/14-privacy-model.md), [16](../04-design/16-accessibility-standards.md)).
4. **The domain core is pure** — no framework/I/O imports in domain layers ([08 §2.3](../02-architecture/08-system-architecture.md)).

## 2. Language standards

| Stack | Standards |
|---|---|
| **TypeScript** | `strict` mode; no `any` (justified exceptions only); ESLint + Prettier; Server Components by default, minimal client JS ([04 NFR DATA-01](../01-product/04-non-functional-requirements.md)); tokens-only styling ([18](../04-design/18-design-tokens.md)). |
| **Python** | Type hints + mypy; ruff/black; async I/O; Pydantic for boundaries; no provider SDK calls outside the AI gateway ([FR-AIT-005](../01-product/03-functional-requirements.md)). |
| **SQL/migrations** | Parameterised queries only; forward-only, expand/contract migrations ([09 §10](../02-architecture/09-database-design.md)). |

## 3. Architecture in code

- **Hexagonal layering** per module: domain core (pure) → application (use cases, transactions, outbox)
  → adapters (FastAPI/SQLAlchemy/Redis/broker) ([08 §2.3](../02-architecture/08-system-architecture.md)).
- **No cross-context imports or cross-schema SQL** — enforced by fitness functions ([ADR-0002](../02-architecture/adr/ADR-0002-database-per-context.md)).
- **Dependency inversion** — depend on ports, not concretes; providers are swappable adapters
  (LLM gateway, notification, repositories).
- **Idempotent, retry-safe** critical-path writes ([10 §6](../02-architecture/10-api-design.md)).

## 4. Non-negotiable code mandates

| Mandate | Enforcement |
|---|---|
| No child PII/secrets in logs | Redaction + CI log-scan ([39](./39-logging.md)) |
| No direct LLM provider SDK calls in product code | Static analysis ([FR-AIT-005](../01-product/03-functional-requirements.md)) |
| Every route has an auth policy binding | CI fitness function ([12 §9](../03-security-privacy/12-authorization-model.md)) |
| No hardcoded strings (i18n) or raw design values | Lint ([04 NFR L10N-02](../01-product/04-non-functional-requirements.md), [18](../04-design/18-design-tokens.md)) |
| Input validation at boundaries | Schema-driven ([10 §11](../02-architecture/10-api-design.md), [13 §4](../03-security-privacy/13-security-model.md)) |
| Accessibility rules (labels, focus, targets) | Lint + axe ([16](../04-design/16-accessibility-standards.md)) |

## 5. Error handling & naming

- **Explicit errors**, mapped to the uniform API problem shape ([10 §4](../02-architecture/10-api-design.md)); never
  swallow exceptions; never leak internals.
- **Intention-revealing names**; domain vocabulary = canonical role/context names ([Authoring Brief §2/§5](../_meta/authoring-brief.md)).
- Small, focused functions; comments explain *why*, not *what*.

## 6. Risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R-1 | Boundary erosion (cross-context coupling) | Loses modularity | Fitness functions, review, per-schema grants. |
| R-2 | Provider SDK leak into product code | AI ungoverned | Static-analysis gate. |
| R-3 | PII/secret leakage | Privacy/security | Lint + redaction + scanning. |
| R-4 | Inconsistent style | Maintainability | Formatters/linters in CI. |

## Open questions

- **Monorepo tooling** for TS+Python shared standards ([48](./48-repository-standards.md)).
- **Fitness-function tooling** for architecture rules in both stacks.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial coding standards: TS/Python conventions, hexagonal architecture-in-code, non-negotiable safety/privacy/a11y code mandates, error/naming rules. | Principal Engineer |
