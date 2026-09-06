# Project Taleem — Master Product Scope & Roadmap

**Status:** Living document · **Last updated:** 2026-09-06 · **Repository HEAD at authoring:** `23747f9`

This is the **single high-level reference** for what Project Taleem is, what it will be when it is
finished, and exactly how much of it exists today. It does not replace the detailed blueprint — the
94 documents under [`docs/`](docs/) and the architecture records at the repository root remain
authoritative for their subjects, and this document links to them rather than restating them.

**Reading rule.** Every status claim below is tied to evidence in this repository: a source file, a
test, a migration, a contract, or a CI run. Where evidence does not exist, the status says so.
Nothing here is marked complete because it was planned, designed, or reported complete elsewhere.

---

## 1. Executive Summary

**Project Taleem (تعلیم, "education") is a digital school for children in Pakistan who cannot
attend a physical one.** Not a content library and not a tutoring app: a structured school — a
curriculum, a teacher, progression, assessment, and a report a parent can read — delivered on the
cheapest Android phone a family already owns, in Urdu, and working when the network does not.

**The problem.** Pakistan has one of the largest out-of-school populations in the world. The
barriers are rarely the child's willingness: distance, cost, safety, gender, disability, displaced
families, and the simple absence of a school within reach. Existing digital education assumes a
reliable connection, a shared language of instruction that is usually English, and a literate adult
to supervise. Each assumption excludes the children who need it most.

**Who it serves.** Children from kindergarten through Grade 10; their guardians, who are often the
only adult in the loop and may themselves have limited literacy; mentors and teachers where a human
is available; and the curriculum authors and reviewers who make the content trustworthy.

**Principles that constrain every technical decision in this repository:**

- **Urdu-first, not Urdu-translated.** The interface, the curriculum, and the teaching voice are
  authored in Urdu and rendered right-to-left by default. English is supported where the curriculum
  requires it — as a subject and as a second option — never as the assumed default.
- **Offline-first.** A lesson downloaded once must be completable with the aircraft in flight mode,
  and the resulting progress must reconcile without loss or duplication when connectivity returns.
  The offline path is the primary path, not a degraded fallback.
- **Child safety and privacy by construction.** A child has no email address, no phone number, no
  date of birth, and no recoverable credential anywhere in this system. That is enforced by the
  database schema, not by a policy document.
- **Guardian involvement is a precondition, not a feature.** No child can sign in without live,
  recorded, withdrawable guardian consent, and the withdrawal takes effect on the next request.
- **Accessibility is a release gate.** WCAG 2.2 AA, keyboard reachability, screen-reader support,
  and low-bandwidth operation are exit criteria, not a later pass.

### Current maturity — stated honestly

**Project Taleem is not a working school today. It is a substantially complete school *platform*
with almost no school *content* in it, no verified running environment, and no governance sign-off
to admit a real child.**

Specifically:

- The **engineering artefact is of release-candidate quality**: 7 bounded contexts, 60 HTTP
  operations across 58 paths, 345 backend tests at 95.96% coverage, strict `mypy` clean across 135
  source files, 4 migrations verified reversible against PostgreSQL 16, 9 validated OpenAPI
  contracts with served-path parity enforcement, a complete offline sync engine with 90 frontend
  tests, and production asymmetric authentication.
- The **product is not**. There are zero published lessons in any database, zero audio assets for an
  audio-first product, no real AI in the AI Teacher, no verified live deployment, and a landing page
  that still says "M1 walking skeleton" in its own words.
- The **governance gates are not signed**. `GO_NO_GO_DECISION.md` records **NO-GO for Pilot 1 with
  real children** until M-Gov and M-Safe close. Nothing in this repository indicates that has
  changed. **No real child data may touch this system.**

The honest summary: the hard, structural engineering is done to a high standard; the content, the
teaching intelligence, the human governance, and the live environment are not.

---

## 2. Product Vision

The finished platform is a **complete digital school**, not a subset of one. A child enrolled in
Taleem should have every element a physical school gives them, subject to what software can deliver:

| Element of a school | What Taleem provides |
| --- | --- |
| A place to attend | A student portal that opens to today's plan, on a low-end phone, online or off |
| A curriculum | Kindergarten to Grade 10, aligned to Pakistan's National Curriculum outcomes, authored originally |
| A teacher | An AI Teacher grounded in the published curriculum — never free-floating generation |
| A timetable | A daily learning plan derived from mastery, forgetting, and the curriculum graph |
| Lessons | Text, visual, and audio content with interactive activities and exercises |
| Homework and revision | Spaced review scheduled from a forgetting model, plus assigned practice |
| Assessment | Formative checks, summative assessments, auto-grading, and honest mastery estimates |
| A report card | Guardian-readable progress, knowledge growth, and intervention alerts |
| Pastoral care | Distress detection routed to a human within an SLA; safeguarding escalation |
| A registrar | Guardian-held enrolment, consent, and an auditable record of who did what |

Sequencing is set by [`ROADMAP.md`](ROADMAP.md) and [`CRITICAL_PATH.md`](CRITICAL_PATH.md), and the
governing rule there is unchanged: **governance and safety gate everything; content and audio are
the long pole; engineering is largely parallel and largely already done.**

Milestone definitions M0–M7 live in [`docs/08-delivery/45-milestone-plan.md`](docs/08-delivery/45-milestone-plan.md).
This document does not renumber them.

---

## 3. Users and Roles

Roles below are the ones the repository actually implements in its deny-by-default policy table
([`auth/pdp.py`](services/core-api/src/taleem_core/auth/pdp.py)), plus the human roles the
governance documents define but no software surface yet serves. Each is marked accordingly.

### 3.1 Student (learner) — implemented

- **Purpose.** Learn. The only role that consumes lessons and produces attempts.
- **Identity.** A `student_ref` opaque identifier. No email, no phone, no date of birth. Signs in
  with a **family code + display name + 4–6 digit PIN**, optionally bound to a device.
- **Permissions.** `operate learning.session`, `read learning.knowledge`. Nothing else.
- **Workflows.** Sign in → today's plan → lesson session (`:next`, `:teach`, `:hint`, `:explain`,
  `:answer`, `:end`) → progress, homework, reviews, achievements → offline download and sync.
- **Security boundary.** A learner token reaches **only its own** `student_ref`; every student-scoped
  route re-checks ownership (`require_owner_or`), and sync deltas carrying another child's ref are
  rejected. Verified by `test_identity_api.py` and `test_student_api.py`.

### 3.2 Guardian / parent — implemented

- **Purpose.** The responsible adult. Enrols children, gives and withdraws consent, sees progress.
- **Identity.** A `guardian_ref` plus the only contact address in the platform. Passphrase-based,
  length-led policy (NIST SP 800-63B), PBKDF2-HMAC-SHA256 at the OWASP work factor.
- **Permissions.** `read identity.self`, `manage identity.learner`, `manage identity.consent`,
  `read identity.audit`, `read guardian.self`. **Read-only** over all learning data — a guardian
  never mutates a child's learning state.
- **Workflows.** Register → enrol a learner → grant consent → share the family code → monitor via
  the Guardian Portal → withdraw consent at any time → read the family audit trail.
- **Security boundary.** Ownership is derived from the verified token subject, never from a request
  body. Another family's learner returns `404` rather than `403`, so a probe cannot confirm a ref
  names a real child elsewhere.

### 3.3 AI Teacher — implemented as a deterministic engine, not an AI

- **Purpose.** Teach, explain, hint, and plan — grounded strictly in published curriculum.
- **Current reality.** A templated, explainable decision engine
  ([`domain/ai_teacher.py`](services/core-api/src/taleem_core/contexts/learning/domain/ai_teacher.py),
  [`domain/runtime.py`](services/core-api/src/taleem_core/contexts/learning/domain/runtime.py)).
  **There is no language model in the running system.** See §8.
- **Security boundary.** Cannot emit content that is not derived from a published `LessonView`.

### 3.4 Curriculum author (`subject_author`) — implemented

- **Purpose.** Write lessons, objectives, activities, and assessment blueprints.
- **Permissions.** `read` and `author` on `curriculum.lesson`; may submit their own drafts. **May
  not review or publish** — no self-approval.
- **Workflows.** Create draft → `:validate` (automated gates) → `:submit` into review.

### 3.5 Curriculum reviewers — implemented

Five distinct reviewer roles, each owning one stage of the review workflow: `subject_expert`,
`instructional_designer`, `a11y_specialist`, `language_editor`, `safety_officer`.

- **Permissions.** `read` and `review` on `curriculum.lesson`. Not `publish`.
- **Workflows.** `:review` with `approve` or `request_changes` at their own stage only. Stage order
  and the no-self-approval rule are enforced in the domain as well as the PDP (defence in depth).

### 3.6 Curriculum architect — implemented

- **Permissions.** Adds `publish` and `rollback` on `curriculum.lesson` to the reviewer set.
- **Workflows.** Publish an approved lesson; roll back a published version.

### 3.7 Operations (`system`) — implemented

