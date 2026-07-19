# 45 · Milestone Plan

| | |
|---|---|
| **Document ID** | 45 |
| **Owner** | Program Director |
| **Status** | Draft (Phase 1) |
| **Last updated** | 2026-07-19 |
| **Related** | [44 Roadmap](./44-roadmap.md) · [46 Backlog](./46-project-backlog.md) · [43 Risk Register](./43-risk-register.md) · [02 PRD](../01-product/02-prd.md) · [50 Definition of Done](../07-engineering/50-definition-of-done.md) |

## Purpose

This document breaks the [44 Roadmap](./44-roadmap.md) into **milestones with concrete exit criteria**,
so progress is measurable and each milestone's "done" is unambiguous. Milestones are **relative and
sequence-based** (M0, M1, …); calendar dates are assigned when resourcing is confirmed.

## Scope

In scope: milestones, their deliverables, and exit criteria, mapped to roadmap phases. Out of scope:
individual stories ([46 Backlog](./46-project-backlog.md)) and dated scheduling (pending resourcing).

---

## 1. Principles

1. **Every milestone has a binary exit criterion** — met or not, no partial credit.
2. **Non-negotiables are exit criteria** (safety/reach/a11y/privacy), per [50 DoD](../07-engineering/50-definition-of-done.md).
3. **Milestones ladder to the north-star** ([01 Vision §6](../00-overview/01-vision.md)).

## 2. Milestones

```mermaid
graph LR
    M0[M0 Foundation] --> M1[M1 Walking skeleton]
    M1 --> M2[M2 Learn loop]
    M2 --> M3[M3 Assess + report]
    M3 --> M4[M4 Offline + safety]
    M4 --> M5[M5 MVP pilot]
    M5 --> M6[M6 v1 full school]
    M6 --> M7[M7 Scale hardening]
```

| Milestone | Deliverable | Exit criteria |
|---|---|---|
| **M0 · Foundation** (current) | 50-doc blueprint + ADRs | All docs Approved; **CI green** (lint/link/mermaid); non-negotiables specified ([44](./44-roadmap.md) Phase 1). |
| **M1 · Walking skeleton** | End-to-end thin slice: auth → one lesson → submit, deployed | Core-path request flows through all layers in staging; observability live ([38](../07-engineering/38-monitoring.md)). |
| **M2 · Learn loop** | Lesson runtime + AI Teacher (guardrailed) for KG–G5 sample | A child completes a guardrailed lesson + AI Q&A; safety guardrails + transcripts working ([22](../05-education/22-lesson-engine.md), [24](../05-education/24-ai-teacher-specification.md)). |
| **M3 · Assess + report** | Formative + exam, auto-grade, gradebook, report card v1 | Attempt→auto-grade→report card, honest & version-pinned ([23](../05-education/23-assessment-engine.md), [29](../06-portals/29-reporting-system.md)); north-star event fires. |
| **M4 · Offline + safety** | Offline day-pack + sync; safety spine (moderation, triage) | Offline E2E + idempotent sync green; all AI/media moderated; flags triaged within SLA ([33](../02-architecture/33-offline-architecture.md), [15](../03-security-privacy/15-child-safety-framework.md)). |
| **M5 · MVP pilot** | Thin complete school for a pilot cohort | **All MVP release gates green** ([02 §10](../01-product/02-prd.md)); pilot cohort learns end-to-end on reference baseline. |
| **M6 · v1 full school** | KG–G10, human grading + promotion, portals, student life | v1 release gates green; full loop incl. human grading + promotion ([02 §4.2](../01-product/02-prd.md)). |
| **M7 · Scale hardening** | Load-validated toward 1M | Core-path SLOs held under load; no un-mitigated ceilings ([04 NFR SCAL](../01-product/04-non-functional-requirements.md)). |

## 3. Tracking

- Each milestone's exit criteria map to backlog epics ([46](./46-project-backlog.md)) and are gated by
  the [DoD](../07-engineering/50-definition-of-done.md).
- Risks ([43](./43-risk-register.md)) are burned down per milestone; a blocking safety/privacy risk halts
  the milestone.

## Open questions

- **Calendar dates** — assigned once team size/funding is confirmed.
- **Pilot cohort** definition ([02 PRD open Qs](../01-product/02-prd.md)).
- **M-level parallelism** — which milestones can overlap safely.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial milestone plan: M0–M7 with binary exit criteria mapped to roadmap phases and the DoD. | Program Director |
