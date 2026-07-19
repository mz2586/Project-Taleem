# 01 · Vision Document

| | |
|---|---|
| **Document ID** | 01 |
| **Owner** | CEO / Chief Product Officer |
| **Status** | Approved (Phase 1) |
| **Last updated** | 2026-07-19 |
| **Related** | [02 PRD](../01-product/02-prd.md) · [15 Child Safety](../03-security-privacy/15-child-safety-framework.md) · [44 Roadmap](../08-delivery/44-roadmap.md) |

## Purpose

This document states *why* Project Taleem exists, *who* it serves, *what* it must become, and the
*principles and constraints* that every downstream decision must honour. It is the constitution of
the project: when documents or teams disagree, they resolve the disagreement against this vision.

## Scope

In scope: the mission, the problem, the target learner and their real-world constraints, the product
thesis, the definition of success, non-negotiable principles, and what we explicitly refuse to
build. Out of scope: implementation detail (owned by the architecture and specification documents).

---

## 1. The problem

Millions of children in Pakistan are out of school or in schools that cannot teach them. The reasons
compound: cost, distance, teacher shortages and absenteeism, overcrowded classrooms, gendered
barriers to attendance, displacement, disability, and the simple fact that a child who falls behind
in one grade is rarely given the patient, individual attention needed to catch up.

The children who most need a great teacher are the least likely to ever get one. A patient,
knowledgeable, always-available teacher — one per child — has historically been impossible to
provide at the scale of a nation. It is now possible.

**The constraint that defines our design** is not curriculum or content; those exist. It is the
child's reality: a **shared low-end Android phone**, an **intermittent 3G connection metered by the
megabyte**, **a few hours of electricity**, a **noisy home with no desk**, a caregiver who may not be
literate, and a language of instruction (Urdu) that most global software treats as an afterthought.
A product that ignores any one of these does not reach the child. This is why every specification in
this repository treats low-bandwidth performance, offline capability, accessibility, and child
safety as **acceptance criteria, not features**.

## 2. The mission

> **Give every Pakistani child a real school — one that teaches, cares, assesses fairly, and
> celebrates progress — regardless of income, geography, gender, or connectivity.**

Not content. Not a course. A **school**: enrolment, a timetable, teachers who know you, classmates,
homework, exams, a report card, a principal's office, and a graduation. The digital medium and AI
let us deliver that experience to one child or one million, at a marginal cost approaching zero, at a
quality that a well-resourced private school would envy.

## 3. What Taleem is — and is not

Taleem **is a complete digital school**. It has:

- **Enrolment and student records** — a child is admitted, placed in a grade, and belongs to a cohort.
- **AI Teachers** — patient, expert, always-available tutors that deliver lessons and answer the
  question a child was too shy to ask in a class of sixty.
- **A structured day** — timetabled lessons mapped to the national curriculum, not an infinite
  content shelf.
- **Assessment and honest grading** — formative practice, exams, and human-reviewed subjective work.
- **Report cards and promotion** — verifiable evidence of learning a guardian can trust and a future
  school or employer can recognise.
- **Student life** — streaks, houses/cohorts, celebrations, a sense of belonging and momentum.
- **Human mentors** — real educators who supervise cohorts, handle what AI should not, and provide
  the human warmth and accountability a machine cannot.
- **Guardian engagement** — parents see attendance, progress, and report cards, and are nudged to
  support their child, in language they understand.
- **Administration** — the back office that lets one team run a national school system safely.

Taleem **is not**:

- ❌ **an LMS** — we are not a container for someone else's course; we teach.
- ❌ **a course marketplace** — we are one coherent school with one curriculum spine, not a bazaar.
- ❌ **a chatbot** — the AI Teacher is a bounded, safety-governed, curriculum-grounded educator, not
  an open-ended conversational toy.

## 4. Product thesis

Three bets, each of which the architecture must make true:

1. **AI makes 1:1 teaching affordable at national scale.** A tiered AI Teacher (cheap models for
   routine feedback, powerful models for hard explanations) gives every child individual attention
   that no human system could staff. See [24 AI Teacher](../05-education/24-ai-teacher-specification.md).
2. **Structure beats a content firehose.** Children who have never had school need a school — a path,
   a rhythm, mastery gates, and someone who notices when they stop. Curriculum-as-data and a
   mastery-based lesson engine provide the spine. See [21 Curriculum](../05-education/21-curriculum-engine.md).
3. **Reaching the hardest-to-reach child is the whole game.** If it works for a girl on a shared 3G
   phone in a village with four hours of power, it works for everyone. Optimise relentlessly for the
   bottom of the connectivity and affordability curve, and the top takes care of itself.

## 5. Who we serve (summary; full detail in [05 Personas](../01-product/05-user-personas.md))

- **The Student** — a child aged ~5–16, grades KG–10, often sharing a device, often behind, often
  under-served by prior schooling, learning primarily in Urdu.
- **The Guardian** — a parent who wants their child to learn and to have proof of it, who may have
  limited literacy or time, and who holds legal consent.
- **The Mentor** — a human educator who scales their care across a cohort with AI doing the heavy
  lifting.