- **Purpose.** Keep the platform safe and observable during a pilot.
- **Permissions.** `operate ops.control` (kill switch), `read ops.status`, `write sync.batch`,
  `read identity.audit`.
- **Explicit non-permission.** An operator **cannot** grant consent or reset a child's PIN. Consent
  is a decision only the responsible adult may make; this is asserted by a test.

### 3.8 Mentor / teacher — partially implemented

- **Implemented.** `read learning.knowledge`, `read learning.session`, `read ops.status` in the PDP.
- **Not implemented.** No mentor GUI, no mentor identity provisioning, no assignment of a mentor to
  a learner. Workflows are specified in [`MENTOR_WORKFLOWS.md`](MENTOR_WORKFLOWS.md); no surface
  exists.

### 3.9 Administrator — not implemented

Specified in [`docs/06-portals/`](docs/06-portals/). No admin role in the PDP, no admin GUI, no
tenant or school management. School-level administration is out of scope until Pilot 3.

### 3.10 Safeguarding / governance roles — not implemented in software

DPO, safeguarding lead, and on-call reviewer are defined in [`INCIDENT_RESPONSE.md`](INCIDENT_RESPONSE.md)
and the M-Gov / M-Safe gates. They are **human roles with no software surface**: there is no
safeguarding triage queue, no distress-flag review console, and no reporting workflow implemented.
This is a governance blocker, not an oversight — see §11.

---

## 4. Complete System Architecture

Detailed records: [`ARCHITECTURE_REVIEW.md`](ARCHITECTURE_REVIEW.md),
[`docs/02-architecture/`](docs/02-architecture/), [`OFFLINE_ARCHITECTURE.md`](OFFLINE_ARCHITECTURE.md).
This section summarises and marks status only.

### 4.1 Frontend — implemented, wired to a development auth stub

| Element | Status | Evidence |
| --- | --- | --- |
| Next.js App Router, React, TypeScript strict | 🟢 | `apps/web`, `tsc --noEmit` clean |
| 11 routes (`/`, student ×6, guardian ×2, studio, index) | 🟢 | `apps/web/app/**/page.tsx` |
| PWA — service worker, manifest, install | 🟢 | `apps/web/public/sw.js`, `manifest.webmanifest` |
| Offline: IndexedDB, download manager, sync queue, background drain | 🟢 | `apps/web/lib/offline/*`, 90 vitest tests |
| Crash recovery, reconciliation, cache versioning, LRU eviction | 🟢 | `syncCrashRecovery.test.ts`, `reconcile.test.ts`, `purge.test.ts` |
| Client-side Ed25519 package-signature verification | 🟢 | `lib/offline/signature.ts` + tests |
| RTL and Urdu-first shell | 🟢 | `app/layout.tsx` (`lang="ur" dir="rtl"`), RTL-mirrored `BottomNav` |
| Design tokens and component primitives | 🟢 | `design-system/tokens.css`, `components/student/ui.tsx` |
| **Authentication** | 🟡 | Still `NEXT_PUBLIC_DEV_STUDENT_TOKEN` / `DEV_GUARDIAN_TOKEN` stubs in `lib/student/config.ts` and `lib/guardian/config.ts` — the real identity API now exists but the frontend has not been rewired |
| Landing page product content | 🔴 | `app/page.tsx` still renders "M1 walking skeleton. Governance-safe scaffolding only." |

### 4.2 Backend — implemented

FastAPI over a pure-stdlib domain core. The `contexts` and `platform` layers import no framework, so
the entire domain is unit-testable with no third-party installs — a property the test suite relies
on and CI enforces.

| Element | Status | Evidence |
| --- | --- | --- |
| Hexagonal architecture: domain / application / adapters per context | 🟢 | Directory shape under `contexts/*` |
| Bounded contexts: `identity`, `curriculum_studio`, `learning`, `guardian`, `sync`, `ops`, `health` | 🟢 | `contexts/` |
| Composition root wiring all contexts, one deployable | 🟢 | `main.py` |
| RFC 9457 problem+json error contract | 🟢 | `platform/errors.py` |
| Structured logging with redaction, correlation IDs | 🟢 | `platform/logging.py`, `platform/correlation.py` |
| Metrics + golden signals, Prometheus exposition | 🟢 | `platform/metrics.py`, `GET /metrics` |
| Security headers, CORS allowlist (never `*`) | 🟢 | `platform/security_headers.py`, `test_cors.py` |
| Feature flags, i18n, plugin/module registry | 🟢 | `platform/` |
| Pure-stdlib Ed25519 (tokens and offline packages) | 🟢 | `platform/ed25519.py`, `test_ed25519.py` |
| Fail-closed production configuration | 🟢 | `platform/config.py::_assert_production_safe` |

### 4.3 Database — implemented

| Element | Status | Evidence |
| --- | --- | --- |
| PostgreSQL, SQLAlchemy 2.0, schema-per-context boundary | 🟢 | `identity`, `curriculum_studio`, `learning`, `ops` schemas |
| Alembic migrations, reversible | 🟢 | `0001_initial_curriculum_studio`, `0002_learning`, `0003_ops`, `0004_identity`; round trip verified on PostgreSQL 16 |
| ORM ↔ migration parity guard | 🟢 | `tests/test_schema_parity.py` (PostgreSQL-gated) |
| Optimistic locking → retryable `409`, never `500` | 🟢 | `version_id_col` + `test_studio_conflict.py`, `test_session_state_conflict.py` |
| Append-only tables (consent, audit) enforced by port shape | 🟢 | `identity/application/ports.py` has no update or delete |
| In-memory SQLite for local/dev; PostgreSQL required in production | 🟢 | `main.py`, `_assert_production_safe` |
| Backup / restore / point-in-time recovery | 🔴 | [`docs/02-architecture/56-bcdr-plan.md`](docs/02-architecture/56-bcdr-plan.md) is a plan; nothing operational exists |

### 4.4 Architecture principles — status

| Principle | Status | Note |
| --- | --- | --- |
| Domain-driven design with real bounded contexts | 🟢 | Contexts share no ORM base; cross-context reads go through explicit read models |
| Hexagonal / ports-and-adapters | 🟢 | Domain has zero framework imports |
| Deny-by-default authorization | 🟢 | `pdp.authorize` returns deny for anything not explicitly allowed |
| Fail-closed safety controls | 🟢 | Kill switch reads fail closed; config refuses insecure production boot |
| Auditability | 🟡 | Identity audit trail complete; **learning-side and safeguarding audit trails are not** |
| Governance gates in code | 🟡 | Curriculum 9-gate review and consent gate enforced; M-Gov/M-Safe are human gates with no software representation |

---

## 5. Student Experience

### 5.1 Student onboarding

| Feature | Status | Evidence / gap |
| --- | --- | --- |
| Account creation by a guardian | 🟢 | `POST /v1/identity/learners` |
| Guardian association (mandatory, no orphan learners) | 🟢 | Foreign key + `ON DELETE CASCADE`, `identity.learner_account` |
| Consent required before first sign-in | 🟢 | `sign_in_learner` consent gate; `test_a_learner_without_consent_cannot_sign_in` |
| Child-safe sign-in (family code + name + PIN) | 🟢 | `POST /v1/identity/learners:signin` |
| Device binding | 🟢 | `known_devices`, bounded to 5, most recent first |
| Grade / age placement at enrolment | 🟢 | `grade_band`, `grade_level` (KG–12) |
| Student profile screen | 🟡 | `/student/profile` exists but reads the dev-stub learner, not the identity API |
| **Onboarding UI (join, consent, sign-in screens)** | 🔴 | No `/join`, `/consent`, or `/signin` route exists. The API is complete; the journey has no interface |
| Diagnostic placement assessment | 🔴 | Not implemented. Grade is declared by the guardian, not measured |

### 5.2 Student dashboard

| Feature | Status | Evidence |
| --- | --- | --- |
| Today's plan | 🟢 | `GET /v1/learning/students/{ref}/today`, `/student/today` |
| Continue learning / resume session | 🟢 | Session lifecycle endpoints; `/student/session` |
| Progress overview | 🟢 | `GET .../progress`, `/student/progress` |
| Achievements | 🟢 | `GET .../achievements` |
| Streaks | 🟢 | Derived in `student_queries`, surfaced to guardian and student |
| Learning history | 🟢 | `GET .../history` |
| Homework | 🟢 | `GET .../homework`, `/student/homework` |
| Spaced review queue | 🟢 | `GET .../reviews`, driven by `HalfLifeForgettingModel` |
| Timetable | 🟢 | `GET .../timetable` |
| Notifications with read state | 🟢 | `GET .../notifications`, `POST .../notifications/{id}:read` |
| Recommendations | 🟢 | `GET .../recommendations` |
| Offline status indicator | 🟢 | `OfflineBadge`, `SyncStatusBadge` |
| Subject browsing | 🟢 | `/student/subjects` |

Every one of these read models is implemented and tested **against synthetic data**. None has ever
rendered a real published lesson, because none exists (§6.3).

### 5.3 Learning journey and progression

