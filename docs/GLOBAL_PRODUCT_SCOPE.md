# Project Taleem — Global Product Scope

**Status:** Binding product definition · **Adopted:** 2026-10-22 · **Owner:** Engineering lead

This document defines *what* Project Taleem must be. It does not track status: implementation status,
evidence, and the execution roadmap live in
[`PROJECT_TALEEM_MASTER_SCOPE.md`](../PROJECT_TALEEM_MASTER_SCOPE.md), which is the single
authoritative status reference. Where the two disagree on scope, this document wins; where they
disagree on status, the master scope wins (and must cite evidence).

## Mission

Build a dependable, accessible education platform that helps learners worldwide master skills
through curriculum-aware personalized learning, AI tutoring, teacher support, family involvement,
and resilient offline operation.

**Pakistan is the launch market, not the product boundary.** Pakistan-specific facts — the National
Curriculum (NCP) grade and subject roster, Urdu as primary language, Eastern-Arabic numerals,
recorded-Urdu-audio requirements — are *configuration* of one curriculum pack and one locale. They
must not be hard-coded into core domain logic. No curriculum, country, or language is claimed as
supported until it has been implemented and validated (see "Supported today" in the master scope).

## Product scope

### A. Student learning experience

- Age-appropriate student interface.
- Structured lessons, exercises, assessments, and feedback.
- Learning objectives linked to curriculum standards.
- Progress tracking based on demonstrated skill, not time spent.
- Responsive, accessible, localization-ready UI.
- Support for low-end devices and intermittent connectivity.

### B. Personal AI tutor

- Curriculum-grounded explanations and guided practice.
- Hints before answers, step-by-step teaching, misconception remediation.
- Difficulty adaptation based on learner evidence.
- Explicit evaluation of accuracy, pedagogical quality, age appropriateness, and safety.
- Replaceable AI provider integration and operational cost tracking.
- Offline fallback for supported learning activities.
- Voice and richer multimodal interaction as *separately validated* capabilities.

**Hard limits.** An LLM may not make unrestricted decisions about a child, may not access learner
records it is not authorized for, and may not bypass content or safety controls. Verified
curriculum facts are always distinguishable from generated explanations.

### C. Learning intelligence engine

- Curriculum objective and skill model.
- Diagnostic assessments.
- Evidence-based mastery estimates with confidence and provenance.
- Adaptive next-step recommendations.
- Spaced revision and retention checks.
- Teacher-visible explanations of why a recommendation was made.
- A single incorrect answer is never treated as definitive evidence of inability.

### D. Global curriculum and content

- A curriculum-independent domain model.
- Configurable countries, education systems, grade structures, subjects, standards, and academic
  calendars — expressed as **curriculum packs**.
- Versioned content packs with provenance, approval status, and review history.
- Localization workflows for translated content and interface strings.
- RTL and LTR support; locale-aware formatting.
- Qualified human review for important educational content.

### E. Offline-first infrastructure

- Explicit local persistence and synchronization guarantees.
- Durable queued learner activity; idempotent event processing.
- Conflict detection and deterministic reconciliation rules.
- Recovery after browser restart, device restart, and connectivity interruption.
- A visible distinction between *saved on this device*, *synchronized*, and *server-confirmed*.
- Safe handling of authorization changes, revoked consent, and expired sessions.
- Tests proving acknowledged work is never silently lost.
- Shared local learning hubs only after core offline functionality is reliable.

### F. Family and teacher experiences

- Secure guardian identity, verified relationships, and consent.
- Authorized child progress and activity views.
- Teacher lesson planning, assignments, class insights, and remedial recommendations.
- Teacher oversight of AI-generated educational material.
- No exposure of one learner's private data to another family or to unauthorized staff.

### G. Global organizational capabilities

- Organization and school tenancy with tested isolation.
- Configurable locale, curriculum, and regional policy.
- Internationalization and accessibility foundations.
- Data retention, deletion, export, and consent workflows.
- Jurisdiction-specific privacy and child-protection review before each regional launch.
- Operational observability, backup, recovery, and support documentation.
- A documented path to regional data residency.

### H. Future expansion (tracked; must not delay Releases 1–3)

- Full school administration, attendance, and timetabling.
- Advanced voice tutoring and community learning hubs.
- Additional age groups and vocational education.
- Publisher and education-system integrations.
- Scholarships and verified educational opportunities.

## Release gates

A release is complete only when its acceptance criteria, tests, documentation, **and required human
approvals** are all satisfied. Engineering alone cannot close a release that needs an approval.

| Release | Name | Must deliver |
| --- | --- | --- |
| **R1** | Reliable learning platform | Real identity and consent; student learning journey; curriculum delivery with real content; assessments; guardian integration; offline persistence and sync; production deployment; security controls; end-to-end tests; the initial localization foundation; an explicit list of the curricula and languages genuinely supported. |
| **R2** | Personalized learning | Mastery model, diagnostics, adaptive paths, revision engine, curriculum-grounded AI tutor, safety evaluations, teacher interventions — validated with reproducible tests and controlled educational evaluation. |
| **R3** | Global readiness | Additional validated locales and curriculum packs; accessibility, regional privacy, security, reliability, performance, deployment operations, onboarding. Each regional launch carries documented human approval. |
| **R4** | Education ecosystem | School administration, richer media, voice, community distribution, integrations, and new markets — each as an independently scoped milestone. |

## Engineering rules (summary)

The repository on GitHub is the source of truth; heavy work runs in Codespaces; migrations are
reversible; every change ships with tests; nothing is reported as passing, deployed, integrated, or
approved without evidence; a placeholder or mock is never recorded as a production integration; and
security, consent, and child-safety behaviour is never weakened to make a test or a deadline pass.
Full conventions: [`CONTRIBUTING.md`](../CONTRIBUTING.md), [`ENGINEERING.md`](../ENGINEERING.md).
