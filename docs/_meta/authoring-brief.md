# Authoring Brief & Canonical Decisions

> **Read this first.** Every document in this repository must be consistent with the
> decisions fixed here. If a document needs to contradict something below, it must instead
> raise an ADR (see `docs/02-architecture/adr/`) — it may not silently diverge.

This file is the **single source of truth** for names, scope, roles, and cross-cutting
technical decisions. It exists so that ~50 documents authored in parallel read as one coherent
work.

---

## 1. What we are building

**Project Taleem** (working title; "taleem" / تعلیم = "education" in Urdu) is a **complete digital
school**, not an LMS, not a course marketplace, and not a chatbot. It delivers a structured
Pakistani school experience — enrolment, timetabled classes, AI teachers, homework, assessments,
report cards, attendance, student life, parent engagement, and school administration — to children
who cannot afford or reach a traditional school.

**North-star outcome:** a child with a low-end Android phone on a 3G connection and 2 hours of
electricity a day can enrol, attend school, learn, be assessed fairly, and progress grade-to-grade
with a verifiable report card.

**Scale target:** architect for **1,000,000 concurrent-capable enrolled students**. Design for
this from day one; do not hand-wave scale.

---

## 2. Users & roles (canonical vocabulary)

Use these exact role names everywhere.

| Role | Description |
|---|---|
| **Student** | Enrolled child learner (primary user). Ages ~5–16, grades KG–10. |
| **Guardian** | Parent/guardian who consents, monitors, and receives report cards. Legal consent-holder. |
| **Mentor** | Human educator/coach who supervises a cohort, handles escalations the AI can't, and does human grading of subjective work. Not the AI. |
| **Teacher (AI)** | The **AI Teacher** — an AI persona that delivers lessons, answers questions, and gives formative feedback. Always render as "AI Teacher" in student-facing copy; never imply it is human. |
| **School Admin** | Operates a "school" / region: enrolment, cohorts, timetables, mentor assignment. |
| **Platform Admin** | Taleem staff: catalog/curriculum publishing, safety operations, platform config. |
| **Safety Officer** | Specialised role in Trust & Safety: reviews flagged content, safeguarding escalations. |
| **Curriculum Architect** | Authors/maps curriculum, learning objectives, and assessment blueprints. |

"User" alone is ambiguous — always qualify.

---

## 3. Educational scope (v1)

- **Curriculum spine:** the **Single National Curriculum (SNC) / National Curriculum of Pakistan**,
  grades **KG through Grade 10**, culminating toward the Matric (SSC) pathway. Model curriculum as
  data, not hardcode — provinces and boards vary.
- **Subjects (v1 core):** Urdu, English, Mathematics, General Science / Science, Islamiat, Social
  Studies / Pakistan Studies. Design the model to add subjects and boards without schema change.
- **Languages / medium of instruction:** **Urdu (primary), English (secondary)**. Architecture must
  support additional languages (Sindhi, Pashto, Punjabi, Balochi) as first-class later. Full RTL
  support for Urdu is mandatory, not an afterthought.
- **Pedagogy:** mastery-based progression, spaced retrieval, formative-first assessment, low-stakes
  practice. Age-appropriate, culturally grounded, and neutral/respectful on religion and gender.

---

## 4. Fixed technical decisions (do not re-litigate; raise an ADR to change)

**Frontend:** Next.js (App Router) · React · TypeScript (strict) · Tailwind CSS. Mobile-first,
offline-capable PWA. Server Components by default; minimize client JS for low-end devices.

**Backend:** Python **FastAPI**. Clean/Hexagonal architecture, DDD bounded contexts, async I/O.
REST + OpenAPI as the contract. WebSockets for realtime (live class, presence, notifications).
Event-driven integration between contexts (outbox pattern → broker).

**Data:** **PostgreSQL** (primary OLTP, one logical DB per bounded context where justified) ·
**Redis** (cache, sessions, rate limits, queues) · **Meilisearch** (search) · **S3-compatible**
object storage (media, uploads, generated report cards). Analytics via an event pipeline into a
columnar warehouse (design-time choice: ClickHouse-compatible).

**AI:** Provider-abstracted LLM gateway. Default to the latest, most capable **Claude** models
(e.g. Claude Opus 4.8 / Sonnet 5 / Haiku 4.5 tiered by task) behind our own `AITeacher` service —
never call a provider SDK directly from product code. RAG over curriculum content; strict safety
system prompts; every AI interaction logged and moderatable.

**Infra:** Docker · Kubernetes-ready · GitHub Actions CI/CD · Terraform-ready IaC. Multi-region
readiness with primary presence close to Pakistan (low latency + data-residency posture).

