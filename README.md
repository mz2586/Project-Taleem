<div align="center">

# 🎓 Project Taleem

**The world's best AI-powered online school for Pakistani children who cannot afford or access traditional education.**

*A complete digital school — not an LMS, not a course platform, not a chatbot.*

`Status: Phase 1 — Foundation Blueprint (50/50 documents + ADRs drafted; pending approval)` · `Last updated: 2026-07-19`

</div>

---

## What this repository is

This repository is the **enterprise-grade blueprint** for Project Taleem, produced *before* a single
line of production code is written. It contains the vision, product requirements, architecture,
security & privacy model, child-safety framework, design system, educational engine specifications,
portal specifications, engineering standards, and delivery plan required to build a platform that
can serve **one million students**.

Start here:

1. **[Authoring Brief & Canonical Decisions](docs/_meta/authoring-brief.md)** — the single source of truth for names, scope, roles, and fixed technical decisions.
2. **[01 · Vision](docs/00-overview/01-vision.md)** — why this exists and what "done" looks like.
3. **[08 · System Architecture](docs/02-architecture/08-system-architecture.md)** — how it fits together.
4. **[44 · Roadmap](docs/08-delivery/44-roadmap.md)** — the path from blueprint to launch.

---

## Guiding principles

| Principle | What it means here |
|---|---|
| **AI-first education** | The AI Teacher is core pedagogy, not a bolt-on. Every learner gets a patient, personal tutor. |
| **Child safety by default** | Safety is an acceptance criterion for every feature, not a module. |
| **Low-bandwidth empathy** | Designed for a low-end Android phone on 3G with intermittent power. Every screen has a data budget. |
| **Accessibility (WCAG 2.2 AA)** | Urdu-first, RTL-complete, one-handed, screen-reader friendly. |
| **Scale from day one** | Architected for 1,000,000 students. No decision that quietly caps growth. |
| **Privacy by design** | Minimal data, strong consent, encryption, least privilege. |
| **Enterprise quality** | SOLID · Clean/Hexagonal · DDD · 12-Factor · OWASP · Every decision documented. |

---

## The 50 foundation documents

### 00 · Overview & Product

| # | Document | Location |
|---|---|---|
| 01 | Vision Document | [docs/00-overview/01-vision.md](docs/00-overview/01-vision.md) |
| 02 | Product Requirements Document (PRD) | [docs/01-product/02-prd.md](docs/01-product/02-prd.md) |
| 03 | Functional Requirements | [docs/01-product/03-functional-requirements.md](docs/01-product/03-functional-requirements.md) |
| 04 | Non-Functional Requirements | [docs/01-product/04-non-functional-requirements.md](docs/01-product/04-non-functional-requirements.md) |
| 05 | User Personas | [docs/01-product/05-user-personas.md](docs/01-product/05-user-personas.md) |
| 06 | User Journeys | [docs/01-product/06-user-journeys.md](docs/01-product/06-user-journeys.md) |
| 07 | Information Architecture | [docs/01-product/07-information-architecture.md](docs/01-product/07-information-architecture.md) |

### 02 · Architecture & Data

| # | Document | Location |
|---|---|---|
| 08 | System Architecture | [docs/02-architecture/08-system-architecture.md](docs/02-architecture/08-system-architecture.md) |
| 09 | Database Design | [docs/02-architecture/09-database-design.md](docs/02-architecture/09-database-design.md) |
| 10 | API Design | [docs/02-architecture/10-api-design.md](docs/02-architecture/10-api-design.md) |
| 32 | Search Architecture | [docs/02-architecture/32-search-architecture.md](docs/02-architecture/32-search-architecture.md) |
| 33 | Offline Architecture | [docs/02-architecture/33-offline-architecture.md](docs/02-architecture/33-offline-architecture.md) |
| 34 | Media Architecture | [docs/02-architecture/34-media-architecture.md](docs/02-architecture/34-media-architecture.md) |
| 35 | Deployment Architecture | [docs/02-architecture/35-deployment-architecture.md](docs/02-architecture/35-deployment-architecture.md) |
| 36 | Infrastructure Architecture | [docs/02-architecture/36-infrastructure-architecture.md](docs/02-architecture/36-infrastructure-architecture.md) |
| — | Architecture Decision Records | [docs/02-architecture/adr/](docs/02-architecture/adr/) |