| Feature | Status | Evidence |
| --- | --- | --- |
| Curriculum graph (objectives, prerequisites) | 🟢 | `domain/decision.py::CurriculumGraph`, built from published curriculum |
| Adaptive next-step selection | 🟢 | `DecisionConfig` + decision graph; `POST /sessions/{id}:next` |
| Mastery estimation (Bayesian Knowledge Tracing) | 🟢 | `domain/estimator.py::BKTEstimator`, `test_learning_domain.py` |
| Forgetting / decay model | 🟢 | `domain/forgetting.py::HalfLifeForgettingModel` |
| Misconception detection | 🟢 | `domain/scorer.py`, counter `taleem_misconceptions_detected_total` |
| Recommendations | 🟢 | `application/analytics.py` |
| Learning-path visualisation for the learner | 🔴 | Data exists; no UI presents a path |

### 5.4 Lesson experience

| Feature | Status | Evidence / gap |
| --- | --- | --- |
| Lesson session lifecycle | 🟢 | `create`, `:next`, `:teach`, `:hint`, `:explain`, `:answer`, `:end` |
| Text content delivery | 🟢 | `LessonView` read model |
| Explanation styles adapted to attempts and mastery | 🟢 | `ai_teacher.explain` style resolution |
| Hints with escalation after repeated failure | 🟢 | `consecutive_failures >= 3` escalates |
| Answer scoring and feedback | 🟢 | `domain/scorer.py` |
| **Visual content (images, diagrams)** | 🔴 | No media pipeline, no uploads, no CDN. `docs/02-architecture/34-media-architecture.md` is a design |
| **Interactive activities** | 🔴 | Assessment blueprints model item types; no interactive activity runtime exists in the web app |
| **Audio narration** | 🔴 | Zero audio assets in the repository; no TTS integration |
| **Lesson player UI** | 🟡 | `/student/session` drives the session API but renders text only |

### 5.5 Progress and analytics

| Feature | Status | Evidence |
| --- | --- | --- |
| Objective completion tracking | 🟢 | `learning` schema, durable |
| Mastery per objective with confidence | 🟢 | `domain/knowledge.py::StudentKnowledge` |
| Knowledge growth over time | 🟢 | `application/analytics.py`, surfaced in the Guardian Portal |
| Durable assessment evidence, idempotent under replay | 🟢 | `sync_consumer.py`, `test_sync_evidence.py` |
| Learning analytics events (outbox) | 🟢 | `LearningOutboxRow`; no consumer/warehouse yet |

---

## 6. Curriculum System

### 6.1 Curriculum architecture — implemented

Entities in [`contexts/curriculum_studio/domain/`](services/core-api/src/taleem_core/contexts/curriculum_studio/domain/):

- **Hierarchy** — subject → grade → unit → lesson → objective (`hierarchy.py`).
- **Lesson** — content blocks, objectives, metadata, versioning (`lesson.py`, `content.py`).
- **Assessment blueprint** — item types, coverage per objective (`assessment.py`).
- **AI teaching metadata** — what the teaching engine may say about this lesson (`ai_teaching.py`).
- **Provenance** — derivation, source, licence, aligned SLO codes (`provenance.py`).
- **Quality** — 9 named gates (`quality.py`).
- **Workflow** — 10 states, 6 actions, stage-ordered review (`workflow.py`).
- **Versioning** — immutable published versions with rollback (`versioning.py`).

Reference: [`CURRICULUM_FRAMEWORK.md`](CURRICULUM_FRAMEWORK.md),
[`docs/05-education/21-curriculum-engine.md`](docs/05-education/21-curriculum-engine.md).

### 6.2 Curriculum Studio platform — implemented

See §7 for the full breakdown. Ten endpoints under `/v1/studio`, covering authoring, validation,
submission, five-stage review, publication, version listing, and rollback.

### 6.3 Curriculum content — this is the critical gap

**The platform can hold a curriculum. There is no curriculum in it.**

| Item | Status | Reality |
| --- | --- | --- |
| Grade 4 subject design documents | 🟢 | 6 markdown documents in [`curriculum/grade-4/`](curriculum/grade-4/) plus [`GRADE4_MATH_CURRICULUM.md`](GRADE4_MATH_CURRICULUM.md) — **design artefacts, not authored lessons** |
| One end-to-end lesson expressed as code | 🟢 | `vertical_slice/fractions_lesson.py` — a fixture proving the pipeline, seeded only in tests |
| **Lessons authored, reviewed, and published in a database** | 🔴 | **Zero.** No environment contains a published lesson |
| Lesson audio | 🔴 | **Zero audio files exist in this repository** |
| Grades other than 4 | 🔴 | Not started |
| Ingestion / authoring pipeline from the design documents | 🔴 | [`curriculum-research/04_CURRICULUM_INGESTION_PIPELINE.md`](curriculum-research/04_CURRICULUM_INGESTION_PIPELINE.md) specifies it; no implementation |

### 6.4 Licensing, copyright, and provenance — decided, enforced in code

The rule, from [`curriculum-research/02_MASTER_CURRICULUM_MATRIX.md`](curriculum-research/02_MASTER_CURRICULUM_MATRIX.md)
and enforced by `domain/provenance.py`:

- **Default derivation is `authored-original`.** Content is written for Taleem and aligned to the
  *kind* of outcome the National Curriculum Progression Grid describes.
- **Verbatim government SLO text is copyright-reserved and must not be reproduced.** Authoritative
  SLO population happens only under an NCC/MoFEPT memorandum of understanding.
- **Ingestion is permitted only for open-licensed material or material covered by that MoU**
  (`Derivation.INGESTED` with a `permission_ref`).
- **Prohibited sources are refused by the validator**, not by convention: textbook scans and named
  unofficial repositories are blocked by `PROHIBITED_SOURCE_MARKERS`.

This document makes no recommendation to copy protected educational content, and the platform is
built to refuse it.

**Outstanding:** the NCC/MoFEPT MoU does not exist. Until it does, Taleem's curriculum is
original-authored-and-aligned only, which is workable but slower.

---

## 7. Curriculum Authoring Studio

| Capability | Status | Evidence |
| --- | --- | --- |
| Browse curriculum hierarchy | 🟢 | `GET /v1/studio/hierarchy` |
| Create and edit lesson drafts | 🟢 | `POST /v1/studio/lessons`, `GET /v1/studio/lessons/{id}` |
| Learning objective authoring | 🟢 | `domain/hierarchy.py`, part of the lesson aggregate |
| Activity and content-block authoring | 🟢 | `domain/content.py` |
| Assessment blueprint authoring | 🟢 | `domain/assessment.py` |
| Automated validation before submission | 🟢 | `POST .../{id}:validate` — 4 automated gates (alignment, accessibility, readability, performance) |
| Submit into review | 🟢 | `POST .../{id}:submit` |
| Five-stage human review with no self-approval | 🟢 | `POST .../{id}:review`; enforced in both PDP and domain |
| Nine quality gates, all green required to publish | 🟢 | `quality.py::all_gates_green` |
| Publish | 🟢 | `POST .../{id}:publish` (curriculum architect only) |
| Version history | 🟢 | `GET .../{id}/versions` |
| Rollback to a previous version | 🟢 | `POST .../{id}:rollback` |
| Provenance and licence gate | 🟢 | `provenance.py::check_provenance` |
| Optimistic-lock conflict handling | 🟢 | `409` with retry semantics, `test_studio_conflict.py` |
| Audit history of transitions | 🟢 | `TransitionRecord` per workflow move |
| **Studio web UI** | 🟡 | `/studio` exists as a console shell (`StudioConsole.tsx`); it is not a full authoring environment |
| **Content preview as a learner would see it** | 🔴 | Not implemented |
| **Media upload (images, audio) into a lesson** | 🔴 | Zero `UploadFile` occurrences in the backend; the capability does not exist |
| **Bulk import from the markdown design documents** | 🔴 | Not implemented |

---

## 8. AI Teacher

### 8.1 Current state — a deterministic engine, and it says so

**There is no language model anywhere in the running system.** This must not be overstated in any
investor, partner, or user-facing material.

What exists:

- A **templated teaching runtime** (`domain/runtime.py`) that composes utterances from published
  lesson content using fixed templates in Urdu and English.
- An **explainable decision layer** (`domain/ai_teacher.py`) selecting explanation style from the
  learner's attempt count, mastery estimate, and recent errors, and emitting a confidence annotation
  plus an escalation flag after three consecutive failures.
- A **curriculum grounding boundary**: the engine can only speak about a `LessonView` that is
  currently published. An objective with no published lesson returns `404`, not an invention.
- Endpoints: `POST /v1/learning/sessions/{id}:teach`, `:hint`, `:explain`;
  `GET /v1/learning/students/{ref}/ai-teacher/plan` and `/capabilities`.

What exists but is **not connected**:

- `ports/llm.py` defines the `LLMProvider` port, `LLMRequest`/`LLMResponse`, a four-tier model
  routing policy (`light`, `standard`, `deep`, `safety`) where safety never yields to cost, and a
  `StubLLMProvider` documented as "deterministic, offline, **NON-production**".
