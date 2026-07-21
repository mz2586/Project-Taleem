# Product Readiness Review (PRR) — Pre-Pilot

Reviewer: acting Product/UX/Safety panel (multi-persona). Type: **review only — no code modified.**
Date: 2026-07-21. Subject: Project Taleem at `phase-5.5` (`931f1d0`).

Method: the platform was evaluated as it **actually exists in code** (not as designed on paper),
through ten stakeholder lenses, across the thirteen learner-journey stages, against twelve readiness
dimensions. Findings distinguish *built and working*, *scaffolded/stubbed*, and *designed-only*.
The bar is a **real child using this in a pilot** — the highest bar, because a child's safety and
first experience of school are at stake.

Reference for scope of what exists: `PHASE_5_5_REPORT.md`, `docs/12-student-experience/`,
`CTO_REVIEW.md`. This review supersedes none of them; it judges pilot-readiness.

---

## 1. Executive summary

Project Taleem has an **unusually strong engineering and design foundation** for its stage: a real,
evidence-based Learning Intelligence platform (BKT mastery, spaced revision, a pure decision engine),
a governed curriculum-authoring system, a hardened, authenticated, migrated, CI-guarded backend, and
a clean mobile-first PWA shell — all built with a discipline (design → adversarial review → fix →
build) that is rare this early.

But **as a product a real child could safely use in a pilot, it is not ready.** The gap is not the
core learning loop — that genuinely works end to end — it is the **operational and human layer around
it** that a child pilot cannot exist without:

- **There is no operational child-safety net.** The "Help" affordance changes a screen; nothing routes
  a distressed child to a real human. There is no safeguarding on-call, no mandatory-reporting flow.
- **There is no child-safe way to sign in** (dev-stub only), and the **Phase-1.5 governance decisions**
  (lawful basis, DPIA, residency, safeguarding SLA, child-identity, mandatory reporting) are unresolved.
- **The platform is "audio-first" for low-literacy children — but has no audio.** `ReadAloud` renders
  "Audio not available"; no lesson carries recorded Urdu audio. For a weak reader, the product is
  currently unusable as intended.
- **Offline — the mission-critical mode for 3G/intermittent learners — is designed but not built.**
  Off the network, the app shows an error, not a lesson.
- **There is essentially no content** (one sample Fractions lesson) and **no parent or mentor
  visibility** (those portals do not exist). A child cannot pilot on one lesson, and no responsible
  pilot puts children in front of an AI with no adult oversight.

Individually each is closeable; collectively they mean the **first pilot must be a small, supervised,
facilitated pilot** on a narrow, fully-audio content set, with real humans (mentors/safeguarding)
present — **not** an open, unsupervised, at-home rollout.

Persona one-liners (detail in §11 lens table):

- **Student:** the core lesson loop is engaging and safe, but there's no audio, no offline, and
  screens show raw codes like `MATH-G4-FR-01`.
- **Parent/Guardian:** currently invisible — no way to see progress, attendance, or wellbeing.
- **Mentor:** no portal, no escalation inbox — the human safety layer has no interface.
- **Teacher/Author:** Curriculum Studio is capable, but the authoring web client is stale and there's
  almost no authored content or audio.
- **School Administrator:** no admin surface, no cohort/enrolment/reporting.
- **Accessibility specialist:** strong tokens/contracts and RTL, but non-functional audio and no real
  audit or screen-reader/switch testing.
- **Child-safety reviewer:** excellent *architectural* posture (approved-content-only, IDOR, no PII,
  no chat/ads) but **no operational safeguarding** and unresolved governance → not approvable.
- **Educational psychologist:** the pedagogy is sound and evidence-based, but unvalidated on the
  population, misconception-clearance is too lenient, and the "AI teacher" is templated (no adaptivity).
- **UX designer:** clean, calm, mobile-first shell; several journeys are stubs; onboarding is missing.
- **Product manager:** a strong platform, but the MVP the *pilot* needs (audio, offline, safeguarding,
  parent/mentor, content) is not the MVP that exists.

**Total findings:** 7 BLOCKER · 11 HIGH · 12 MEDIUM · 8 LOW.

---

