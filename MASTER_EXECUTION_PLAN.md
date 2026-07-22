# Master Execution Plan — Platform to Real School (Phase 6)

Status: **Plan only.** The anchor document for Phase 6: the complete execution roadmap taking Project
Taleem from its current state to a real-world pilot. Companions: [ROADMAP.md](ROADMAP.md),
[CRITICAL_PATH.md](CRITICAL_PATH.md), [PILOT_PLAN.md](PILOT_PLAN.md), [RISK_REGISTER.md](RISK_REGISTER.md),
and the pre-pilot [PRODUCT_READINESS_REVIEW.md](PRODUCT_READINESS_REVIEW.md).

> **⚠️ Reconstructed document (2026-07-22).** The original `MASTER_EXECUTION_PLAN.md` was lost from the
> working tree (it was authored earlier and never committed; the environment dropped the untracked
> file). This version is **reconstructed** from: the committed milestone reports (`CTO_REVIEW.md`,
> `PHASE_4_2_REPORT.md`, `PHASE_5_5_REPORT.md`), the surviving companion docs (ROADMAP, CRITICAL_PATH,
> PILOT_PLAN, RISK_REGISTER — which reference WS1–WS16 and the milestones throughout), and the
> implemented platform. The **workstream set, dependencies, MVP definition, and non-negotiables are
> reconstructed faithfully and are internally consistent with the companion docs**; per-workstream
> Effort/Risk bands are reconstructed planning estimates, not recovered originals. Sections that are a
> best-effort reconstruction rather than a verbatim recovery are marked **[reconstructed]**.

---

## 0. Honest baseline — built vs missing

Grounded in the Product Readiness Review (PRR) and the milestone reports. **Built** (governance-safe,
no child data): Curriculum Studio authoring + SQL persistence; the Learning Intelligence platform (BKT
mastery, spaced revision, pure decision engine, session engine, **templated** AI teaching runtime,
scorer, analytics) with SQL persistence, bearer-JWT with PDP and IDOR auth, observability, reversible
PostgreSQL migrations; the Student backend query APIs (homework, assessments, reviews, timetable,
notifications, achievements, history, recommendations) as derived read models; the Student Portal
frontend core scaffold; and (Phase 6.2A) offline-lite. **Missing for a real pilot** (PRR B1–B7):
operational safeguarding, resolved governance/consent, child-safe auth, Urdu audio, real content,
parent/mentor visibility, and offline hardening — the work this plan sequences.

---

## 1. Workstreams (WS1–WS16)

Each workstream: **Objective · Deliverables · Dependencies · Effort (S/M/L/XL) · Risk (L/M/H) · Owner
type · Parallelizable work · Exit criteria.** Effort/Risk bands are **[reconstructed]** planning
estimates.

### WS1 — Governance & Legal

- **Objective:** make it lawful and ethical to serve children — the master gate.
- **Deliverables:** lawful-basis and parental-consent model; **DPIA**; data-residency decision;
  retention and erasure policy; mandatory-reporting policy; child-identity model decision; **independent
  external child-safety review**; terms/consent artefacts.
- **Dependencies:** external (legal/DPO/independent reviewer). Blocks everything child-facing.
- **Effort:** L (bounded by external timelines). **Risk:** H.
- **Owner:** Founder/Legal/DPO + independent reviewer.
- **Parallelizable:** policy drafting ∥ DPIA ∥ reviewer engagement.
- **Exit (M-Gov):** DPIA signed, consent model, mandatory-reporting policy, external safety review
  passed, residency decided. Hard gate for any child data.

### WS2 — Child Safety (operational safeguarding)

- **Objective:** a live human safety net — every child in distress reaches a trained person, fast.
- **Deliverables:** safeguarding runbook; distress/help escalation → human within SLA; mandatory-
  reporting workflow; on-call safeguarding staffing + training; incident logging; drills.
- **Dependencies:** WS1 (policy).
- **Effort:** L. **Risk:** H.
- **Owner:** Safeguarding lead + Ops + Backend (escalation plumbing).
- **Parallelizable:** build ∥ staffing ∥ runbook/drills.
- **Exit (M-Safe):** distress→human within SLA in a drill; reporting workflow tested; on-call staffed.
  Hard gate for any child use.

### WS3 — Child-safe Auth & Onboarding

