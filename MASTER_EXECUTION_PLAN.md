# Master Execution Plan — Platform to Real School

Status: **Program plan only — no code, no commits.** Date: 2026-07-21. Baseline: `phase-5.5`
(`931f1d0`). Grounded in `CTO_REVIEW.md`, `PHASE_4_2_REPORT.md`, `PHASE_5_5_REPORT.md`, and
`PRODUCT_READINESS_REVIEW.md` (PRR). Companion documents: [ROADMAP.md](ROADMAP.md),
[CRITICAL_PATH.md](CRITICAL_PATH.md), [PILOT_PLAN.md](PILOT_PLAN.md),
[RISK_REGISTER.md](RISK_REGISTER.md).

This plan converts the current *platform* into a *supervised real-world pilot* of a school. It is a
program-management artifact: workstreams, dependencies, owners, effort, risk, and exit criteria —
not an engineering task list.

---

## 0. Where we are (the honest baseline)

**Built and working:** Curriculum Studio (authoring + SQL persistence + publish workflow + quality
gates); the Learning Intelligence platform (BKT mastery, spaced revision, pure decision engine,
session engine, **templated** AI teaching runtime, scorer, analytics) with SQL persistence, bearer-JWT
with PDP and IDOR auth, observability, and reversible PostgreSQL migrations; the Student backend APIs
(homework, assessments, reviews, timetable, notifications, achievements, history, recommendations,
today, hints — derived read models); a governance-safe Student Portal **core scaffold** (Today,
Session, Profile, Progress) on a synthetic learner + dev-stub token.

**Missing for a child pilot (PRR blockers):** operational safeguarding (B1), Phase-1.5 governance +
DPIA (B2), child-safe auth/identity (B3), Urdu audio (B4), offline (B5), real curriculum content (B6),
parent + mentor visibility (B7). Plus HIGH gaps: durable sessions, portal completeness, misconception
clearance, accessibility audit, admin/enrolment, scale hardening.

**The shape of the remaining work is human, content, and safety — not core algorithms.**

Effort key (team-level, planning estimates, not commitments): **S** ≤2 wk · **M** 2–6 wk · **L**
6–12 wk · **XL** >12 wk. Risk: L/M/H. Owner types abbreviated in each workstream.

---

## 1. The 16 workstreams

Each maps to PRR findings and can run with the parallelization noted. IDs `WS1…WS16`.

### WS1 — Governance & Legal (Phase-1.5)

- **Objective:** make it lawful and ethical to serve children — the master gate.
- **Deliverables:** lawful-basis and parental-consent model; **DPIA**; data-residency decision;
  retention and erasure policy; mandatory-reporting policy; child-identity model decision; **independent
  external child-safety review**; terms/consent artefacts.
- **Dependencies:** none (it is the root). Feeds WS3, WS6, WS7, WS8, WS10, WS14.
- **Effort:** L (mostly serial, external-dependent). **Risk:** H (blocks everything; legal timelines
  are outside our control).
- **Owner:** Legal/DPO + Founder + external reviewer.
- **Parallelizable:** the *policy* work parallelizes; the *sign-off* is a serial gate.
- **Exit criteria:** DPIA signed; consent model approved; mandatory-reporting policy adopted;
  independent safety review passed; residency decided. (Closes B2.)

### WS2 — Child Safety (operational safeguarding)

- **Objective:** a real human safety net around the AI.
- **Deliverables:** safeguarding pipeline (Help/distress → real-time alert → on-call lead + mentor);
  triage + escalation runbook; mandatory-reporting workflow (implements WS1 policy); staffed on-call
  roster + SLA; incident logging; crisis protocol wired to the app.
- **Dependencies:** WS1 (policy/SLA), WS9-runtime detection signals, WS7 (mentor interface).
- **Effort:** L. **Risk:** H (a failure here is the worst outcome).
- **Owner:** Safeguarding lead + Backend + Ops.
- **Parallelizable:** build (backend) ∥ staffing/training ∥ runbook authoring.
- **Exit criteria:** a real distress signal reaches a trained human within SLA in a drill; reporting
  workflow tested; on-call staffed for pilot hours. (Closes B1.)