## 2. Scores

Calibrated against "ready for a real child to use in a pilot," not "good for this stage." At this
stage the platform *deserves* low pilot-readiness scores and high design-quality — both are true.

| Dimension | Score | One-line rationale |
| --- | --- | --- |
| **Overall product** | **42 / 100** | Excellent core + foundation; missing the human/operational layer a child pilot requires. |
| **Student experience** | **52 / 100** | The lesson loop works and is calm/safe; no audio, no offline, stub screens, raw codes, no onboarding. |
| **Parent experience** | **12 / 100** | Not built — no visibility of progress, attendance, or wellbeing. |
| **Educational quality** | **55 / 100** | Evidence-based engine is real; templated (non-adaptive) AI, one lesson, lenient clearance, unvalidated params. |
| **Accessibility** | **50 / 100** | Strong tokens/RTL/contracts; but non-functional audio (fatal for audio-first) + no audit. |
| **Child-safety** | **45 / 100** | Best-in-class *architecture*; **no operational safeguarding** + governance unresolved → not approvable yet. |
| **Mobile / offline readiness** | **40 / 100** | Mobile-first UI is good (~101 kB, budgets met); offline not built → the mission mode is broken. |
| **Pilot readiness** | **28 / 100** | No-Go for an unsupervised pilot; a narrow supervised pilot is reachable after the blockers. |

---

## 3. BLOCKER findings (must close before ANY real-child pilot)

| # | Problem | Why it matters | Recommended solution | Pre-pilot |
| --- | --- | --- | --- | --- |
| **B1** | **No operational safeguarding.** The Help button (and any distress) only changes a UI state; nothing reaches a human. No on-call, no mandatory-reporting flow. | A child in distress has no real path to help — the single most important thing about putting a child in front of an AI. | Build the safeguarding pipeline: Help/distress → real-time alert to an on-call safeguarding lead + mentor; mandatory-reporting workflow; documented SLA; staffed during pilot hours. | **Yes** |
| **B2** | **Governance gate unresolved (Phase-1.5).** Lawful basis, DPIA, data residency, safeguarding SLA, child-identity, mandatory-reporting policy are not decided. | Operating a service for children without these is legally/ethically impermissible. | Complete the Phase-1.5 founder decisions + DPIA + an independent external child-safety review before onboarding any child. | **Yes** |
| **B3** | **No child-safe authentication/identity.** Only a dev-stub token + synthetic learner exist. | Real children cannot be onboarded or kept separate/secure; a shared device leaks between learners. | Build guardian/mentor-provisioned, PII-minimal child sign-in (PIN/picture), device-linked, learner-scoped tokens; "switch learner" clears prior state. | **Yes** |
| **B4** | **No Urdu audio; the "audio-first" product has no audio.** `ReadAloud` shows "Audio not available"; lessons carry no audio refs. | The core value for low-literacy children is audio narration. Without it, weak readers cannot use the product. | Record Urdu audio for all pilot content; wire audio refs through the lesson package → `ReadAloud`; make audio mandatory on the pilot content path. | **Yes** |
| **B5** | **Offline not built.** Offline is designed only; the app errors without a network. | The target learner is on 3G/intermittent/offline. A product that needs connectivity excludes exactly the children it's for. | Build offline-core: cache the day's lesson packages + run a full session offline + queue/sync evidence (the designed subsystem). For a first *supervised Wi-Fi* pilot this can be reduced but must degrade gracefully. | **Yes** (offline-core, or a Wi-Fi-guaranteed supervised setting) |
| **B6** | **No real curriculum content.** One sample lesson (Fractions) exists. | A pilot cannot run on one lesson; children need a coherent, reviewed learning path. | Author + review a narrow but complete pilot content set (1 subject, 1–2 grades, ~20–40 lessons) with audio and quality-gate sign-off. | **Yes** |
| **B7** | **No parent or mentor visibility.** Parent and Mentor portals do not exist. | A child pilot with zero adult oversight/visibility is unsafe and fails "parent visibility"; mentors are the human safety layer with no interface. | Build minimal Parent view (progress, attendance, wellbeing status) and minimal Mentor view (assigned learners, escalation inbox, review) for the pilot. | **Yes** |