- **The port is referenced only by `tests/test_ports.py`.** It is not wired into
  `AITeacherService` or into `main.py`. The abstraction is proven to compile; it teaches nobody.

Design references: [`AI_TEACHER_ARCHITECTURE.md`](AI_TEACHER_ARCHITECTURE.md),
[`AI_TEACHER_INTERACTION_MODEL.md`](AI_TEACHER_INTERACTION_MODEL.md),
[`AI_TEACHER_SAFETY_MODEL.md`](AI_TEACHER_SAFETY_MODEL.md),
[`AI_TEACHER_EVALUATION.md`](AI_TEACHER_EVALUATION.md),
[`AI_TEACHER_OFFLINE.md`](AI_TEACHER_OFFLINE.md),
[`docs/05-education/24-ai-teacher-specification.md`](docs/05-education/24-ai-teacher-specification.md).

### 8.2 Future scope

| Capability | Status |
| --- | --- |
| Curriculum-grounded generation (retrieval limited to published lessons) | 🔴 |
| Lesson-aware tutoring turns | 🟡 (templated today) |
| Student-context-aware explanation (mastery, errors, grade band) | 🟢 (deterministic) |
| Adaptive re-explanation in a different style | 🟢 (deterministic, fixed template set) |
| Free-form learner questions | 🔴 |
| Assessment assistance and worked solutions | 🔴 |
| Learning recommendations | 🟢 (analytics-driven, not generated) |

### 8.3 Safety requirements — specified, mostly unimplemented

| Requirement | Status | Note |
| --- | --- | --- |
| Curriculum grounding boundary | 🟢 | Enforced structurally today |
| No unsafe advice / age-appropriate output | 🟡 | Trivially true for fixed templates; **unproven for any generative path** |
| Hallucination controls | 🔴 | Not applicable today; required before any model is connected |
| Distress detection and escalation to a human | 🔴 | Tier routing policy exists (`route_tier` sends distress-adjacent turns to the strongest tier); **no detector and no human queue exist** |
| Transcript retention and review | 🔴 | Not implemented |
| Guardian visibility of AI activity | 🟡 | Guardian Portal exposes `ai_teacher_activity` derived from the deterministic engine |
| Per-feature guardian consent for AI teaching | 🟢 | `ConsentScope.AI_TEACHING` is separable and withdrawable |
| Auditability of AI turns | 🔴 | Not implemented |
| Kill switch halts child-facing AI traffic | 🟢 | `/v1/learning/sessions` is child-facing |

### 8.4 AI architecture — the intended shape

- **AI gateway.** All model traffic goes through the `LLMProvider` port. No product code calls a
  vendor SDK directly, so a provider or residency change is a composition-root edit.
- **Model independence.** Tiering is a routing policy on the port, not scattered call sites.
- **Prompt and data boundary.** Prompts carry curriculum grounding and pseudonymous learner context
  — never a child's name, address, or contact detail, none of which the platform stores.
- **Retrieval grounding.** Constrained to currently-published `LessonView` objects, which is already
  the boundary the deterministic engine respects.

**Explicit constraints honoured in this repository:** no paid AI provider is connected, no paid
account exists, no API key is configured, and no charge has been incurred. Provider selection is
blocked on **FD-03** (LLM inference residency and zero-retention) in
[`FOUNDER_DECISIONS.md`](FOUNDER_DECISIONS.md) — a founder and legal decision, not an engineering one.

---

## 9. Guardian Portal

### 9.1 Guardian dashboard

| Feature | Status | Evidence |
| --- | --- | --- |
| Multiple children under one guardian | 🟢 | `GET /v1/guardian/dashboard`, up to 12 learners |
| Per-child learning progress | 🟢 | `GET /v1/guardian/children/{ref}` |
| Attendance | 🟢 | Derived in `guardian_service.py` |
| Learning timeline | 🟢 | Same |
| Weekly summaries | 🟢 | Same |
| Knowledge growth | 🟢 | From `LearningAnalytics` |
| Assessment history | 🟢 | From student read models |
| AI Teacher activity | 🟢 | From the deterministic engine |
| Recommendations | 🟢 | From `LearningAnalytics` |
| Intervention notifications | 🟢 | Derived; **display only — no delivery channel** |
| Offline synchronisation status | 🟢 | Surfaced per child |
| Streaks and achievements | 🟢 | Derived |
| Guardian web UI | 🟡 | `/guardian` and `/guardian/children/[studentRef]` exist, wired to the dev-token stub |

Reference: [`GUARDIAN_EXPERIENCE.md`](GUARDIAN_EXPERIENCE.md),
[`GUARDIAN_PORTAL_REPORT.md`](GUARDIAN_PORTAL_REPORT.md).

### 9.2 Guardian controls

| Control | Status | Evidence |
| --- | --- | --- |
| Enrol a child | 🟢 | `POST /v1/identity/learners` |
| Reset a child's PIN / unlock a locked child | 🟢 | `POST /v1/identity/learners/{ref}/pin:reset` |
| Grant consent, per scope | 🟢 | `POST /v1/identity/consents` |
| Withdraw consent, wholly or per scope | 🟢 | `POST /v1/identity/consents:withdraw` |
| Read the consent history | 🟢 | `GET /v1/identity/consents/{ref}` |
| Read the family audit trail | 🟢 | `GET /v1/identity/audit` |
| **Guardian consent and control UI** | 🔴 | The API is complete; no screen exists |
| Notification preferences | 🔴 | Not implemented |
| Data export / deletion request | 🔴 | Not implemented (§18) |

**Deliberate non-capability.** A guardian is **read-only over learning data**. They cannot alter a
child's mastery, answers, or history. This is an integrity property, not a missing feature.

---

## 10. Authentication & Identity

### 10.1 Current implementation

| Element | Status | Evidence |
| --- | --- | --- |
| EdDSA / Ed25519 asymmetric token signing | 🟢 | `auth/keys.py`, `auth/jwt_verifier.py` |
| Kid-addressed rotating key set, overlap rotation (no flag day) | 🟢 | `KeySet.by_kid`, `with_key` |
| JWKS discovery endpoint | 🟢 | `GET /.well-known/jwks.json` |
| Issuer / audience binding, enforced in production | 🟢 | `auth/setup.py` |
| Production is asymmetric-only (HS256 refused) | 🟢 | `test_auth_asymmetric.py` |
| Alg-confusion and `none`-alg defence | 🟢 | `TokenVerifier.verify` rejects disallowed algorithms |
| Deny-by-default PDP | 🟢 | `auth/pdp.py` |
| IDOR guards on every learner-scoped route | 🟢 | `require_owner_or`, `_require_own_learner` |
| **Guardian account lifecycle** | 🟢 | `identity` context (commit `23747f9`) |
| **Verifiable guardian consent** | 🟢 | Same |
| **Child-safe sign-in journey** | 🟢 | Same |
| **Token issuance** | 🟢 | `identity/application/tokens.py` — the only place that mints a token |
| Durable per-account lockout | 🟢 | 5 wrong PINs, 10 wrong passphrases |
| Per-client rate limiting on public routes | 🟡 | `adapters/rate_limit.py` — **process-local by design and documented as such**; a shared-cache implementation is required for multi-instance deployment |
| Session management (refresh, revocation list) | 🟡 | Short TTLs (10 min learner, 60 min guardian) bound the risk; **there is no refresh token and no revocation list** |

### 10.2 Development authentication

HS256 with a well-known dev secret, available only outside production. `platform/config.py` refuses
to start a production instance without a real Ed25519 seed, a real PostgreSQL URL, a non-default
offline signing seed, and a KDF work factor at or above the OWASP minimum.

The **frontend** still carries `NEXT_PUBLIC_DEV_STUDENT_TOKEN` and `NEXT_PUBLIC_DEV_GUARDIAN_TOKEN`
stubs. This is the single largest remaining wiring gap and is the immediate next task (§24).

### 10.3 Production authentication — what remains

| Item | Status |
| --- | --- |
| Rewire the web app from dev tokens to the identity API | 🔴 |
| Sign-in, join, and consent screens | 🔴 |
| KMS/HSM-held signing keys (**FD-14**) | ⚫ Blocked on a founder/security decision |
| Refresh tokens and explicit revocation | 🔴 |
| Distributed rate limiting behind a shared cache | 🔴 |
| Guardian email verification | 🔴 |
| Account recovery for a guardian who forgets their passphrase | 🔴 |
| Mentor and administrator identity provisioning | 🔴 |

---

## 11. Child Safety & Consent

**This section governs whether the system may be used by a real child. Today the answer is no.**

### 11.1 What is implemented