- **Objective:** age-appropriate, guardian-linked identity replacing the dev JWT stub.
- **Deliverables:** device-linked handle + PIN/picture-password; guardian provisioning; short-lived
  bearer (`sub == student_ref`); production JWKS (FD-14); shared-device "switch learner".
- **Dependencies:** WS1.
- **Effort:** M. **Risk:** H.
- **Owner:** Backend (auth) + Frontend.
- **Parallelizable:** identity model ∥ onboarding UI.
- **Exit:** a child signs in safely (no PII, IDOR-guarded); guardian consent linked. (Closes PRR B3.)

### WS4 — Educational Content (the long pole)

- **Objective:** real, NCP-aligned, authored-original pilot curriculum.
- **Deliverables:** the Grade 4 Mathematics pilot curriculum (see [GRADE4_MATH_CURRICULUM.md](GRADE4_MATH_CURRICULUM.md),
  [LESSON_CATALOG.md](LESSON_CATALOG.md)) — 31 objectives, 31 lessons + 8 revisions + 1 summative, item
  pools, misconceptions, hints, homework; educational review + content-QA sign-off.
- **Dependencies:** none to start (gate-free authoring). Feeds WS5, WS10, WS13, WS16.
- **Effort:** XL (scales with author throughput × lesson count). **Risk:** H.
- **Owner:** Curriculum authors + SMEs + EdReview.
- **Parallelizable:** many authors in parallel across lessons.
- **Exit (with WS5, M-Content):** pilot lesson set published, quality-gates green, review signed.
  (Closes PRR B6.)

### WS5 — Audio & Media

- **Objective:** Urdu-first audio for every lesson (audio-first for non-readers).
- **Deliverables:** narration scripts, segmentation, timing metadata, captions, recorded audio, visuals
  with alt-text (see [AUDIO_SCRIPT_GUIDE.md](AUDIO_SCRIPT_GUIDE.md)).
- **Dependencies:** WS4 (content to narrate).
- **Effort:** L. **Risk:** M.
- **Owner:** Media/audio production + Lang review.
- **Parallelizable:** record in parallel across lessons, trailing WS4.
- **Exit:** Urdu audio + captions for all pilot lessons, verified offline. (Closes PRR B4.)

### WS6 — Parent Platform

- **Objective:** trustworthy parent visibility (a Pilot-1 trust requirement).
- **Deliverables:** minimal parent view — progress, attendance, wellbeing; consent surface.
- **Dependencies:** WS1, WS3.
- **Effort:** M. **Risk:** M.
- **Owner:** Frontend + Backend (derived reads).
- **Parallelizable:** ∥ WS7/WS8/WS12.
- **Exit:** a parent sees their child's progress + wellbeing safely. (Contributes to PRR B7.)

### WS7 — Mentor Platform

- **Objective:** mentors teach, mediate the summative, and receive escalations.
- **Deliverables:** assigned-learners view; escalation queue + learner context; mentor-mediated
  summative review; safeguarding actions.
- **Dependencies:** WS2 (escalation), WS3.
- **Effort:** M. **Risk:** M.
- **Owner:** Frontend + Backend.
- **Parallelizable:** ∥ WS6/WS8/WS12.
- **Exit:** a mentor acts on an escalation within SLA and mediates a summative. (Contributes to B7.)

### WS8 — Administration & Enrolment

- **Objective:** enrol cohorts, assign mentors, enforce consent-before-enrolment.
- **Deliverables:** minimal admin — cohorts, mentor assignment, enrolment with verified consent,
  reporting.
- **Dependencies:** WS1, WS3.
- **Effort:** M. **Risk:** M.
- **Owner:** Backend + Frontend.
- **Parallelizable:** ∥ WS6/WS7/WS12.
- **Exit:** a cohort is enrolled with consent + mentors assigned.

### WS9 — AI (templated pilot; deferred LLM tiers)

- **Objective:** safe, approved-content teaching + detection signals for the pilot.
- **Deliverables:** (a) templated feedback/teaching runtime (already built) tuned for pilot content;
  (b) distress/abuse **detection signals** feeding WS2 escalation (conservative, human-in-loop);
  deferred: regional/small-model then frontier LLM tiers, each independently safety-reviewed.