---

## 4. HIGH findings (needed for a good pilot)

| # | Problem | Why it matters | Recommended solution | Pre-pilot |
| --- | --- | --- | --- | --- |
| H1 | **Sessions are in-memory** (`InMemorySessionRepository`); lost on restart; no resume. | A child who loses connection/closes the app loses their session — the design promised resumable. Also blocks horizontal scale. | Persist the session aggregate + interactions; implement resume/abandon reconciliation. | Yes |
| H2 | **AI teacher is templated only** (no LLM adaptivity/rephrasing). Feedback is generic. | Limited personalization/adaptive explanation reduces educational effectiveness; the "AI" is content sequencing. | Acceptable (safe) for the *first* pilot; plan the small/regional model tier behind the safety layers next. Improve authored feedback variety meanwhile. | No (acceptable for pilot 1) |
| H3 | **Secondary journeys are stubs.** Homework/Assessments/Achievements/Notifications/Timetable/Revision screens are empty stubs or unbuilt; the portal doesn't yet consume the Phase-5.5 APIs (Today composes raw calls; no hint button in-session). | Half the learner journey the review is asked to assess isn't reachable in the UI. | Wire the portal to the 5.5 APIs (`today`, `reviews`, `homework`, `:hint`, …) and build the pilot-scope screens. | Yes (for the journeys in the pilot) |
| H4 | **No onboarding/first-run flow built.** The portal jumps to Today using a fixed dev learner; no sign-in/first-run. | First-time onboarding (stage 1 of the journey) does not exist for a real child. | Build the guardian-assisted setup + child first-run (with B3). | Yes |
| H5 | **Scalability blockers unproven/present.** Evidence-hydration N+1 (CTO M3), O(lessons) query scans, in-memory sessions, no content CDN/cache, no load test. | "Millions of learners" is unproven and has known bottlenecks. | Fix M3/query scans; persist sessions; add content caching; run a load test at pilot+headroom scale. | Partly (fix the worst; load-test before scale, not pilot) |
| H6 | **Misconception clearance too lenient** (CTO M5): one correct/lucky answer clears a confirmed misconception. | A child can appear to have corrected a misconception they still hold → false mastery, wrong pathing. | Require ≥2 targeted corrects / remediation-context; clear only misconceptions the item exercised. | Yes (pedagogical correctness) |
| H7 | **Learning-science parameters unvalidated** for the population (BKT slip/guess, spacing intervals, mastery thresholds are defaults). | Mastery/revision decisions may be mis-calibrated for Urdu-medium KG–10 learners; the pilot is partly to learn this. | Instrument + review the analytics during the pilot; treat parameters as tunable; don't over-trust mastery calls for promotion. | No (the pilot validates these) — but plan the measurement now |
| H8 | **Accessibility unaudited.** Non-functional audio (B4), weak `:focus-visible` tokens, studio a11y gaps, no screen-reader/switch/RTL testing. | WCAG 2.2 AA is a non-negotiable and the audio-first promise is unmet; disabled children may be excluded. | Independent a11y audit on the pilot build; add focus-visible + high-contrast/large-text; fix audio (B4); test with SR/switch + real RTL. | Yes |
| H9 | **Offline error recovery is a dead end.** With no offline data, disconnection yields an error/empty state, not a graceful cached experience. | The most common real-world condition (patchy network) produces a broken experience. | Ships with B5 (offline-core) — cache + graceful degradation + honest status. | Yes |
| H10 | **Notifications are non-operational.** Derived list only; no delivery/push, no real triggers, read-state not persisted. | Engagement/return-next-day (stages 11/13) rely on gentle nudges that don't actually fire. | Wire real (capped, calm) triggers (revision due, streak) + delivery; decide read-state storage. | No (nice-to-have for pilot 1) |
| H11 | **No admin/cohort/enrolment surface.** No way to enrol a pilot cohort, assign mentors, or pull operational reports. | Running and monitoring even a small pilot needs basic administration. | Minimal admin: enrol learners, assign mentors, cohort report, safeguarding dashboard. | Yes (operational necessity) |

---