| Control | Status | Evidence |
| --- | --- | --- |
| A child has no email, phone, date of birth, or address | 🟢 | `identity.learner_account` has no such column; migration `0004_identity` |
| No child sign-in without live guardian consent | 🟢 | `sign_in_learner` gate; fails closed |
| Consent is append-only evidence with policy version and capture method | 🟢 | `identity.consent_record`; ports expose no update or delete |
| Consent scopes are separable and independently withdrawable | 🟢 | `learning_data`, `ai_teaching`, `voice_audio`, `progress_sharing` |
| Withdrawal takes effect on the next request | 🟢 | Derived state read per sign-in, not cached in a claim |
| Superseded policy version invalidates consent for the sign-in gate | 🟢 | `ConsentState.is_current` |
| Guardian IP and user agent hashed, never stored raw | 🟢 | `identity_api._hash_context` |
| Append-only identity audit trail, guardian-readable | 🟢 | `identity.audit_event` |
| Operators cannot consent on a guardian's behalf | 🟢 | Asserted by test |
| Kill switch halts child sign-in but not guardian consent withdrawal | 🟢 | `platform/kill_switch.py` |
| Data minimisation in tokens (refs and role only) | 🟢 | `tokens.py` |

### 11.2 What is not implemented — production blockers

| Requirement | Status | Owner |
| --- | --- | --- |
| **M-Gov**: DPIA signed, consent model approved, mandatory-reporting policy, external safety review, data residency decided | ⚫ | DPO / legal / founder |
| **M-Safe**: distress→human within SLA proven in a drill, reporting workflow tested, on-call staffed | ⚫ | Safeguarding lead |
| Distress detection in learner input | 🔴 | Engineering, after M-Gov |
| Safeguarding triage queue and reviewer console | 🔴 | Engineering |
| Abuse reporting route for a child or guardian | 🔴 | Engineering |
| Age verification beyond guardian declaration | 🔴 | Product / legal |
| Data retention schedule and automated purge | 🔴 | Engineering + legal |
| Subject access, export, and erasure workflows | 🔴 | Engineering + legal |
| Independent child-safety review of the AI path | ⚫ | External reviewer |

**Standing position:** [`GO_NO_GO_DECISION.md`](GO_NO_GO_DECISION.md) records **NO-GO for Pilot 1
with real children** until M-Gov and M-Safe close. [`FINAL_READINESS_REPORT.md`](FINAL_READINESS_REPORT.md)
records **NOT READY** for the Pilot 0 dry run. Nothing in the repository shows either has changed.
See also [`docs/03-security-privacy/`](docs/03-security-privacy/) and
[`INCIDENT_RESPONSE.md`](INCIDENT_RESPONSE.md).

---

## 12. Offline-First Learning

Specifications: [`OFFLINE_ARCHITECTURE.md`](OFFLINE_ARCHITECTURE.md),
[`OFFLINE_STORAGE_SPEC.md`](OFFLINE_STORAGE_SPEC.md), [`OFFLINE_SYNC_SPEC.md`](OFFLINE_SYNC_SPEC.md),
[`OFFLINE_SECURITY_REVIEW.md`](OFFLINE_SECURITY_REVIEW.md), [`OFFLINE_TEST_PLAN.md`](OFFLINE_TEST_PLAN.md).

| Capability | Status | Evidence |
| --- | --- | --- |
| Service worker, app shell caching, install as a PWA | 🟢 | `apps/web/public/sw.js`, `manifest.webmanifest` |
| Content-hashed offline lesson packages | 🟢 | `GET /v1/offline/packages`, `packages/{lesson_id}` |
| Ed25519 package signing (server) and verification (client) | 🟢 | `package_signer.py`, `lib/offline/signature.ts`, `GET /v1/offline/signing-keys` |
| IndexedDB storage with LRU eviction and purge | 🟢 | `lib/offline/idb.ts`, `purge.ts` |
| Download manager | 🟢 | `lib/offline/packages.ts` |
| Outbound sync queue with background drain | 🟢 | `lib/offline/syncQueue.ts`, `backgroundSync.ts` |
| Durable, idempotent server-side sync | 🟢 | `POST /v1/sync/batch`, `sync_consumer.py`, evidence table |
| Conflict policy per delta type | 🟢 | `contexts/sync/domain.py` (monotonic max, idempotent set, server-order-wins) |
| Crash recovery mid-sync | 🟢 | `syncCrashRecovery.test.ts` |
| Reconciliation after divergence | 🟢 | `reconcile.test.ts` |
| Cache versioning across releases | 🟢 | `cacheVersion.ts` |
| Connectivity detection and freshness display | 🟢 | `connectivity.ts`, `SyncStatusBadge` |
| Chaos / fault-injection harness | 🟢 | `lib/offline/chaos.ts`, `chaos.test.ts` |
| Diagnostics | 🟢 | `lib/offline/diagnostics.ts` |
| **Per-route service-worker precaching** | 🔴 | Root shell only |
| **Offline audio packaging** | 🔴 | No audio exists to package |
| **On-device validation on real low-end Android** | 🔴 | Never performed; last device notes are [`DEVICE_PREPARATION.md`](DEVICE_PREPARATION.md) |
| **Low-bandwidth measurement (2G/3G budgets)** | 🔴 | Budgets specified in [`docs/01-product/04-non-functional-requirements.md`](docs/01-product/04-non-functional-requirements.md); never measured |

Offline is the most thoroughly *unit-tested* subsystem in the project (90 frontend tests) and the
least *field-tested*.

---

## 13. Accessibility & Localization

Requirements: [`docs/04-design/16-accessibility-standards.md`](docs/04-design/16-accessibility-standards.md).

| Requirement | Status | Evidence / gap |
| --- | --- | --- |
| WCAG 2.2 AA as a release gate | 🟡 | Specified and partly built into components; **never audited** |
| RTL layout by default | 🟢 | `<html lang="ur" dir="rtl">`; RTL-mirrored navigation |
| Urdu-first interface copy | 🟢 | Urdu strings throughout the student shell; `platform/i18n.py` server-side |
| English support | 🟡 | Locale field exists end to end; no English UI translation set |
| Semantic landmarks, `aria-current`, `aria-live`, `aria-label` | 🟢 | `BottomNav`, `OfflineBadge`, `AppShell`, `ui.tsx` |
| Read-aloud affordance | 🟡 | `ReadAloud` component exists as an interface with **no audio behind it** |
| Keyboard navigation | 🟡 | Native controls used throughout; **no keyboard traversal test** |
| Screen-reader validation (TalkBack, NVDA) | 🔴 | Never performed |
| Automated accessibility testing in CI (axe or equivalent) | 🔴 | Not present |
| Responsive design for small, low-DPI screens | 🟡 | Token-based spacing and thumb-reachable navigation; unmeasured on real devices |
| Colour contrast verification | 🔴 | Tokens defined in `design-system/tokens.css`; contrast never measured |
| Low-bandwidth accessibility | 🟡 | Offline architecture serves this; unmeasured |

**Accepted gap.** The components were built to accessibility guidance, but *built to* is not
*verified as*. No assistive-technology session and no automated audit has been run. The audit is
scheduled after the screens land (WS11 in [`ROADMAP.md`](ROADMAP.md)).

---

## 14. Audio & Voice Learning

The product is designed audio-first — for children with limited literacy, audio is not an
enhancement, it is the interface. Design: [`AUDIO_SCRIPT_GUIDE.md`](AUDIO_SCRIPT_GUIDE.md),
[`CONTENT_PRODUCTION_PIPELINE.md`](CONTENT_PRODUCTION_PIPELINE.md),
[`docs/02-architecture/34-media-architecture.md`](docs/02-architecture/34-media-architecture.md).

| Capability | Status | Reality |
| --- | --- | --- |
| Audio script standards and QA checklist | 🟢 | Documented |
| **Any audio asset at all** | 🔴 | **Zero `.mp3`, `.wav`, `.m4a`, or `.ogg` files exist in this repository** |
| Lesson narration | 🔴 | Not started |
| Accessibility read-aloud with real speech | 🔴 | `ReadAloud` is a button with no engine behind it |
| Text-to-speech for Urdu | 🔴 | Not integrated. A platform speech engine is the zero-asset-cost path |
| Voice interaction (learner speaks) | 🔴 | Not started; requires `ConsentScope.VOICE_AUDIO` and an M-Gov decision |
| Offline audio packaging | 🔴 | Package format supports it; nothing to package |
| Media upload and storage pipeline | 🔴 | No `UploadFile` handling exists in the backend |

**Note on consent.** The consent vocabulary already carries `voice_audio` as a separable scope, so
audio can be shipped without forcing guardians into an all-or-nothing choice.

---

## 15. Assessments & Learning Analytics

References: [`docs/05-education/23-assessment-engine.md`](docs/05-education/23-assessment-engine.md),
[`docs/05-education/58-mastery-and-assessment-validity.md`](docs/05-education/58-mastery-and-assessment-validity.md).

