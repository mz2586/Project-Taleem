# Project Taleem — Global Product Scope

**Status:** Binding product definition · **Adopted:** 2026-10-22 · **Revised:** 2026-10-22 (official
global mandate: two pathways, positioning, business principles) · **Owner:** Engineering lead

This document defines *what* Project Taleem must be. It does not track status: implementation status,
evidence, and the execution roadmap live in
[`PROJECT_TALEEM_MASTER_SCOPE.md`](../PROJECT_TALEEM_MASTER_SCOPE.md), which is the single
authoritative status reference. Where the two disagree on scope, this document wins; where they
disagree on status, the master scope wins (and must cite evidence).

## Vision and mission

Build Project Taleem into a global, AI-powered, offline-first education platform that can evolve
into a comprehensive, teacher-supported online school through qualified education partners.

**Mission:** make high-quality, personalized education accessible to children worldwide regardless
of language, country, household income, device capability, or internet reliability.

## Two connected pathways

| Pathway | What it is | Status of claim |
| --- | --- | --- |
| **Taleem Learn** — free core learning | Lessons, exercises, assessments, progress; personalized paths and mastery; curriculum-grounded AI tutoring with child-safety controls; downloadable offline content; family access and teacher support where available. | The R1–R2 product. |
| **Taleem School** — structured, teacher-supported education | Teacher-led learning and assignments; class and school management; academic calendars, assessments, and reports; guardian communication; integration with authorized education partners and recognized qualifications **only through appropriate accreditation arrangements**. | R3–R4, partner-dependent. |

**Self-directed learning in Taleem Learn is never represented — in the UI, reports, certificates,
or marketing — as accredited schooling.** Any qualification pathway exists only through a named,
authorized partner and is labelled as such.

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
- **Interface language, instructional language, and curriculum region are independent settings**:
  an English interface can present an Urdu-medium lesson from a Pakistani curriculum pack.
- **Language priorities:** English and Urdu first. Arabic and others are evaluated on demand and on
  the availability of validated content; none is claimed until it works and its content is reviewed.
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

### H. School and education-partner capabilities, and future expansion

Planned: structured schooling, attendance, timetabling, teacher administration, school reporting,
institutional onboarding, and qualification pathways. Only the minimum needed for a credible pilot is
prioritized; full school ERP and independent accreditation are **not** prerequisites for R1.

Tracked expansion (must not delay R1–R3):

- Full school administration, attendance, and timetabling.
- Advanced voice tutoring and community learning hubs.
- Additional age groups and vocational education.
- Publisher and education-system integrations.
- Scholarships and verified educational opportunities.

## Competitive positioning

Taleem enters a field that already includes Khan Academy, CK-12, IXL, and formal virtual-school
providers. AI tutoring, adaptive practice, or free lessons alone are **not** differentiators and are
never claimed as such. Differentiation must be demonstrated, with evidence, through the
*integration* of:

1. Reliable offline-first learning.
2. Curriculum-aware personalization and measurable mastery.
3. Global curriculum and localization infrastructure.
4. Connected student, guardian, and teacher workflows.
5. A credible pathway from free learning to partner-supported formal schooling.

## Business-model principles

- Free to start; sustained by optional family services, institutional subscriptions, school
  contracts, government and NGO sponsorship, and education partnerships.
- Learner data is never sold; advertising is never targeted at children; unnecessary personal-data
  disclosure is never a condition of basic educational access.
- AI inference and operating cost are tracked **per learner**, with quotas and funding mechanisms
  that keep the free tier useful and financially sustainable.

## Release gates

A release is complete only when its acceptance criteria, tests, documentation, **and required human
approvals** are all satisfied. Engineering alone cannot close a release that needs an approval.

| Release | Name | Must deliver |
| --- | --- | --- |
| **R1** | Reliable learning platform | Real identity, authorization, and guardian consent; complete student journeys; working curriculum delivery and assessments; guardian dashboard on real services; reliable offline persistence and sync; localization and curriculum-configuration foundations; an initial validated English/Urdu experience and explicitly defined curriculum packs; production deployment, monitoring, security, and recovery checks; end-to-end tests of real student and guardian workflows. |
| **R2** | Personalized learning | Mastery model, diagnostics, adaptive paths, revision engine, curriculum-grounded AI tutor, safety evaluations, teacher interventions — validated with reproducible tests and controlled educational evaluation. |
| **R3** | Global pilot readiness | Additional validated locales and curriculum packs; accessibility, regional privacy, security, reliability, performance, deployment operations, onboarding. Each regional launch carries documented human approval. |
| **R4** | Education ecosystem | Expanded school administration, voice and richer interaction, community hubs, publisher and education-system integrations, additional age groups and vocational learning, broader partner-operated schooling — each independently scoped. |

**R1 acceptance condition.** A real learner can use the approved authentication flow, complete
learning activities, retain work offline, synchronize safely, and have the correct progress visible
to an authorized guardian — demonstrated end to end with recorded evidence.

## Engineering rules (summary)

The repository on GitHub is the source of truth; heavy work runs in Codespaces; migrations are
reversible; every change ships with tests; nothing is reported as passing, deployed, integrated, or
approved without evidence; a placeholder or mock is never recorded as a production integration; and
security, consent, and child-safety behaviour is never weakened to make a test or a deadline pass.
Full conventions: [`CONTRIBUTING.md`](../CONTRIBUTING.md), [`ENGINEERING.md`](../ENGINEERING.md).