## 5. MEDIUM findings

| # | Problem | Why it matters | Recommended solution | Pre-pilot |
| --- | --- | --- | --- | --- |
| M1 | Raw objective codes (e.g. `MATH-G4-FR-01`) shown to children in Today/Profile. | Cognitive load + not child-friendly; a child doesn't read SLO codes. | Show human titles (from the lesson) + icons; never raw codes on child surfaces. | Yes (cheap) |
| M2 | Motivation/engagement is thin in the UI — achievements/streaks derived but not surfaced; minimal celebration. | Sustained engagement (stages 11/13) drives real learning outcomes. | Surface achievements/streaks; warm, reduced-motion celebration; goals. | Partly |
| M3 | Emotional-safety framing is generic/templated (feedback text, "try again"). | Tone matters enormously for a child; generic text can feel cold. | Author warmer, specific, encouraging feedback per item; avoid any shame. | Yes (content) |
| M4 | Progress shows accuracy % — potentially anxiety-inducing. | Framing learning as a percentage can demotivate/anxietize children. | Prefer growth framing ("3 new ideas mastered"); de-emphasize raw accuracy on child surfaces. | Yes (cheap) |
| M5 | Assessments: summative correctly mentor-gated, but the mentor flow doesn't exist (ties to B7). | The gate points to a portal that isn't built. | Build the minimal mentor summative flow with B7. | Yes |
| M6 | Homework/Timetable are derived lists with no real assignment/submission/scheduling UX. | Stages 7–8 are shallow. | Wire submission via the evidence path; simple scheduling. | Partly |
| M7 | Media assets (SVG/diagrams) are refs only — no real visuals in lessons. | Visual concepts (CLT) are core to teaching; text-only is weaker and less accessible. | Produce/author real media for pilot content; verify alt text. | Yes (content) |
| M8 | Content breadth/coherence: even within one subject there's no reviewed scope-and-sequence. | Children need a coherent path, not isolated lessons. | Define + author the pilot scope-and-sequence with prerequisites (the DAG). | Yes |
| M9 | Session/lesson history + analytics exist but aren't surfaced to child/parent. | Reflection + parent trust rely on visible history. | Surface a simple history/timeline (child + parent). | Partly |
| M10 | High-contrast/dark mode + grade-band presets designed but not implemented in student components. | Accessibility + age-fit reduced. | Implement band presets + contrast/dark themes on the pilot build. | Partly |
| M11 | The authoring web client (`lib/studio-api.ts`, StudioConsole) is stale (pre-auth: sends `actor_role`, no token) and would 401. | Authors can't use the web console against the current API; content pipeline friction. | Update the studio client for bearer auth (mentor/author surface). | No (author-side; not the child pilot) |
| M12 | No analytics/telemetry review loop wired for the pilot (server metrics exist; no dashboards). | You can't learn from the pilot without visibility. | Stand up the pilot analytics dashboards (privacy-safe) before it starts. | Yes (to learn from the pilot) |

---

## 6. LOW findings

- **L1** Bottom-nav band presets not implemented (Early/Middle/Senior all get the full nav). Fix with M10.
- **L2** `docs/` numbering skips `09` (cosmetic).
- **L3** Root-level report clutter continues to grow (add this file to `docs/_reports/` eventually).
- **L4** Notification read-state deliberately client-side (accepted); revisit if persistence is needed.
- **L5** Timetable has no real calendar/dates (single "today" block set) — fine for pilot 1.
- **L6** Recommendations logic is heuristic (not the full engine) — acceptable, note for parity later.
- **L7** No app install/PWA onboarding prompt tuning for Android-Go.
- **L8** Some copy is English-first in the code (labels like "Homework") though the app is Urdu-first — localize all strings.

---

## 7. Journey-stage assessment (1–13)

