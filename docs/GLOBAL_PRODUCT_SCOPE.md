# Project Taleem — Global Product Scope

**Status:** Binding product definition · **Adopted:** 2026-10-22 · **Revised:** 2026-10-24
(definitive mission: AI-led school, no hired teaching workforce) · **Owner:** Founder + Engineering
lead

This document defines *what* Project Taleem must be. It does not track status: implementation status,
evidence, and the execution roadmap live in
[`PROJECT_TALEEM_MASTER_SCOPE.md`](../PROJECT_TALEEM_MASTER_SCOPE.md), which is the single
authoritative status reference. Where the two disagree on scope, this document wins; where they
disagree on status, the master scope wins (and must cite evidence).

## Definitive mission (authoritative, adopted 2026-10-24)

**The AI is the teacher. The platform is the school. Education should be free for children who
cannot afford it.**

Project Taleem is a global, AI-led, online-only school. It gives children who cannot afford formal
education access to a complete, high-quality education. It is **not** a conventional teacher-led
virtual school, it does **not** hire teachers to deliver lessons, and it is **not** merely an LMS
for existing schools.

**Definition of success.** A child can access Taleem, learn through AI instruction, complete
meaningful educational activities, receive appropriate feedback, demonstrate mastery, keep their
progress through unreliable connectivity, and follow a structured educational path, without paying
for a private teacher or private schooling.

### No hired teaching workforce

- AI is the primary instructional provider. Teacher hiring, teacher-delivered classes and
  teacher-led instruction are never foundational requirements. No learner journey may depend on a
  teacher existing.
- Humans are still required where quality, safety and legitimacy demand it: **curriculum review
  and subject-expert approval, safeguarding oversight, legal compliance, independent evaluation, and
  accreditation.** These roles oversee the school; they do not teach in it.
- Existing teacher and class tools (classes, assignments, marking) remain **optional** features
  for a guardian, volunteer mentor or partner institution. Every capability they offer also has an
  AI-led or system path that needs no teacher.

### Quality is non-negotiable

Taleem is a reliable educational system, not a chatbot labelled as a school. Curriculum content is
grounded, properly sourced and reviewed as required. Assessments are validated. AI is evaluated for
accuracy, pedagogical quality, age appropriateness and safety. Learner progress reflects evidence,
not engagement metrics. Children's privacy, consent and authorization are enforced, with escalation
procedures for safety concerns.

### Recognized education

The long-term goal is a complete, reliable, global AI-led school with a credible route to
recognized qualifications. Accreditation and qualification pathways compatible with AI-led
instruction are researched per jurisdiction. Where a jurisdiction requires conventional teacher-led
teaching, that incompatibility is documented and alternatives (e.g. private-candidate examinations,
partner-assessed credentials) are assessed. **The product vision is never silently changed to fit
an unsuitable pathway, and no accreditation or qualification recognition is ever claimed before
authorization is obtained.**

## Required capabilities of the finished product

1. Complete structured education: grade levels, subjects, curricula and learning objectives.
2. An AI Teacher that explains lessons, answers questions, gives examples, provides hints,
   identifies misconceptions and adapts instruction to each learner.
3. Diagnostic assessments, exercises, homework, automated marking where reliable, examinations,
   progress reports and academic records.
4. A learning intelligence engine that tracks demonstrated mastery, recommends revision and
   determines appropriate next learning steps.
5. A complete student experience from enrolment and onboarding through lessons, assessment,
   progression and completion.
6. Secure parent or guardian access, consent, appropriate progress reporting and child-safety
   controls.
7. Offline-first learning, downloadable content, durable local progress and reliable
   synchronization.
8. Global curriculum and localization support: multiple languages, countries, education systems,
   RTL/LTR interfaces.
9. Accessibility for children with affordable devices, limited bandwidth and different learning
   needs.
10. A sustainable model that keeps core educational access free, especially for underserved
    children, without selling children's data or targeted advertising to children.
11. A credible path toward formally recognized education and qualifications, subject to the
    appropriate jurisdiction, institutional authorization and examination requirements.

The evidence-backed status of each lives in the master scope.

**Self-directed learning is never represented, in the UI, reports, certificates or marketing, as
accredited schooling** until a named, authorized pathway exists, and then it is labelled as such.

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
- Explanations of why a recommendation was made, visible to the learner, the guardian and any
  reviewer.
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

### F. Family experience and optional human oversight

- Secure guardian identity, verified relationships, and consent.
- Authorized child progress and activity views.
- Optional tools for a guardian, volunteer mentor or partner institution (classes, assignments,
  marking, insights). Every one has an AI-led or system path, so no learner depends on them.
- Human review of AI-generated educational material before it reaches learners (curriculum
  reviewers, not teachers).
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
4. A complete AI-led school loop (teaching, assessment, homework, reports, progression) with no
   hired teaching workforce.
5. A credible pathway from free AI-led learning to recognized qualifications.

## Business-model principles

- Core education is free for children who cannot afford it; sustained by philanthropy, government
  and NGO sponsorship, institutional licensing, optional family services, and education partnerships.
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
| **R2** | Personalized learning | Mastery model, diagnostics, adaptive paths, revision engine, curriculum-grounded AI tutor, safety evaluations, optional human interventions — validated with reproducible tests and controlled educational evaluation. |
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
