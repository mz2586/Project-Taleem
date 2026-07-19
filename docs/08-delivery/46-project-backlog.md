# 46 · Project Backlog

| | |
|---|---|
| **Document ID** | 46 |
| **Owner** | Staff Product Manager / Program Director |
| **Status** | Draft (Phase 1) |
| **Last updated** | 2026-07-19 |
| **Related** | [02 PRD](../01-product/02-prd.md) · [03 FR](../01-product/03-functional-requirements.md) · [44 Roadmap](./44-roadmap.md) · [45 Milestone Plan](./45-milestone-plan.md) · [50 Definition of Done](../07-engineering/50-definition-of-done.md) |

## Purpose

This document is the **seed project backlog** — the initial epics (`EP-NN`) that decompose the PRD
feature spine ([02 §5](../01-product/02-prd.md)) and functional requirements ([03](../01-product/03-functional-requirements.md))
into deliverable work, mapped to milestones ([45](./45-milestone-plan.md)). It is the source of stories
(`ST-NNN`) that the development workflow pulls from ([49](../07-engineering/49-development-workflow.md)).

## Scope

In scope: the epic-level backlog with traceability to FRs and milestones, and the story-writing
convention. Out of scope: fully decomposed stories (created as work begins) and sprint planning. This is
the **Phase-1 seed**; the living backlog will exceed it.

---

## 1. Backlog principles

1. **Traceable** — every epic maps to FR(s) ([03](../01-product/03-functional-requirements.md)) and a
   milestone ([45](./45-milestone-plan.md)); every story to an epic.
2. **MVP-first** — "Must" capabilities ([02 §9.1](../01-product/02-prd.md)) are the earliest epics.
3. **Safety/reach/a11y are acceptance criteria on every story**, per the [DoD](../07-engineering/50-definition-of-done.md).
4. **Thin vertical slices** — deliver end-to-end value, not horizontal layers.

## 2. Epics (seed)

| Epic | Title | Contexts / FR prefix | Milestone | Release |
|---|---|---|---|---|
| **EP-01** | Identity, guardian anchor & consent | Identity `FR-IDN` | M1 | MVP |
| **EP-02** | Child sign-in on shared devices | Identity `FR-IDN` | M1 | MVP |
| **EP-03** | Enrolment, cohorts & timetable | Enrolment `FR-ENR` | M1 | MVP |
| **EP-04** | Curriculum-as-data (KG–G5) + versioning | Curriculum `FR-CUR` | M2 | MVP |
| **EP-05** | Lesson runtime, progress & resume | Lesson `FR-LSN` | M2 | MVP |
| **EP-06** | AI Teacher: RAG tutoring + safety guardrails | AI Teacher `FR-AIT` | M2 | MVP |
| **EP-07** | Assessment: item bank, attempts, auto-grade | Assessment `FR-ASM` | M3 | MVP |
| **EP-08** | Gradebook & report card v1 | Grading `FR-GRD` | M3 | MVP |
| **EP-09** | North-star + analytics ingest | Analytics `FR-ANL` | M3 | MVP |
| **EP-10** | Offline day-pack + deterministic sync | Lesson/Media `FR-LSN/FR-MED` | M4 | MVP |
| **EP-11** | Media pipeline + moderation | Media `FR-MED` | M4 | MVP |
| **EP-12** | Trust & Safety spine (moderation, triage, audit) | Trust & Safety `FR-TNS` | M4 | MVP |
| **EP-13** | Transactional notifications (SMS/WA) | Engagement `FR-ENG` | M4 | MVP |
| **EP-14** | Platform config & feature flags | Platform/Admin `FR-ADM` | M1 | MVP |
| **EP-15** | Design system, tokens & components (Urdu/RTL/AA) | Cross-cutting | M1 | MVP |
| **EP-16** | Guardian Portal | Portals | M5 | MVP→v1 |
| **EP-17** | Human grading workflow | Assessment `FR-ASM` | M6 | v1 |
| **EP-18** | Promotion decisions & transcripts | Grading `FR-GRD` | M6 | v1 |
| **EP-19** | Mentor Portal (triage + grading) | Portals | M6 | v1 |
| **EP-20** | Student life (streaks/cohorts) + nudges | Engagement `FR-ENG` | M6 | v1 |
| **EP-21** | Search (Urdu-aware) | Search `FR-SCH` | M6 | v1 |
| **EP-22** | Analytics dashboards | Analytics `FR-ANL` | M6 | v1 |
| **EP-23** | KG–G10 curriculum + subjects | Curriculum `FR-CUR` | M6 | v1 |
| **EP-24** | Scale hardening toward 1M | Cross-cutting `NFR-SCAL` | M7 | v1→scale |
| **EP-25** | Thin Payments & Sponsorship | Payments `FR-PAY` | M6 | v1 |

## 3. Story convention

A story (`ST-NNN`) is a thin vertical slice with:

- **Title** + parent epic (`EP-NN`).
- **User value** (as a role from [Authoring Brief §2](../_meta/authoring-brief.md)).
- **Acceptance criteria** tracing to FR acceptance ([03](../01-product/03-functional-requirements.md))
  and satisfying the [DoD](../07-engineering/50-definition-of-done.md) (safety/reach/a11y/privacy).
- **Traceability:** FR ID(s), NFR constraints, milestone.

Example: *ST-001 (EP-01): A Guardian grants consent and enrols a child (FR-IDN-001) — no child record
without a linked consent (acceptance), offline-safe, Urdu-first, privacy-reviewed.*

## 4. Prioritisation & governance

- Priority follows MoSCoW ([02 §9](../01-product/02-prd.md)) and milestone order ([45](./45-milestone-plan.md)).
- Risks ([43](./43-risk-register.md)) generate mitigation stories.
- The backlog is living; this seed is the Phase-1 starting point, refined as specs are approved.

## Open questions

- **Estimation approach** and team topology mapping epics → teams.
- **Story-level decomposition** owner per epic.
- **Backlog tool** and `EP-NN`/`ST-NNN` ID management ([49](../07-engineering/49-development-workflow.md)).

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial seed backlog: 25 epics mapped to FRs, contexts, milestones, and releases; story convention with FR/DoD traceability. | Staff PM / Program Director |