| Stage | State | Verdict |
| --- | --- | --- |
| 1. First-time onboarding | **Not built** (dev learner) | Blocked (B3/H4) |
| 2. Daily login | **Not built** (dev-stub) | Blocked (B3) |
| 3. Dashboard (Today) | **Built**; composes raw calls; raw codes; no audio | Works, needs polish (H3/M1/B4) |
| 4. Starting today's lesson | **Built** (one big action → session) | Works |
| 5. AI teaching session | **Built**, templated, safe, in-scope; no audio; not durable | Works but limited (B4/H1/H2) |
| 6. Asking for help | **Cosmetic** — UI state only, no human | Blocked (B1) |
| 7. Homework | **Stub/derived**, no submission UX | Shallow (H3/M6) |
| 8. Revision | **API built**, no UI screen wired | Partial (H3) |
| 9. Assessments | **API built** (formative); summative mentor-gate points nowhere | Partial (B7/M5) |
| 10. Progress tracking | **Built** (child); **no parent view** | Half (B7) |
| 11. Motivation & engagement | **Thin** — derived, not surfaced | Weak (M2) |
| 12. Session completion | **Built** (celebrate + next) | Works |
| 13. Returning next day | **No notifications/streaks surfaced; no offline** | Weak (H10/B5) |

The **spine (3→4→5→12) works**; the **human, motivational, and continuity layers around it are the gap.**

---

## 8. Dimension assessment

| Dimension | Verdict |
| --- | --- |
| Simplicity | Strong — one clear action, calm shell. |
| Cognitive load | Mostly low; raw codes + missing audio hurt low-literacy learners. |
| Motivation | Weak — engagement mechanics designed, barely surfaced. |
| Accessibility | Mixed — great structure, fatal audio gap, unaudited. |
| Mobile usability | Strong — mobile-first, within budget. |
| Offline suitability | Poor — not built; the mission mode is broken. |
| Error recovery | Weak offline; calm error UX exists but no cached fallback. |
| Educational effectiveness | Real engine; limited by templated AI, thin content, lenient clearance, unvalidated params. |
| Emotional safety | Good non-punitive design; generic tone; no real help path. |
| Child safety | Excellent architecture; **no operational safeguarding**; governance unresolved. |
| Parent visibility | Absent. |
| Scalability (millions) | Sound core (pure engine, shard-by-student), but in-memory sessions + N+1 + no load test. |

---

## 9. Stakeholder lens table

| Persona | Biggest blocker for them |
| --- | --- |
| Student | No audio; no offline; raw codes; no onboarding. |
| Parent/Guardian | No visibility at all (B7). |
| Mentor | No portal / escalation inbox (B7/B1). |
| Teacher/Author | Almost no content + stale authoring client (B6/M11). |
| School Administrator | No admin/enrolment/reporting (H11). |
| Accessibility specialist | Non-functional audio + no audit (B4/H8). |
| Child-safety reviewer | No operational safeguarding + governance (B1/B2). |
| Educational psychologist | Templated (non-adaptive) teaching + unvalidated params + lenient clearance (H2/H6/H7). |
| UX designer | Missing onboarding + stub journeys (H3/H4). |
| Product manager | The pilot MVP (audio/offline/safeguarding/parent-mentor/content) isn't the built MVP. |

---

## 10. Top 25 recommendations (ranked)

1. **Stand up operational safeguarding** (real-time Help → human, on-call, mandatory-reporting). (B1)
2. **Resolve Phase-1.5 governance + DPIA + independent child-safety review.** (B2)
3. **Build child-safe, PII-minimal auth/onboarding** (guardian-provisioned PIN/picture). (B3, H4)
4. **Record Urdu audio for all pilot content and wire it through `ReadAloud`.** (B4)
5. **Build offline-core** (cache day-pack → run session offline → sync), or guarantee a supervised
   Wi-Fi setting for pilot 1. (B5, H9)
6. **Author + quality-gate a narrow, coherent pilot content set** (1 subject, 1–2 grades, ~20–40
   lessons, with media + audio). (B6, M7, M8)
7. **Build minimal Parent + Mentor portals** (progress/attendance/wellbeing; escalation inbox). (B7)
8. **Persist sessions + resume** (off in-memory). (H1)
9. **Wire the portal to the Phase-5.5 APIs + build the pilot-scope screens** (revision, homework,
   in-session hint, achievements). (H3)