- **Dependencies:** WS2 (escalation), WS4 (content).
- **Effort:** M (pilot scope). **Risk:** M.
- **Owner:** Learning/AI + Safety.
- **Parallelizable:** feedback tuning ∥ detection signals.
- **Exit:** templated teaching runs on pilot content; detection signals route to a human. **No
  generative LLM to children in the pilot.**

### WS10 — Child Safety (product surface)

- **Objective:** the product's own safety controls (distinct from WS2 operations).
- **Deliverables:** content pre-moderation at packaging; crisis affordance; no open messaging;
  safety-clearance of every surface a child sees; content child-safety review.
- **Dependencies:** WS4 (content), WS1.
- **Effort:** M. **Risk:** H.
- **Owner:** Safety + Product + Content.
- **Parallelizable:** ∥ WS4/WS12.
- **Exit:** every child-facing surface + lesson is safety-cleared; crisis affordance present.

### WS11 — Accessibility

- **Objective:** every child — including disabled and low-literacy — can use it (WCAG 2.2 AA).
- **Deliverables:** design tokens/themes; audio-first flows; screen-reader + RTL support; an
  accessibility **audit** with disabled participants.
- **Dependencies:** tokens early; audit after screens land (WS12).
- **Effort:** M. **Risk:** M.
- **Owner:** Frontend + a11y specialist.
- **Parallelizable:** tokens ∥ builds; audit is near the convergence.
- **Exit:** a11y audit passed; usable by a non-reader and a screen-reader user. (Closes PRR accessibility gap.)

### WS12 — UX / Portal completion

- **Objective:** complete, dead-end-free student journeys.
- **Deliverables:** finish onboarding → session → help → homework → revision → assessment → progress →
  completion per `STUDENT_UI_FLOW`; error/empty states; engagement (streaks/achievements).
- **Dependencies:** WS3, WS5, WS9.
- **Effort:** M. **Risk:** M.
- **Owner:** Frontend.
- **Parallelizable:** ∥ WS6/WS7/WS8.
- **Exit:** every pilot journey is complete with no dead ends.

### WS13 — Offline

- **Objective:** work on 3G/intermittent/offline — the mission mode.
- **Deliverables:** offline-core — service-worker caching of the app shell + day's lesson packages;
  local durable store (IndexedDB); run a full session offline; queue evidence with idempotent client
  ids; sync via `sync.batch` (wire to the learning evidence path); honest offline status; integrity
  checks. **(Phase 6.2A delivered offline-lite: packages, SW, IndexedDB, offline dashboard/lessons,
  local progress + resume, cache versioning. Full sync/session offline is 6.2B/6.2C.)**
- **Dependencies:** WS4/WS5 (packaged content + audio), existing sync engine (extend), durable sessions
  (WS15/H1).
- **Effort:** L. **Risk:** H (data loss / sync correctness).
- **Owner:** Frontend + Backend (sync) + QA.
- **Parallelizable:** SW/cache ∥ local store ∥ sync path.
- **Exit:** a full session runs offline from cache and syncs with no double-counting; app degrades
  gracefully offline. (Closes B5, PRR H9. For a Wi-Fi-supervised pilot, offline-lite may suffice — see
  PILOT_PLAN.)

### WS14 — Security **[reconstructed]**

- **Objective:** protect child data and the platform end-to-end.
- **Deliverables:** security review + external pentest; data residency + at-rest encryption; secrets/
  key management (KMS, FD-14); dependency/supply-chain scanning; kill-switch; deny-by-default preserved.
- **Dependencies:** WS1 (residency), ongoing.
- **Effort:** L. **Risk:** M.
- **Owner:** Security + Backend.
- **Parallelizable:** most hardening ∥ everything else from day 0.
- **Exit:** review + pentest passed; residency + encryption in place; no open blocker findings.

### WS15 — Engineering hardening & durability

- **Objective:** production-grade durability + performance of the built platform.
- **Deliverables:** **durable sessions** with resume (off in-memory, PRR H1); fix the evidence-hydration
  N+1 and O(lessons) query scans (CTO M3, PRR H5); content read caching; the learning-persistence design
  set with a migration if new tables (durable sessions) are added (follow the design→review→build
  discipline); observability dashboards.
- **Dependencies:** none (pure engineering; no external gate).
- **Effort:** M. **Risk:** M.
- **Owner:** Backend.
- **Parallelizable:** off the critical path — do early.
- **Exit:** sessions survive restart/deploy; N+1 fixed; load test green.