- **The School & Platform Admins and Safety Officers** — the people who run and protect the school.

## 6. Definition of success

We measure success by learning and reach, not vanity metrics.

| Horizon | What success looks like |
|---|---|
| **Learner outcome** | A child demonstrably moves from not-knowing to mastery on curriculum objectives, evidenced by assessment, and progresses grade-to-grade. |
| **Reach** | The product is usable — end to end — on a low-end Android phone on 3G with intermittent power, in Urdu. Reach is defined at the bottom of the curve. |
| **Trust** | Guardians trust the report card; children feel safe; safeguarding incidents are detected and handled; zero tolerance for child-safety failures. |
| **Scale** | The system serves 1,000,000 students without architectural rework or degradation of the core learning path. |
| **Sustainability** | Marginal cost per active student trends toward affordability at national scale, funded by sponsorship/scholarship/government partnership rather than fees that exclude the poor. |

**North-star metric:** *number of curriculum objectives mastered by students who would otherwise be
out of school* — a measure that is impossible to game by adding logins or content.

## 7. Non-negotiable principles

These bind every document and every engineer. Violating one is a release blocker.

1. **Child safety is absolute.** Every AI output, upload, and interaction is governed by the
   [Child Safety Framework](../03-security-privacy/15-child-safety-framework.md). When safety and any
   other goal conflict, safety wins — always.
2. **Design for the bottom of the curve.** Low-bandwidth, offline-first, low-end-device, intermittent
   power, and low-literacy caregivers are the *design centre*, not edge cases.
3. **Urdu-first and RTL-complete.** The primary language is Urdu with correct Nastaʿlīq/Naskh
   rendering and full right-to-left support. English is secondary. Additional languages are
   first-class citizens of the architecture.
4. **Accessible to every child.** WCAG 2.2 AA is the floor. A child with low vision, low literacy, or
   a motor impairment can attend school here.
5. **Privacy by design, minimal data.** We collect the least data needed to teach and protect a
   child, with strong guardian consent, encryption, and least privilege. See
   [14 Privacy](../03-security-privacy/14-privacy-model.md).
6. **Honesty in assessment and AI.** We never inflate grades, never fabricate a child's progress, and
   never let the AI pretend to be human or assert false facts unchallenged. The AI Teacher is
   grounded in curriculum and says "I don't know" rather than mislead a child.
7. **Scale is a design property, not a later project.** No decision may quietly cap growth at a
   number below one million.
8. **Enterprise quality is the standard.** SOLID, Clean/Hexagonal architecture, DDD, 12-Factor,
   OWASP, and documented decisions — because the stakes are children's futures.

## 8. What we explicitly refuse to build

Stating anti-goals prevents scope drift and protects children.

- **No open-ended, ungrounded chatbot.** The AI Teacher stays within curriculum and safety rails.
- **No engagement-maximising dark patterns.** We motivate learning, we do not exploit dopamine.
- **No data monetisation.** Children's data is never sold, never used for advertising, never used to
  train third-party models.
- **No pay-to-learn wall for the core school.** The core learning path must be reachable by a child
  who cannot pay. Monetisation is via sponsorship/partnership, never by excluding the poor.
- **No feature that only works on good hardware or fast internet** ships without a documented
  degraded-mode experience for the bottom of the curve.
- **No unsupervised high-stakes AI decisions** about a child (promotion, safeguarding) without human
  accountability in the loop.

## 9. Strategic constraints & assumptions

- **Regulatory:** we will operate under Pakistani data-protection expectations and international
  child-safety norms (planning assumption: align to the strictest of PECA/PDPB drafts, GDPR-K
  principles, and COPPA-equivalent protections). Confirmed in [14 Privacy](../03-security-privacy/14-privacy-model.md).
- **Curriculum authority:** we align to the national/provincial curriculum and must be adaptable to
  provincial and board variation; we do not invent our own credential in isolation of recognition
  pathways (planning assumption — partnership strategy owned by the business, not this repo).
- **Funding model:** sustainability depends on sponsorship, philanthropy, and public partnership
  (planning assumption); the architecture must keep marginal cost per student low to make this viable.
- **Connectivity trajectory:** we assume connectivity and device quality will *improve* over the
  product's life, but we refuse to bet a child's education on that improvement arriving first.

## 10. The ten-year picture

A decade out, Taleem is the school that a Pakistani child attends when no other school can have them —
and increasingly, the school a child *chooses* because its teaching is that good. A national and then
regional institution: millions of learners, recognised credentials, a corps of human mentors
amplified by AI, and a body of evidence that a great teacher for every child is no longer a dream but
an operating system. The blueprint in this repository is the first, deliberate step toward that.

---

## Open questions

- **Credential recognition:** what board/government partnership makes the report card portable? (Business track.)
- **Funding commitments:** which sponsors/partners underwrite the marginal cost at 1M scale? (Business track.)
- **Language rollout order** beyond Urdu/English (Sindhi, Pashto, Punjabi, Balochi) — sequence and demand signals.
- **Human mentor supply:** recruitment, training, and safeguarding vetting pipeline at scale.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial approved vision (Phase 1). | CEO / CPO |