### 03 · Security, Privacy & Safety

| # | Document | Location |
|---|---|---|
| 11 | Authentication Strategy | [docs/03-security-privacy/11-authentication-strategy.md](docs/03-security-privacy/11-authentication-strategy.md) |
| 12 | Authorization Model | [docs/03-security-privacy/12-authorization-model.md](docs/03-security-privacy/12-authorization-model.md) |
| 13 | Security Model | [docs/03-security-privacy/13-security-model.md](docs/03-security-privacy/13-security-model.md) |
| 14 | Privacy Model | [docs/03-security-privacy/14-privacy-model.md](docs/03-security-privacy/14-privacy-model.md) |
| 15 | Child Safety Framework | [docs/03-security-privacy/15-child-safety-framework.md](docs/03-security-privacy/15-child-safety-framework.md) |

### 04 · Design & Experience

| # | Document | Location |
|---|---|---|
| 16 | Accessibility Standards | [docs/04-design/16-accessibility-standards.md](docs/04-design/16-accessibility-standards.md) |
| 17 | UI Design System | [docs/04-design/17-ui-design-system.md](docs/04-design/17-ui-design-system.md) |
| 18 | Design Tokens | [docs/04-design/18-design-tokens.md](docs/04-design/18-design-tokens.md) |
| 19 | Component Library | [docs/04-design/19-component-library.md](docs/04-design/19-component-library.md) |
| 20 | Navigation Structure | [docs/04-design/20-navigation-structure.md](docs/04-design/20-navigation-structure.md) |

### 05 · Educational Engines

| # | Document | Location |
|---|---|---|
| 21 | Curriculum Engine Specification | [docs/05-education/21-curriculum-engine.md](docs/05-education/21-curriculum-engine.md) |
| 22 | Lesson Engine | [docs/05-education/22-lesson-engine.md](docs/05-education/22-lesson-engine.md) |
| 23 | Assessment Engine | [docs/05-education/23-assessment-engine.md](docs/05-education/23-assessment-engine.md) |
| 24 | AI Teacher Specification | [docs/05-education/24-ai-teacher-specification.md](docs/05-education/24-ai-teacher-specification.md) |

### 06 · Portals & Platform Services

| # | Document | Location |
|---|---|---|
| 25 | Parent Portal Specification | [docs/06-portals/25-parent-portal.md](docs/06-portals/25-parent-portal.md) |
| 26 | Student Portal Specification | [docs/06-portals/26-student-portal.md](docs/06-portals/26-student-portal.md) |
| 27 | Admin Portal Specification | [docs/06-portals/27-admin-portal.md](docs/06-portals/27-admin-portal.md) |
| 28 | Mentor Portal Specification | [docs/06-portals/28-mentor-portal.md](docs/06-portals/28-mentor-portal.md) |
| 29 | Reporting System | [docs/06-portals/29-reporting-system.md](docs/06-portals/29-reporting-system.md) |
| 30 | Notification System | [docs/06-portals/30-notification-system.md](docs/06-portals/30-notification-system.md) |
| 31 | Analytics Platform | [docs/06-portals/31-analytics-platform.md](docs/06-portals/31-analytics-platform.md) |

### 07 · Engineering Practice