| Capability | Status | Evidence |
| --- | --- | --- |
| Assessment blueprint per lesson | 🟢 | `domain/assessment.py` |
| Attempt submission and scoring | 🟢 | `POST /sessions/{id}:answer`, `domain/scorer.py` |
| Durable assessment evidence, idempotent under offline replay | 🟢 | `sync_consumer.py`, `test_sync_evidence.py` |
| Bayesian mastery estimation with confidence | 🟢 | `BKTEstimator` |
| Forgetting-curve-driven spaced review | 🟢 | `HalfLifeForgettingModel`, `GET .../reviews` |
| Misconception detection | 🟢 | `domain/scorer.py` |
| Progress and knowledge-growth analytics | 🟢 | `application/analytics.py` |
| Weekly summaries | 🟢 | Guardian Portal |
| Assessment history | 🟢 | `GET .../assessments` |
| **Summative examinations** | 🔴 | Formative loop only |
| **Auto-graded free-text or constructed response** | 🔴 | Not implemented |
| **Human grading workflow** | 🔴 | M6 scope |
| **Report card generation** | 🔴 | `docs/06-portals/29-reporting-system.md` specifies it; not implemented |
| **Grade promotion** | 🔴 | M6 scope |
| **Analytics warehouse / event consumer** | 🔴 | Outbox rows are written; nothing consumes them |
| **Psychometric validity work** | 🔴 | Specified in doc 58; not started |

---

## 16. Notifications & Interventions

| Capability | Status | Evidence / gap |
| --- | --- | --- |
| In-app learner notifications with read state | 🟢 | `GET .../notifications`, `POST .../notifications/{id}:read` |
| Intervention detection (a child falling behind) | 🟢 | Derived in `guardian_service.py` |
| Guardian-visible intervention alerts | 🟢 | Guardian Portal `intervention_notifications` |
| **Delivery channels (push, SMS, email)** | 🔴 | None. Notifications are visible only when the user opens the app |
| **Learning reminders / scheduling** | 🔴 | Not implemented |
| **Notification preferences** | 🔴 | Not implemented |
| **Guardian escalation when a child is inactive** | 🔴 | Detected, never delivered |

For families sharing one phone with intermittent data, in-app-only delivery is a genuine product
gap, not merely a missing integration. SMS is the realistic channel and requires a cost decision.

---

## 17. Security

Evidence base: [`OFFLINE_SECURITY_REVIEW.md`](OFFLINE_SECURITY_REVIEW.md),
[`VERIFICATION_BLOCKER_1_AUTH.md`](VERIFICATION_BLOCKER_1_AUTH.md),
`tests/test_attack_hardening.py`, `tests/test_auth.py`, `tests/test_auth_asymmetric.py`,
`tests/test_security_headers.py`, `tests/test_cors.py`.

| Control | Status | Evidence |
| --- | --- | --- |
| Asymmetric token signing with rotating JWKS | 🟢 | §10.1 |
| Deny-by-default authorization (PDP) | 🟢 | `auth/pdp.py` |
| IDOR protection on every learner-scoped route | 🟢 | `require_owner_or`, ownership re-derivation |
| Privilege-escalation resistance (role from token, never body) | 🟢 | `test_identity_api.py`, `test_guardian_api.py` |
| Token validation: alg confusion, `none`, expiry, `nbf`, `iss`, `aud` | 🟢 | `jwt_verifier.py` + tests |
| Request validation and payload bounds | 🟢 | Pydantic models with explicit `max_length` |
| Security headers | 🟢 | `platform/security_headers.py` |
| CORS: exact-origin allowlist, never `*` | 🟢 | `main.py`, `test_cors.py` |
| Uniform, non-enumerating error responses | 🟢 | `forbidden()`, uniform sign-in failure |
| Credential storage: PBKDF2-HMAC-SHA256, per-secret salt, constant-time compare | 🟢 | `identity/domain/credentials.py` |
| Production floor on the KDF work factor | 🟢 | `_assert_production_safe` |
| Durable account lockout | 🟢 | §10.1 |
| Fail-closed configuration | 🟢 | `platform/config.py` |
| Identity audit logging | 🟢 | `identity.audit_event` |
| Monitoring and golden signals | 🟢 | `GET /metrics`, `GET /v1/ops/status` |
| Rate limiting | 🟡 | Process-local; needs a shared store for multi-instance |
| Secret management | 🟡 | Environment variables only; **no KMS/HSM (FD-14)** |
| **External penetration test** | 🔴 | Never performed |
| **Dependency and container vulnerability scanning in CI** | 🔴 | Not present |
| **Learning-side and safeguarding audit trails** | 🔴 | Only identity is audited |

---

## 18. Privacy

| Requirement | Status | Evidence / gap |
| --- | --- | --- |
| Data minimisation for children | 🟢 | No child email, phone, date of birth, or address anywhere in the schema |
| Pseudonymous identifiers throughout | 🟢 | `student_ref`, `guardian_ref` opaque and unguessable |
| No PII in tokens | 🟢 | `tokens.py` — refs and role only |
| No PII in the audit trail | 🟢 | Refs and hashed context only |
| Guardian contact data limited to one email | 🟢 | `identity.guardian_account` |
| Consent recorded with policy version and evidence | 🟢 | §11.1 |
| Log redaction | 🟢 | `platform/logging.py` |
| **DPIA** | ⚫ | M-Gov; not signed |
| **Data retention schedule and automated purge** | 🔴 | Not implemented |
| **Subject access / export** | 🔴 | Not implemented |
| **Erasure ("delete my child's data")** | 🔴 | Not implemented. `ON DELETE CASCADE` exists at the identity layer, but learning data is in a separate schema and is not cascaded |
| **Data residency determination (FD-01 / FD-02)** | ⚫ | Founder and legal decision |
| **Privacy notice as a published artefact** | 🔴 | A policy *version string* is enforced; the policy text itself is not in the repository |

The last two rows matter: the consent gate enforces agreement to `2026-09-consent-v1`, but the
document that version identifies **does not yet exist**. Writing and approving it is an M-Gov task.

---

## 19. Administration & Operations

| Capability | Status | Evidence |
| --- | --- | --- |
| Liveness and readiness probes | 🟢 | `GET /health`, `GET /health/ready` |
| Prometheus metrics | 🟢 | `GET /metrics` |
| Operational status summary | 🟢 | `GET /v1/ops/status` |
| Operator kill switch, shared across instances, fails closed | 🟢 | `GET/POST /v1/ops/kill-switch*`, `ops.kill_switch` table |
| Structured logs with correlation IDs | 🟢 | `platform/logging.py`, `platform/correlation.py` |
| Pilot 0 synthetic-user simulator | 🟢 | `tools/pilot_simulator.py`, `make simulate` |
| Reversible migrations, runnable out of band | 🟢 | Alembic (`upgrade head` → `downgrade base` → `upgrade head` verified on PostgreSQL 16) + `.github/workflows/migrate.yml` |
| CI: code, docs, devcontainer | 🟢 | `.github/workflows/` |
| Cloud development environment | 🟢 | `.devcontainer/`, GitHub Codespaces |
| Runbooks and incident response | 🟢 (documented) | [`MONITORING_RUNBOOK.md`](MONITORING_RUNBOOK.md), [`INCIDENT_RESPONSE.md`](INCIDENT_RESPONSE.md), [`PILOT_RUNBOOK.md`](PILOT_RUNBOOK.md) |
| Deployment configuration | 🟡 | Vercel (`vercel.json`, `api/index.py`, build-step migrations via `scripts/vercel_migrate.py`); also `render.yaml`, Railway manifests, Terraform scaffold |
| **A verified live environment** | 🔴 | No live URL is recorded in this repository and none is asserted here. The last verified environment (Railway) went down around 2026-08-31; see [`CURRENT_PROJECT_STATUS.md`](CURRENT_PROJECT_STATUS.md) §4–5 |
| **Backup and restore** | 🔴 | [`docs/02-architecture/56-bcdr-plan.md`](docs/02-architecture/56-bcdr-plan.md) is a plan; nothing operational |
| **Alerting on the golden signals** | 🔴 | Metrics exposed; no alert rules, no destination |
| **On-call rotation** | ⚫ | M-Safe; staffing decision |

---

## 20. Implementation Matrix

Status key: 🟢 complete · 🟡 partial · 🔴 not started · ⚫ governance, legal, or human decision.