### WS16 — Infra / Ops / QA / Pilot prep

- **Objective:** deploy, observe, test, and dry-run the pilot.
- **Deliverables:** IaC environments; CI/CD; monitoring + on-call alerting; backups/DR (RPO/RTO);
  kill-switch + rollback; analytics instrumentation; QA (load, cross-device, offline, safety, security);
  UAT; **Pilot 0** internal dry run; device provisioning + MDM; consent/enrolment readiness.
- **Dependencies:** all streams converge here.
- **Effort:** L. **Risk:** M.
- **Owner:** SRE/Ops + QA + Ops coordination.
- **Parallelizable:** infra + QA planning early; Pilot-0 dry run is the serial finale.
- **Exit (M-Assure → M-Pilot0):** all pilot journeys pass QA/a11y/safety/security; Pilot 0 passes;
  devices/site/staff/consent ready. Gate for Pilot 1.

---

## 2. MVP — the "Minimum Viable School"

### Included (Pilot 1 MVP)

Audio-first Urdu lessons on real pilot content; the **templated** AI teacher with graduated hints and
help→human; homework, revision, and formative assessment; a child-friendly, accessible, offline-lite
PWA; **minimal** parent (progress/attendance/wellbeing), mentor (assigned learners, escalation,
mentor-mediated summative), and admin/enrolment (consent-gated); durable sessions; operational
safeguarding.

### Intentionally excluded (from the MVP / Pilot 1)

- Generative LLM teacher tiers (templated is safe/sufficient) — WS9 later.
- Full at-home offline for intermittent networks (Wi-Fi-supervised for pilot 1) — WS13 full later.
- Multi-subject / broad grade coverage — content scales after pilot 1.
- Push notifications, rich gamification, full admin suite, national-scale infra.
- Autonomous promotion/summative grading (always mentor-mediated).

### Must never be compromised (non-negotiables — true at every scale)

- **Child safety comes first** — a child in distress always reaches a human; the whole thing pauses
  before it endangers a child.
- **AI uses approved content only** — no generative LLM to children until independently safety-reviewed;
  no AI claims to be a human teacher.
- **No child PII** beyond the pseudonymous `student_ref`; deny-by-default + IDOR-guarded; encrypted;
  in-region.
- **Audio-first, Urdu-first, WCAG 2.2 AA** — no child is excluded by literacy, language, or disability.
- **Governance/consent is satisfied before any child touches it** — no child data without a lawful
  basis, a DPIA, and safeguarding in place.
- **Learning is never high-stakes or punitive** — promotion is human-mediated and identity-assured; the
  summative is mentor-mediated.

---

## 3. Workstream summary matrix **[reconstructed effort/risk]**

| WS | Name | Effort | Risk | Gates | Owner |
| --- | --- | --- | --- | --- | --- |
| WS1 | Governance & Legal | L | H | M-Gov (root) | Legal/DPO |
| WS2 | Child Safety (ops) | L | H | M-Safe | Safeguarding |
| WS3 | Child-safe Auth | M | H | — | Backend |
| WS4 | Educational Content | XL | H | M-Content | Curriculum |
| WS5 | Audio & Media | L | M | M-Content | Media |
| WS6 | Parent Platform | M | M | M-Surfaces | Frontend |
| WS7 | Mentor Platform | M | M | M-Surfaces | Frontend |
| WS8 | Administration | M | M | M-Surfaces | Backend |
| WS9 | AI (pilot templated) | M | M | — | Learning/AI |
| WS10 | Child Safety (product) | M | H | — | Safety |
| WS11 | Accessibility | M | M | M-Assure | a11y |
| WS12 | UX / Portal | M | M | M-Surfaces | Frontend |
| WS13 | Offline | L | H | — | Frontend/Backend |
| WS14 | Security | L | M | M-Assure | Security |
| WS15 | Eng hardening | M | M | M-Assure | Backend |
| WS16 | Infra/Ops/QA/Pilot | L | M | M-Assure, M-Pilot0 | SRE/QA |

Critical path, parallelization, and the longest chain are in [CRITICAL_PATH.md](CRITICAL_PATH.md); the
phased timeline is in [ROADMAP.md](ROADMAP.md); the pilot ladder in [PILOT_PLAN.md](PILOT_PLAN.md); the
top-50 risks in [RISK_REGISTER.md](RISK_REGISTER.md).