| # | Document | Location |
|---|---|---|
| 37 | CI/CD Pipeline | [docs/07-engineering/37-cicd-pipeline.md](docs/07-engineering/37-cicd-pipeline.md) |
| 38 | Monitoring | [docs/07-engineering/38-monitoring.md](docs/07-engineering/38-monitoring.md) |
| 39 | Logging | [docs/07-engineering/39-logging.md](docs/07-engineering/39-logging.md) |
| 40 | Testing Strategy | [docs/07-engineering/40-testing-strategy.md](docs/07-engineering/40-testing-strategy.md) |
| 41 | Coding Standards | [docs/07-engineering/41-coding-standards.md](docs/07-engineering/41-coding-standards.md) |
| 42 | Documentation Standards | [docs/07-engineering/42-documentation-standards.md](docs/07-engineering/42-documentation-standards.md) |
| 47 | Folder Structure | [docs/07-engineering/47-folder-structure.md](docs/07-engineering/47-folder-structure.md) |
| 48 | Repository Standards | [docs/07-engineering/48-repository-standards.md](docs/07-engineering/48-repository-standards.md) |
| 49 | Development Workflow | [docs/07-engineering/49-development-workflow.md](docs/07-engineering/49-development-workflow.md) |
| 50 | Definition of Done | [docs/07-engineering/50-definition-of-done.md](docs/07-engineering/50-definition-of-done.md) |

### 08 · Delivery & Governance

| # | Document | Location |
|---|---|---|
| 43 | Risk Register | [docs/08-delivery/43-risk-register.md](docs/08-delivery/43-risk-register.md) |
| 44 | Roadmap | [docs/08-delivery/44-roadmap.md](docs/08-delivery/44-roadmap.md) |
| 45 | Milestone Plan | [docs/08-delivery/45-milestone-plan.md](docs/08-delivery/45-milestone-plan.md) |
| 46 | Project Backlog | [docs/08-delivery/46-project-backlog.md](docs/08-delivery/46-project-backlog.md) |

---

## Technology at a glance

**Frontend:** Next.js · React · TypeScript · Tailwind CSS (mobile-first PWA)
**Backend:** FastAPI (Python) · Clean/Hexagonal · DDD · REST + OpenAPI · WebSockets
**Data:** PostgreSQL · Redis · Meilisearch · S3-compatible storage · columnar analytics warehouse
**AI:** Provider-abstracted LLM gateway (Claude-default) · RAG over curriculum · safety guardrails
**Infra:** Docker · Kubernetes-ready · GitHub Actions · Terraform-ready

See [Authoring Brief](docs/_meta/authoring-brief.md) §4 for the authoritative, ADR-governed stack.

---

## Repository layout

```text
taleem/
├── README.md                     ← you are here
├── docs/
│   ├── _meta/                     ← authoring brief, doc standards seed
│   ├── 00-overview/              ← 01 vision
│   ├── 01-product/               ← 02–07 product, personas, journeys, IA
│   ├── 02-architecture/          ← 08–10, 32–36, ADRs
│   ├── 03-security-privacy/      ← 11–15 auth, authz, security, privacy, child safety
│   ├── 04-design/                ← 16–20 accessibility, design system, tokens, components, nav
│   ├── 05-education/             ← 21–24 curriculum, lesson, assessment, AI teacher
│   ├── 06-portals/               ← 25–31 portals, reporting, notifications, analytics
│   ├── 07-engineering/           ← 37–42, 47–50 engineering practice
│   ├── 08-delivery/              ← 43–46 risk, roadmap, milestones, backlog
│   └── diagrams/                 ← standalone diagrams
└── .github/workflows/           ← CI for docs (lint, link-check) — see 37
```

---

## How to read this blueprint

- **Executives / partners:** 01 Vision → 44 Roadmap → 43 Risk Register.
- **Product:** 02 PRD → 03/04 Requirements → 05/06 Personas & Journeys → 21–31 specs.
- **Architects / engineers:** Authoring Brief → 08 System Architecture → 09/10 Data & API → ADRs → 07-engineering.
- **Design:** 16 Accessibility → 17 Design System → 18 Tokens → 19 Components → 20 Navigation.
- **Trust & Safety / Legal:** 15 Child Safety → 14 Privacy → 13 Security.

---

*Project Taleem is being designed to give every Pakistani child a real school. Quality is not
negotiable, because the stakes are children's futures.*