| Product Area | Scope | Status | Evidence | Remaining Work | Blockers |
| --- | --- | --- | --- | --- | --- |
| Platform core | Hexagonal domain, config, logging, metrics, errors, i18n, flags | 🟢 | `platform/*`, `test_platform.py`, strict `mypy` on 135 files | — | — |
| Persistence | 4 schemas, 4 reversible migrations, ORM parity guard, optimistic locking | 🟢 | `alembic/versions/*`, `test_schema_parity.py` | Retention and erasure across schemas | — |
| Authentication (crypto) | EdDSA, rotating JWKS, iss/aud binding, alg-confusion defence | 🟢 | `auth/*`, `test_auth_asymmetric.py` | KMS-held keys | ⚫ FD-14 |
| Authorization | Deny-by-default PDP, IDOR guards, no self-approval | 🟢 | `auth/pdp.py`, `test_attack_hardening.py` | Mentor and admin roles | — |
| Identity & consent | Guardian accounts, enrolment, consent evidence, child sign-in, audit | 🟢 | `contexts/identity/*`, 65 tests, `identity.openapi.yaml` | Web UI, refresh tokens, email verification | — |
| Curriculum Studio (platform) | Authoring, 9 gates, 5-stage review, publish, version, rollback, provenance | 🟢 | `contexts/curriculum_studio/*`, `test_studio_*.py` | Full authoring UI, preview, media upload, bulk import | — |
| Curriculum content | Published lessons for real learners | 🔴 | 6 design documents; **zero published lessons** | Author, review, publish Grade 4; then other grades | ⚫ MoU for SLO text |
| Learning intelligence | Sessions, BKT mastery, forgetting, decision graph, misconceptions | 🟢 | `contexts/learning/domain/*`, `test_learning_domain.py` | — | — |
| Student read models | 11 derived views (today, homework, reviews, progress, …) | 🟢 | `student_api.py`, `test_student_api.py` | Render real content | Curriculum |
| Student web experience | Dashboard, session, progress, subjects, homework, profile | 🟡 | 8 routes | Rewire to identity API; onboarding screens; lesson player; activities | — |
| Lesson experience | Text, visual, interactive, audio | 🟡 | Text only | Visual pipeline, activity runtime, audio | Media + content |
| AI Teacher | Curriculum-grounded teaching, hints, explanations, plan | 🟡 | `domain/ai_teacher.py`; **templated, no LLM** | Wire the `LLMGateway` port, grounding, safety gates, evaluation | ⚫ FD-03 |
| Guardian Portal | Multi-child dashboard, progress, timeline, interventions | 🟢 (API) / 🟡 (UI) | `contexts/guardian/*`, 2 routes | Consent and control UI; rewire auth | — |
| Offline & PWA | Service worker, IndexedDB, packages, signed sync, chaos | 🟢 | `lib/offline/*`, 90 vitest tests | Per-route precaching, audio packaging, on-device validation | — |
| Assessments | Blueprints, scoring, evidence, mastery, spaced review | 🟢 | `test_sync_evidence.py`, `test_learning_domain.py` | Summative exams, free-text grading, report cards, promotion | — |
| Notifications | In-app with read state, intervention detection | 🟡 | `student_api.py`, `guardian_service.py` | Delivery channels, reminders, preferences | Cost decision |
| Accessibility | WCAG 2.2 AA, RTL, Urdu, keyboard, screen reader | 🟡 | RTL and ARIA present | Automated audit, AT session, contrast verification | — |
| Audio & voice | Narration, read-aloud, TTS, voice input | 🔴 | **Zero audio assets** | Everything | Content + FD-03 for voice |
| Security | Headers, CORS, validation, lockout, uniform errors, audit | 🟢 | 5 dedicated test modules | Pentest, dependency scanning, distributed rate limiting | ⚫ External test |
| Privacy | Minimisation, pseudonymity, no PII in tokens or logs | 🟡 | Schema and code | DPIA, retention, export, erasure, published policy text | ⚫ M-Gov |
| Child safety | Consent gate, kill switch, operator limits | 🟡 | `contexts/identity/*`, `kill_switch.py` | Distress detection, triage queue, abuse reporting | ⚫ M-Gov + M-Safe |
| Operations | Health, metrics, kill switch, runbooks, simulator, CI | 🟢 | `.github/workflows/`, `tools/pilot_simulator.py` | Alerting, backup, restore, on-call | ⚫ M-Safe |
| Deployment | Vercel functions, build-step migrations, devcontainer | 🟡 | `vercel.json`, `api/index.py` | Provision and verify a live environment | — |
| Administration | Admin portal, school/tenant management | 🔴 | — | All of it | Deferred to Pilot 3 |
| Mentor experience | Mentor console, assignment, human escalation target | 🔴 | PDP roles only | All of it | ⚫ M-Safe |

Percentages are deliberately omitted: there is no defensible way to compute them, and a false
precision would undermine the rest of this document.

---

## 21. Remaining Development Roadmap

Existing milestone numbering is preserved. M0–M11 and the RC1 packaging are complete per
[`CHANGELOG.md`](CHANGELOG.md) and the git tags; **M12 (identity, consent, child-safe sign-in)
landed at commit `23747f9`**. Phases A–H below cover everything that remains.

### Phase A — Core student experience (in progress)

- **Goal.** A real child, on a real device, signs in with their own credential and completes a
  lesson. Removes the last development stub from the product path.
- **Features.** Rewire `apps/web` from `NEXT_PUBLIC_DEV_*_TOKEN` to the identity API; join and
  consent screens for guardians; family-code and PIN sign-in for children with a tappable roster;
  session persistence and silent re-authentication; a real landing page; a lesson player that
  renders content blocks and activities.
- **Dependencies.** M12 (done).
- **Acceptance criteria.** No `NEXT_PUBLIC_DEV_*_TOKEN` remains in `apps/web`; a guardian can
  register, enrol, consent, and hand the device to a child who signs in unaided; withdrawing consent
  ends the child's next session; the landing page describes the product.
- **Tests required.** Component and integration tests for the sign-in and consent journeys; a
  regression test asserting the dev-token constants are gone; existing 90 vitest tests stay green.
- **Completion evidence.** Green `make gates`; a recorded end-to-end journey against a running API.

### Phase B — Curriculum and content platform

- **Goal.** Real, published, provenance-clean lessons in a database.
- **Features.** An ingestion tool that turns the `curriculum/grade-4/` design documents into Studio
  drafts; a Studio authoring UI beyond the current console; learner-view preview; media upload;
  publish the Grade 4 set through the full 5-stage review.
- **Dependencies.** Phase A for preview fidelity; nothing else.
- **Acceptance criteria.** At least one complete Grade 4 subject published with all 9 gates green
  and `Provenance.derivation == authored-original`; the student portal renders it end to end;
  offline packages build and verify for it.
- **Tests required.** Ingestion round-trip tests; provenance rejection tests for prohibited sources;
  package signature verification over real content.
- **Completion evidence.** A published lesson count greater than zero in a real database.

### Phase C — Complete guardian experience

- **Goal.** A guardian manages their family without an engineer.
- **Features.** Consent grant and withdrawal UI with per-scope control; learner management; PIN
  reset; the audit trail rendered readably; weekly summary presentation.
- **Dependencies.** Phase A.
- **Acceptance criteria.** Every `/v1/identity` and `/v1/guardian` capability is reachable from the
  UI; a guardian with limited literacy can complete consent in Urdu.
- **Tests required.** Journey tests per control; accessibility checks on the consent form.

### Phase D — AI Teacher

- **Goal.** Replace the templated engine with curriculum-grounded generation, safely, or make a
  documented decision not to.
- **Features.** Wire `LLMGateway` into `AITeacherService` behind a feature flag and the
  `ai_teaching` consent scope; retrieval restricted to published `LessonView` objects; a safety
  gate on every output; transcript retention and audit; an evaluation harness per
  [`AI_TEACHER_EVALUATION.md`](AI_TEACHER_EVALUATION.md); provider adapter that is inert without a key.
- **Dependencies.** Phase B (grounding needs content). **Blocked on FD-03** for any real provider.
- **Acceptance criteria.** With the flag off, behaviour is byte-identical to today. With it on and a
  stub provider, every output is traceable to a published lesson; ungrounded output is refused, not
  softened. No paid provider is connected without an explicit authorisation decision.
- **Tests required.** Grounding-boundary tests; refusal tests; safety-gate tests; a golden-set
  evaluation with a recorded score.

### Phase E — Audio and interactive learning

- **Goal.** The audio-first product actually speaks.
- **Features.** Urdu text-to-speech behind the existing `ReadAloud` affordance (platform speech
  engine first — zero asset cost); an interactive activity runtime; audio packaged for offline;
  narration production per [`CONTENT_PRODUCTION_PIPELINE.md`](CONTENT_PRODUCTION_PIPELINE.md).
- **Dependencies.** Phase B. Voice *input* additionally depends on FD-03 and M-Gov.
- **Acceptance criteria.** Every lesson screen can be heard, offline, in Urdu; activities record
  attempts through the existing evidence path.
- **Tests required.** Speech-availability fallback tests; offline audio package tests.

### Phase F — Production authentication hardening

- **Goal.** Close the identity gaps that a real deployment exposes.
- **Features.** KMS/HSM-held signing keys; refresh tokens and revocation; distributed rate limiting;
  guardian email verification and recovery; mentor and admin provisioning.
- **Dependencies.** Phase A. **FD-14 blocks the KMS item.**
- **Acceptance criteria.** No signing key in an environment variable in production; a revoked
  session stops working immediately; rate limits hold across instances.
- **Tests required.** Revocation tests; multi-instance rate-limit tests.

### Phase G — Consent and child safety completion

- **Goal.** Everything required before a real child is admitted.
- **Features.** Published privacy notice matching the enforced policy version; retention schedule
  and purge; export and erasure workflows spanning both schemas; distress detection; safeguarding
  triage queue; abuse reporting; the M-Safe drill.
- **Dependencies.** ⚫ **M-Gov and M-Safe sign-off. This phase cannot complete through engineering
  alone.**