10. **Tighten misconception clearance** (multi-correct, item-scoped). (H6)
11. **Independent accessibility audit + fix focus-visible/contrast + SR/switch/RTL testing.** (H8)
12. **Minimal admin: enrol cohort, assign mentors, safeguarding dashboard.** (H11)
13. **Replace raw objective codes with child-friendly titles + icons everywhere.** (M1)
14. **Warm, specific, non-punitive feedback + celebration; surface achievements/streaks.** (M2, M3)
15. **De-emphasize accuracy %; use growth framing on child surfaces.** (M4)
16. **Fix the evidence-hydration N+1 + query scans; add content caching.** (H5)
17. **Stand up privacy-safe pilot analytics dashboards** to learn from the pilot. (M12)
18. **Instrument the learning-science parameters for validation during the pilot** (don't auto-promote
    on unvalidated mastery). (H7)
19. **Implement grade-band presets + dark/high-contrast themes on the pilot build.** (M10)
20. **Localize all UI strings (Urdu-first) — no English-first labels on child surfaces.** (L8)
21. **Build the mentor summative-assessment flow** (the gate needs a destination). (M5)
22. **Load-test at pilot + headroom scale** before any scale-out. (H5)
23. **Update the authoring web client for the current auth** (author enablement). (M11)
24. **Wire real, capped, calm notifications** (revision due, streak) for return-next-day. (H10)
25. **Move point-in-time reports under `docs/_reports/`; keep the repo root clean.** (L3)

---

## 11. Recommended MVP for the first real pilot

A **small, supervised, facilitated pilot** — the only responsible first pilot for a child AI product.

**Setting.** ~20–50 children, one subject, 1–2 grades, at a **community learning center** (or
equivalent supervised setting) on **provided devices**, with **trained mentors and a safeguarding lead
physically present**, over a few weeks. Guaranteed on-site Wi-Fi (so offline-core can be a fast-follow
rather than a hard blocker) — but the app must degrade gracefully if the link drops.

**Must-have for that MVP (the blockers, scoped narrow):**

- Operational safeguarding (real human, on-call, mandatory-reporting) — **B1**.
- Governance/DPIA/independent safety review cleared — **B2**.
- Child-safe onboarding + sign-in (guardian-provisioned) — **B3/H4**.
- Full Urdu **audio** on the pilot content — **B4**.
- A coherent, reviewed **pilot content set** with media — **B6/M7/M8**.
- Minimal **Parent + Mentor** portals + minimal **Admin/enrolment** — **B7/H11**.
- **Durable sessions** + the pilot-scope student screens wired — **H1/H3**.
- **Accessibility audit** passed on the pilot build — **H8**.
- Tightened misconception clearance + **child-friendly labels + warm feedback** — **H6/M1/M3/M4**.
- **Privacy-safe analytics** to measure and learn — **M12/H7**.

**Explicitly deferred for pilot 1 (acceptable):** the generative LLM teacher tiers (templated is
safe and sufficient), full offline for at-home use, notifications/push, the full admin suite, breadth
beyond one subject, and scale-out/load. The pilot's job is to validate learning efficacy, safety, and
usability on a small supervised group — not to scale.

---

## 12. Go / No-Go

**Decision: NO-GO for a pilot in the current state. Conditional GO for a small supervised pilot once
the blockers are closed.**

- **NO-GO** for any unsupervised, at-home, or open pilot now: there is no operational safeguarding, no
  child-safe auth, no audio, no offline, negligible content, and no parent/mentor oversight. Putting a
  real child in front of it today would be unsafe and non-compliant.
- **Conditional GO** for the **supervised facilitated pilot MVP (§11)** once **B1–B7** are closed and
  **H1, H3, H6, H8, H11 + the cheap child-safety/UX items (M1/M3/M4)** are done. That is a bounded,
  achievable body of work — mostly the *human and content* layer, plus wiring the excellent backend
  that already exists into the child-facing surfaces.

The engineering foundation is genuinely strong; the honest conclusion is that Taleem is **close on the
machine and far on the humans, audio, and content** — exactly the things a child pilot cannot skip.
Close the seven blockers, run a small supervised pilot, and let real children (with real mentors and
parents watching) tell you what the analytics can't.

*No code was modified in producing this review.*