**Cross-cutting standards:** SOLID, Clean/Hexagonal architecture, DDD, CQRS *only where justified*,
event-driven where beneficial, REST + OpenAPI, 12-Factor, OWASP ASVS, WCAG 2.2 AA, security by
default, privacy by design.

---

## 5. Bounded contexts / services (canonical service map)

Refer to services by these names. (Details owned by `08-system-architecture.md`.)

1. **Identity & Access** — accounts, auth, sessions, RBAC/ABAC, guardian consent.
2. **Enrolment & School Ops** — schools, cohorts, timetables, attendance, mentor assignment.
3. **Curriculum** — subjects, grades, units, learning objectives, standards mapping, versioning.
4. **Lesson Delivery** — lesson runtime, content blocks, progress, resume, offline sync.
5. **AI Teacher** — orchestration of AI tutoring, RAG, safety guardrails, transcript logging.
6. **Assessment** — item bank, quizzes/exams, attempts, grading (auto + human), proctoring-lite.
7. **Grading & Reporting** — gradebook, report cards, transcripts, promotion decisions.
8. **Engagement & Notifications** — messaging, nudges, streaks, multi-channel delivery (SMS/WA/push).
9. **Trust & Safety** — moderation, safeguarding, flag triage, audit.
10. **Media** — upload/transcode/deliver, adaptive bitrate, image optimization, offline packaging.
11. **Search** — indexing + query over curriculum/lessons/help (Meilisearch).
12. **Analytics & Insights** — event ingestion, learning analytics, dashboards.
13. **Payments & Sponsorship** — (thin in v1) scholarships/sponsors/donors, fee waivers.
14. **Platform/Admin** — configuration, feature flags, back-office.

---

## 6. Non-functional targets (headline numbers — full set in `04-non-functional-requirements.md`)

- **Availability:** 99.9% core learning path (student login → lesson → submit).
- **Latency:** p95 API < 300 ms in-region; first meaningful paint < 3 s on 3G / low-end Android.
- **Payload budget:** initial route JS ≤ 150 KB gzip; lesson page fully usable ≤ 500 KB total.
- **Offline:** a student can download a day/week of lessons and complete + queue submissions offline.
- **Data cost empathy:** every screen has a documented data-cost budget; "lite mode" is default on slow links.
- **Accessibility:** WCAG 2.2 AA minimum; usable one-handed on a 360px screen; RTL-complete.
- **Security:** OWASP ASVS L2; child data encrypted at rest and in transit; least privilege.

---

## 7. Brand & design tokens (authoritative seed — full set in `18-design-tokens.md`)

- **Product name in copy:** "Taleem". Tone: warm, encouraging, calm, never patronising.
- **Primary palette (seed):** Deep Ilm Green `#0E7C5A` (learning/growth), Ink `#111827`,
  Paper `#FAFAF7`, Sky `#2563EB` (interactive), Sun `#F59E0B` (reward/celebration),
  Alert `#DC2626`. All pairings must meet WCAG AA contrast; design system owns the final ramp.
- **Type:** Urdu-first typeface with excellent Nastaʿlīq/Naskh rendering (e.g. Noto Nastaliq Urdu /
  Noto Sans Arabic) + a clean Latin companion (e.g. Inter). Fluid type scale, large touch targets
  (≥44px).
- **Spacing scale:** 4px base. Radius scale, elevation scale defined in design tokens doc.

---

## 8. Document format & quality bar

- **Every doc** starts with a metadata block: title, doc ID (from the 01–50 list), owner role,
  status (`Draft` / `Reviewed` / `Approved`), last-updated (2026-07-19), and a 2–4 sentence
  **Purpose** and **Scope / Out-of-scope**.
- Use headings, tables, and **Mermaid** diagrams (```mermaid fenced blocks) liberally. Prefer a
  diagram + table over prose for structure, flows, schemas, and state machines.
- Be concrete and decision-dense: state the decision, the rationale, the alternatives considered,
  and the trade-off. Call out **risks** and **open questions** in their own section.
- Cross-reference sibling docs by relative path.
- Enterprise tone; no marketing fluff; no fabricated statistics. If a number is an assumption,
  label it "(planning assumption)".
- End each doc with **Open Questions** and **Change Log**.
- **Child safety and low-bandwidth empathy are acceptance criteria for every design**, not features.

---

## 9. Repository conventions

- Docs live under `docs/NN-cluster/NN-name.md`. Diagrams that are standalone go in `docs/diagrams/`.
- ADRs use `docs/02-architecture/adr/ADR-NNNN-title.md` (MADR-style: Context, Decision, Status,
  Consequences, Alternatives).
- Numbering `01`–`50` maps to the deliverable list in the root `README.md`.