- **Acceptance criteria.** DPIA signed; a distress signal reaches a human within the SLA in a
  recorded drill; erasure provably removes a child from every schema.
- **Tests required.** Erasure completeness tests across schemas; escalation-path tests.

### Phase H — Production hardening

- **Goal.** Earn the word "production".
- **Features.** Provision and verify a live environment; accessibility audit with assistive
  technology; cross-browser matrix; load, soak, and spike testing; external penetration test;
  dependency and container scanning; alerting; backup and restore rehearsal.
- **Dependencies.** Phases A–G.
- **Acceptance criteria.** Every item in §22 satisfied with recorded evidence.
- **Tests required.** The full gate suite plus each named external validation.

---

## 22. Definition of Done

"Project Taleem complete" means **all** of the following, each with evidence in the repository:

### Product

- A child completes an entire term of curriculum through the platform, unaided by an engineer.
- Curriculum published for the target grade range with all 9 quality gates green.
- Learning progression, mastery, spaced review, and assessment operate on real content.
- A guardian manages consent, sees progress, and receives interventions without support.

### AI

- Curriculum-grounded teaching whose every output traces to a published lesson.
- Safety controls with recorded evaluation results against a golden set.
- Governance approval for the AI path, including provider residency (FD-03).

### Security

- Production authentication with KMS-held keys, revocation, and distributed rate limiting.
- Deny-by-default authorization with no known IDOR or privilege-escalation path.
- An **external** penetration test performed, with findings closed.

### Child safety

- M-Gov closed: DPIA signed, consent model approved, residency decided, privacy notice published.
- M-Safe closed: safeguarding drill passed, reporting workflow tested, on-call staffed.
- Retention, export, and erasure workflows operating across every schema.

### Quality

- Automated tests green: backend, frontend, contracts, migrations, and documentation.
- Accessibility audited against WCAG 2.2 AA with assistive technology on a real device.
- Cross-browser matrix passed on the reference low-end Android baseline.
- Performance budgets measured and met on 2G/3G.
- Offline validated on device, not only in unit tests.

### Operations

- A live production environment, verified, with a recorded URL and health evidence.
- Monitoring with alerting to a staffed destination.
- Backup and restore rehearsed, with a measured recovery time.

---

## 23. Explicit Production Blockers

None of the following is resolved. Each is listed with what would resolve it.

| # | Blocker | Type | Resolved by |
| --- | --- | --- | --- |
| 1 | **M-Gov** — DPIA, consent model approval, mandatory-reporting policy, external safety review, residency | ⚫ Governance | DPO, legal, and founder sign-off |
| 2 | **M-Safe** — safeguarding policy approval and a passed live drill | ⚫ Governance | Safeguarding lead; staffed on-call |
| 3 | **Pilot 1 with real children is NO-GO** | ⚫ Governance | Blockers 1 and 2 |
| 4 | **No published curriculum content** | 🔴 Engineering + content | Phase B |
| 5 | **Zero audio assets for an audio-first product** | 🔴 Content | Phase E |
| 6 | **AI Teacher has no LLM; the port is unwired** | 🟡 Engineering, ⚫ blocked | Phase D, gated on FD-03 |
| 7 | **FD-03** — LLM inference residency and zero-retention | ⚫ Founder + legal | Founder decision |
| 8 | **FD-14** — KMS/HSM topology for signing keys | ⚫ Founder + security | Founder decision |
| 9 | **FD-02** — cloud provider and data-residency posture | ⚫ Founder + legal | Founder decision |
| 10 | **Frontend still uses development auth stubs** | 🔴 Engineering | Phase A — the immediate next task |
| 11 | **No verified live environment** | 🔴 Engineering | Phase H; needs a hosting decision |
| 12 | **No external penetration test** | 🔴 External | Commission a test |
| 13 | **No accessibility audit with assistive technology** | 🔴 External | Commission an audit |
| 14 | **No cross-browser, load, soak, or spike testing** | 🔴 Engineering | Phase H |
| 15 | **No backup, restore, or alerting** | 🔴 Engineering | Phase H |
| 16 | **Production secrets are environment variables only** | 🔴 Engineering | Phase F, gated on FD-14 |
| 17 | **Repository licence undecided** | ⚫ Founding team | [`LICENSE`](LICENSE) records this as open |
| 18 | **NCC/MoFEPT MoU for authoritative SLO text** | ⚫ Legal / partnership | Partnership decision |
| 19 | **Privacy notice text for the enforced policy version does not exist** | 🔴 Legal + engineering | M-Gov |
| 20 | **No data retention, export, or erasure workflow** | 🔴 Engineering + legal | Phase G |
| 21 | **Notifications have no delivery channel** | 🔴 Engineering | Phase C or later; SMS needs a cost decision |
| 22 | **Rate limiting is process-local** | 🟡 Engineering | Phase F |

---

## 24. Current Next Action

### Exact current development position

**Last completed milestone.** **M12 — Identity, consent, and child-safe sign-in**, at commit
`23747f9` on `main`. It closes the journey half of FD-14: guardian accounts, verifiable
append-only parental consent, learner enrolment with no child PII, family-code-plus-PIN sign-in,
durable lockout, uniform non-enumerating failures, an append-only audit trail, and a consent gate
that denies sign-in the moment a guardian withdraws. Evidence: 345 backend tests passing at 95.96%
coverage, `ruff`/`black`/strict `mypy` clean over 135 source files, migration `0004_identity`
reversible and covered by the ORM parity guard, and 9/9 OpenAPI contracts valid with served-path
parity enforced.

Prior completed milestones: M0–M11 plus the Guardian Portal and RC1 packaging (git tags `phase-4.1`
through `phase-11`, `rc1`), and Production Blocker 1 (asymmetric authentication, commit `7982199`).

**Current active milestone.** **Phase A — Core student experience.**

**Immediate next implementation task.** **Rewire `apps/web` from the development token stubs to the
live identity API, and build the three screens the journey needs: guardian join, guardian consent,
and child sign-in.**

Concretely: delete `NEXT_PUBLIC_DEV_STUDENT_TOKEN` and `NEXT_PUBLIC_DEV_GUARDIAN_TOKEN` from
`apps/web/lib/student/config.ts` and `apps/web/lib/guardian/config.ts`, replace them with a session
client over `/v1/identity`, and add `/join`, `/consent`, and `/signin` routes.

**Why this task is next.** Three reasons, in order of weight:

1. **It is the only thing standing between the platform and a usable product.** Every backend
   capability a child or guardian needs now exists and is tested. The web app cannot reach any of it
   because it still authenticates with a token an operator has to mint by hand.
2. **It removes the last governance-unsafe path from the product.** Both config files say in their
   own comments that they "must never ship to a real child" and "never ships to a real guardian".
   While they remain, the frontend cannot be deployed to anyone at all.
3. **It unblocks everything downstream.** Curriculum content (Phase B) needs a real learner session
   to be seen through; the guardian experience (Phase C) is UI over the identity API; audio and
   activities (Phase E) attach to a lesson player that only exists once a real session drives it.

Nothing in Phase A is blocked by governance, legal, payment, or an external decision. It can start
immediately.

---

## Related Documents

- Status and evidence: [`CURRENT_PROJECT_STATUS.md`](CURRENT_PROJECT_STATUS.md), [`DEPLOYMENT_READINESS_REPORT.md`](DEPLOYMENT_READINESS_REPORT.md), [`CHANGELOG.md`](CHANGELOG.md)
- Plan and sequencing: [`ROADMAP.md`](ROADMAP.md), [`CRITICAL_PATH.md`](CRITICAL_PATH.md), [`MASTER_EXECUTION_PLAN.md`](MASTER_EXECUTION_PLAN.md), [`docs/08-delivery/45-milestone-plan.md`](docs/08-delivery/45-milestone-plan.md)
- Decisions and risk: [`FOUNDER_DECISIONS.md`](FOUNDER_DECISIONS.md), [`RISK_REGISTER.md`](RISK_REGISTER.md), [`GO_NO_GO_DECISION.md`](GO_NO_GO_DECISION.md)
- Architecture: [`ARCHITECTURE_REVIEW.md`](ARCHITECTURE_REVIEW.md), [`OFFLINE_ARCHITECTURE.md`](OFFLINE_ARCHITECTURE.md), [`docs/02-architecture/`](docs/02-architecture/)
- Education: [`CURRICULUM_FRAMEWORK.md`](CURRICULUM_FRAMEWORK.md), [`docs/05-education/`](docs/05-education/)
- Safety: [`AI_TEACHER_SAFETY_MODEL.md`](AI_TEACHER_SAFETY_MODEL.md), [`INCIDENT_RESPONSE.md`](INCIDENT_RESPONSE.md), [`docs/03-security-privacy/`](docs/03-security-privacy/)
- Engineering standards: [`ENGINEERING.md`](ENGINEERING.md), [`docs/07-engineering/50-definition-of-done.md`](docs/07-engineering/50-definition-of-done.md)

## Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-09-06 | Initial master scope and roadmap, authored against repository HEAD `23747f9`. | Engineering |
