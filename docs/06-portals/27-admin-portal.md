# 27 · Admin Portal Specification

| | |
|---|---|
| **Document ID** | 27 |
| **Owner** | Product Manager — Operations & Admin |
| **Status** | Draft (Phase 1) |
| **Last updated** | 2026-07-19 |
| **Related** | [07 IA](../01-product/07-information-architecture.md) · [20 Navigation](../04-design/20-navigation-structure.md) · [12 Authorization](../03-security-privacy/12-authorization-model.md) · [21 Curriculum](../05-education/21-curriculum-engine.md) · [15 Child Safety](../03-security-privacy/15-child-safety-framework.md) · [13 Security](../03-security-privacy/13-security-model.md) |

## Purpose

This document specifies the **Admin consoles** — the **School Admin**, **Platform Admin**, and (by
reference) **Trust & Safety** and **Curriculum Authoring** surfaces that run and protect the school.
These are desktop, role-restricted, audited surfaces distinct from the learner apps.

## Scope

In scope: School Admin and Platform Admin capabilities and structure; pointers to the Safety and
Authoring consoles (owned by [15](../03-security-privacy/15-child-safety-framework.md) and
[21](../05-education/21-curriculum-engine.md)). Out of scope: authorization internals ([12](../03-security-privacy/12-authorization-model.md))
and the specific service specs each console drives.

---

## 1. Consoles & roles

| Console | Role ([Authoring Brief §2](../_meta/authoring-brief.md)) | Focus |
|---|---|---|
| **School Admin Console** | School Admin | Enrolment, cohorts, timetables, mentor assignment for a **school/region** |
| **Platform Admin Console** | Platform Admin | Curriculum publishing, config/flags, users & roles, audit, operations |
| **Trust & Safety Console** | Safety Officer | Triage, cases, escalations ([15 §5](../03-security-privacy/15-child-safety-framework.md)) |
| **Curriculum Authoring** | Curriculum Architect | Author/map curriculum ([21 §6](../05-education/21-curriculum-engine.md)) |

## 2. School Admin Console

| Capability | FR |
|---|---|
| Enrol/place Students; assisted/institutional enrolment | [FR-IDN-001](../01-product/03-functional-requirements.md), [11 §3.2](../03-security-privacy/11-authentication-strategy.md) |
| Manage **cohorts** and **timetables** | [FR-ENR-001/002](../01-product/03-functional-requirements.md) |
| Assign **Mentors** to cohorts | [FR-ENR-004](../01-product/03-functional-requirements.md) |
| Cohort transfer/re-placement (audited) | [FR-ENR-006](../01-product/03-functional-requirements.md) |
| School-scoped reports | [FR-ANL-003](../01-product/03-functional-requirements.md), [29](./29-reporting-system.md) |

**Structure:** Enrolment · Cohorts · Timetables · Mentors · Reports ([20 §5](../04-design/20-navigation-structure.md)).
Strictly **tenant-scoped** — a School Admin sees only their school ([12 §4](../03-security-privacy/12-authorization-model.md)).

## 3. Platform Admin Console

| Capability | FR |
|---|---|
| Publish **curriculum versions** (gated, reversible, audited) | [FR-ADM-002](../01-product/03-functional-requirements.md), [21 §5](../05-education/21-curriculum-engine.md) |
| **Feature flags** & config (per cohort/school) | [FR-ADM-001](../01-product/03-functional-requirements.md) |
| Users & roles administration | [12](../03-security-privacy/12-authorization-model.md) |
| **Audit** visibility over privileged actions | [FR-ADM-003](../01-product/03-functional-requirements.md) |
| Operations / maintenance modes | [FR-ADM-004](../01-product/03-functional-requirements.md) |

**Structure:** Curriculum Publishing · Flags/Config · Users & Roles · Audit · Operations.

## 4. Cross-cutting admin rules

- **Least privilege + JIT elevation** for privileged/cross-tenant actions ([12 §7](../03-security-privacy/12-authorization-model.md), [13 §7](../03-security-privacy/13-security-model.md)).
- **MFA mandatory** for all admin roles; Safety Officers hardware-key + dual-control for C4 data
  ([11 §11](../03-security-privacy/11-authentication-strategy.md)).
- **Every privileged action is audited** immutably ([13 §9](../03-security-privacy/13-security-model.md)).
- **No superuser** — even Platform Admin cannot read safeguarding C4 data without the Safety path
  ([15 §6](../03-security-privacy/15-child-safety-framework.md)).
- Desktop, sidebar + breadcrumb navigation, still WCAG 2.2 AA ([16](../04-design/16-accessibility-standards.md)).

## 5. Risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R-1 | Over-broad admin privilege | Large blast radius | Least privilege, JIT, dual-control ([12](../03-security-privacy/12-authorization-model.md)). |
| R-2 | Cross-tenant leakage | Privacy breach | Tenant scoping + RLS + audited cross-tenant paths. |
| R-3 | Bad curriculum publish | Wrong content to children | Gated, reviewed, reversible publish ([21 §5](../05-education/21-curriculum-engine.md)). |
| R-4 | Unaudited privileged action | No accountability | Immutable audit of all privileged actions. |

## Open questions

- **Cross-tenant analytics** for Platform Admin without PII access ([31 Analytics](./31-analytics-platform.md)).
- **Institutional enrolment** admin flow depth for NGO/camp cohorts ([11 §3.2](../03-security-privacy/11-authentication-strategy.md)).
- **Delegated School Admin** sub-roles at scale.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial Admin consoles spec: School Admin + Platform Admin capabilities/structure, cross-cutting least-privilege/MFA/audit rules, pointers to Safety & Authoring consoles. | PM — Operations & Admin |