### WS3 — Child-safe Authentication & Onboarding

- **Objective:** let a real child sign in safely with no PII entry, and be provisioned by an adult.
- **Deliverables:** guardian/mentor provisioning flow; child PIN/picture credential; device-linked,
  learner-scoped short-lived tokens (replace dev-stub); "switch learner" clears prior state; first-run
  onboarding.
- **Dependencies:** WS1 (identity model), existing auth abstraction (extend, don't redesign).
- **Effort:** M. **Risk:** M.
- **Owner:** Backend + Frontend + Security.
- **Parallelizable:** backend token/identity ∥ frontend sign-in/onboarding UI.
- **Exit criteria:** a guardian can provision a child; the child signs in with PIN/picture; tokens are
  learner-scoped (IDOR-safe); no child PII collected. (Closes B3, PRR H4.)

### WS4 — Educational Content (pilot scope-and-sequence)

- **Objective:** a coherent, reviewed, original body of lessons for the pilot subject/grades.
- **Deliverables:** pilot scope-and-sequence (1 subject, 1–2 grades, ~20–40 lessons) with the
  prerequisite DAG; authored lessons through Curriculum Studio (original, provenance-clean); worked
  examples, hints, misconception corrections, assessments, homework per lesson; media/diagrams (WS5
  produces audio; visuals authored here); quality-gate + educational-review sign-off.
- **Dependencies:** Curriculum Studio (exists), WS16-authoring-client fix (M11) for author enablement.
- **Effort:** XL (content is the long pole — authoring + review per lesson). **Risk:** M (quality,
  timeline, subject-expert availability).
- **Owner:** Content team (curriculum authors + subject experts + educational reviewers).
- **Parallelizable:** lessons authored in parallel by multiple authors; **independent of most
  engineering.**
- **Exit criteria:** the pilot lesson set is authored, quality-gates green, educational-review signed,
  and published. (Closes B6, PRR M7/M8.)

### WS5 — Audio & Media Production

- **Objective:** make the audio-first product actually speak Urdu.
- **Deliverables:** recorded Urdu audio for every pilot lesson (teacher script, questions, hints,
  feedback); audio pipeline into the offline lesson package; wired to `ReadAloud`; original
  diagrams/visuals with alt text; captions.
- **Dependencies:** WS4 (content must exist to narrate), design tokens (exist).
- **Effort:** L (per-lesson recording + QA). **Risk:** M (voice talent, dialect quality, volume).
- **Owner:** Audio/Media production + Content (scripts) + Backend (packaging).
- **Parallelizable:** recording parallelizes across lessons; follows WS4 authoring per lesson.
- **Exit criteria:** every pilot lesson has verified Urdu audio playing through `ReadAloud`; media has
  alt text. (Closes B4, PRR M7.)

### WS6 — Parent/Guardian Platform (minimal)

- **Objective:** give parents visibility + trust (and satisfy oversight for the pilot).
- **Deliverables:** parent auth (guardian identity, from WS1/WS3); parent view — child progress,
  attendance/consistency, plain-language reports, wellbeing status; low-literacy (audio/visual)
  summaries; consent management.
- **Dependencies:** WS1, WS3, existing learning/progress APIs (reuse), new parent-scoped APIs
  (contract-first, IDOR to own child).
- **Effort:** M–L. **Risk:** M.
- **Owner:** Backend + Frontend + UX.
- **Parallelizable:** parent APIs ∥ parent UI; independent of the student portal.
- **Exit criteria:** a parent sees their child's progress/attendance/wellbeing; consent is manageable;
  IDOR-scoped to own child. (Closes B7-parent.)

### WS7 — Mentor Platform (minimal)

- **Objective:** the human layer's interface — oversight, support, safeguarding escalation.
- **Deliverables:** mentor auth + assignment; assigned-learners dashboard; **escalation inbox** (from
  WS2); review of flagged learners/wellbeing; mentor-mediated summative-assessment flow (the gate that
  currently points nowhere); notes.
- **Dependencies:** WS1, WS3, WS2 (escalation), existing learning data (reuse).
- **Effort:** M–L. **Risk:** H (this is the operational safety interface).
- **Owner:** Backend + Frontend + Safeguarding lead (requirements).
- **Parallelizable:** with WS6 (shares auth patterns).
- **Exit criteria:** a mentor sees assigned learners + escalations, can act on wellbeing, and can run
  the mentor-mediated summative flow. (Closes B7-mentor, PRR M5.)

### WS8 — Administration Platform (minimal)

- **Objective:** run and monitor a pilot cohort.
- **Deliverables:** enrol learners; assign mentors/guardians; cohort/operational reporting;
  **safeguarding dashboard**; configuration; audit visibility.
- **Dependencies:** WS1, WS3, WS2.
- **Effort:** M. **Risk:** M.
- **Owner:** Backend + Frontend + Ops.
- **Parallelizable:** with WS6/WS7.
- **Exit criteria:** an admin can enrol a cohort, assign mentors, and monitor safeguarding + progress.
  (Closes PRR H11.)

### WS9 — AI (teaching runtime evolution)

- **Objective:** improve teaching quality **without** compromising safety.
- **Deliverables (staged):** (a) richer authored feedback/variety on the templated tier (pilot-safe);
  (b) distress/uncertainty **detection signals** feeding WS2; (c) *post-pilot* small/regional model
  tier behind the grounding + safety layers (scope-check, fallback-to-approved) — **not** for pilot 1.
- **Dependencies:** WS2 (safety layers), WS4 (content), existing runtime (extend).
- **Effort:** M (pilot-scope a/b) · XL (LLM tier, later). **Risk:** H (any generative tier is a child-
  safety surface).
- **Owner:** ML/AI + Backend + Safeguarding lead.
- **Parallelizable:** feedback variety ∥ detection signals; LLM tier is a separate later track.
- **Exit criteria (pilot):** templated teacher gives warm, specific feedback; distress/uncertainty
  signals reach WS2. LLM tiers deferred with a documented gate. (PRR H2/M3.)

### WS10 — Child Safety (product-surface, non-operational)

- **Objective:** the product-side child-safety guarantees (distinct from WS2 operations).
- **Deliverables:** confirm approved-content-only rendering (exists); tighten **misconception
  clearance** (multi-correct, item-scoped, CTO M5); age-appropriate labels/tone; no-PII posture tests;
  content-safety review of all pilot content; help affordance ergonomics.
- **Dependencies:** WS2, WS4.
- **Effort:** S–M. **Risk:** M.
- **Owner:** Safeguarding + Content + Backend.
- **Parallelizable:** yes.
- **Exit criteria:** clearance requires real evidence of correction; pilot content passes a child-
  safety review; no path renders ungrounded content. (PRR H6.)

### WS11 — Accessibility

- **Objective:** meet WCAG 2.2 AA in practice, for real disabled/low-literacy children.
- **Deliverables:** **independent a11y audit** of the pilot build; functional audio (with WS5);
  focus-visible + high-contrast + large-text + dark themes; grade-band presets; screen-reader/switch +
  real RTL testing; child-friendly labels (replace raw codes); Urdu-first localization of all strings.
- **Dependencies:** WS5 (audio), WS12 (UI screens to audit).
- **Effort:** M. **Risk:** M (exclusion of disabled children is a mission failure).
- **Owner:** A11y specialist + Frontend + UX.
- **Parallelizable:** token/theme work early ∥ audit after screens land.
- **Exit criteria:** independent audit passed on the pilot build; audio functional; no color-only
  state; SR/switch/RTL verified. (PRR H8, M1, M10, L8.)

### WS12 — UX / Design & Student Portal completion

- **Objective:** complete the child-facing journeys for the pilot.
- **Deliverables:** wire the portal to the Phase-5.5 APIs (`today`, `reviews`, `:hint`, homework,
  achievements, notifications); build the pilot-scope screens (onboarding, revision, homework,
  achievements, help-in-session); warmer feedback/celebration; growth-framed progress (de-emphasize
  accuracy %); band presets.
- **Dependencies:** WS3 (onboarding/auth), WS5 (audio), WS9 (feedback), WS11 (a11y).
- **Effort:** L. **Risk:** M.
- **Owner:** Frontend + UX.
- **Parallelizable:** screens split across the team; depends on APIs (mostly built).
- **Exit criteria:** every pilot journey (1–13) is reachable, calm, audio-first, and child-friendly.
  (PRR H3, H4, M2, M3, M4.)

### WS13 — Offline

- **Objective:** work on 3G/intermittent/offline — the mission mode.
- **Deliverables:** offline-core — service-worker caching of the app shell + day's lesson packages;
  local durable store (IndexedDB); run a full session offline; queue evidence with idempotent client
  ids; sync via `sync.batch` (wire to the learning evidence path); honest offline status; integrity
  checks.
- **Dependencies:** WS4/WS5 (packaged content + audio), existing sync engine (extend), durable
  sessions (WS15/H1).
- **Effort:** L. **Risk:** H (data loss / sync correctness).
- **Owner:** Frontend + Backend (sync) + QA.
- **Parallelizable:** SW/cache ∥ local store ∥ sync path.
- **Exit criteria:** a full session runs offline from cache and syncs with no double-counting; app
  degrades gracefully offline. (Closes B5, PRR H9. *For a Wi-Fi-supervised pilot, an offline-lite
  subset may suffice — see PILOT_PLAN.*)

### WS14 — Security

- **Objective:** protect children's data and the platform.
- **Deliverables:** production auth hardening (JWKS/asymmetric per FD-14, replace HS256 dev secret —
  the prod-default guard already exists); secrets management; encryption at rest + per-learner crypto-
  shred; RLS enforcement (FORCE RLS) where it must be a boundary; CSP/HSTS; least-privilege; security
  review + pen test of the pilot surface; audit-log integrity (already hash-chained).
- **Dependencies:** WS1 (residency), WS3 (auth).
- **Effort:** M–L. **Risk:** H (a breach of child data is catastrophic).
- **Owner:** Security + Backend + DevOps.
- **Parallelizable:** with most build work.
- **Exit criteria:** independent security review + pen test passed; secrets/KMS in place; encryption +
  erasure verified. (CTO H8; PRR child-safety.)

### WS15 — Engineering hardening & durability

- **Objective:** make the platform reliable at pilot scale and beyond.
- **Deliverables:** **durable sessions** with resume (off in-memory, PRR H1); fix the evidence-hydration
  N+1 and O(lessons) query scans (CTO M3, PRR H5); content read caching; the learning-persistence design
  set with a migration if new tables (durable sessions) are added (follow the design→review→build
  discipline); observability dashboards.
- **Dependencies:** existing persistence (extend).
- **Effort:** M–L. **Risk:** M.
- **Owner:** Backend + DevOps.
- **Parallelizable:** independent of content/UX.
- **Exit criteria:** sessions survive restart + resume; per-interaction path is O(1)-ish; dashboards
  live. (PRR H1/H5.)

### WS16 — Infrastructure, Operations & QA (+ Pilot Prep)

- **Objective:** deploy, operate, assure, and run the pilot.
- **Deliverables:** infra-as-code deploy (Kubernetes-ready), CI/CD to a staging + pilot environment,
  Postgres HA + backups/PITR + DR (design exists — doc 56), monitoring/alerting/on-call, cost model;
  **QA** — test plans, cross-device (Android-Go) matrix, load test at pilot+headroom, a11y + safety +
  offline + security test passes, UAT with facilitators; **Pilot prep** — devices provisioned, site +
  connectivity, mentor/safeguarding training, consent collection, data-collection plan, analytics
  dashboards, rollback/kill-switch, incident runbooks.
- **Dependencies:** all build workstreams (to test/deploy), WS1 (to collect real data).
- **Effort:** L (overlapping). **Risk:** H (operational readiness gates the pilot).
- **Owner:** DevOps/SRE + QA + Program/Ops + Field.
- **Parallelizable:** infra ∥ QA planning early; the *pilot dry-run* is a serial gate at the end.
- **Exit criteria:** Pilot 0 (internal) passed; devices + site + staff + consent ready; kill-switch +
  runbooks tested; analytics live. (See PILOT_PLAN Pilot 0/1.)

---

## 2. MVP — the Minimum Viable School

The smallest thing that is genuinely a *supervised school*, not a demo. (Rationale + phasing in
[PILOT_PLAN.md](PILOT_PLAN.md) Pilot 1.)

### Included

- One subject, 1–2 grades, ~20–40 **original, reviewed, fully-audio** lessons with the prerequisite
  DAG (WS4/WS5).
- The core learner journey: onboarding → daily login → Today → session (templated AI teacher,
  audio-first) → help → homework → revision → formative assessment → progress → completion → return
  (WS3/WS12).
- **Operational safeguarding** with real humans on-call + mandatory reporting (WS2).
- **Minimal Parent** (progress/attendance/wellbeing) and **Mentor** (assigned learners + escalation +
  mentor-mediated summative) portals, and **minimal Admin/enrolment + safeguarding dashboard**
  (WS6/WS7/WS8).
- **Durable sessions**, **accessibility-audited** build, **child-safe auth**, and **security-reviewed**
  surface (WS15/WS11/WS3/WS14).
- Runs in a **supervised, facilitated** setting on **provided devices** with **guaranteed Wi-Fi**;
  **offline-lite** graceful degradation (full offline is a fast-follow) (WS13, reduced).
- Privacy-safe analytics to measure efficacy, safety, and usability (WS16).

### Intentionally excluded (from the MVP / Pilot 1)

- Generative LLM teacher tiers (templated is safe/sufficient) — WS9 later.
- Full at-home offline for intermittent networks (Wi-Fi-supervised for pilot 1) — WS13 full later.
- Multi-subject / broad grade coverage — content scales after pilot 1.
- Push notifications, rich gamification, full admin suite, national-scale infra.
- Autonomous promotion/summative grading (always mentor-mediated).

### Must never be compromised (non-negotiables — true at every scale)

- **Child safety first** — a real human is always reachable; distress halts teaching; when safety and
  any other goal conflict, safety wins.
- **The AI only ever teaches approved, in-scope, original content** — ungrounded generation is
  unreachable by a child; never copy copyrighted material.
- **No child PII beyond the pseudonymous minimum**; data is protected, residency-compliant, and
  erasable.
- **A child reaches only their own data** (IDOR-guarded), always.
- **Audio-first, Urdu-first, WCAG 2.2 AA** — never exclude the low-literacy or disabled child the
  mission exists for.
- **Governance/consent is satisfied before any child touches it** — no child data without a lawful
  basis, a DPIA, and safeguarding in place.
- **Learning is never high-stakes or punitive**; promotion is human-mediated and identity-assured.

---

## 3. Workstream summary matrix

| WS | Name | Effort | Risk | Owner (lead) | Closes |
| --- | --- | --- | --- | --- | --- |
| 1 | Governance & Legal | L | H | Legal/DPO | B2 |
| 2 | Child Safety (ops safeguarding) | L | H | Safeguarding | B1 |
| 3 | Child-safe Auth & Onboarding | M | M | Backend/Frontend | B3, H4 |
| 4 | Educational Content | XL | M | Content | B6 |
| 5 | Audio & Media | L | M | Audio/Media | B4 |
| 6 | Parent Platform | M–L | M | Backend/Frontend | B7-parent |
| 7 | Mentor Platform | M–L | H | Backend/Frontend | B7-mentor, M5 |
| 8 | Administration | M | M | Backend/Frontend | H11 |
| 9 | AI (runtime evolution) | M / XL | H | ML/AI | H2, M3 |
| 10 | Child Safety (product surface) | S–M | M | Safeguarding/Content | H6 |
| 11 | Accessibility | M | M | A11y specialist | H8, M1, M10 |
| 12 | UX / Portal completion | L | M | Frontend/UX | H3, H4, M2–M4 |
| 13 | Offline | L | H | Frontend/Backend | B5, H9 |
| 14 | Security | M–L | H | Security | H8(sec), breach risk |
| 15 | Eng hardening & durability | M–L | M | Backend | H1, H5 |
| 16 | Infra / Ops / QA / Pilot prep | L | H | DevOps/QA/Ops | operational readiness |

The remaining planning artifacts — phasing, the critical path, the pilot ladder, and the ranked risk
register — are in the companion documents.
