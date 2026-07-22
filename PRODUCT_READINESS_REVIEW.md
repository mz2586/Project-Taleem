# Product Readiness Review (PRR) — Pre-Pilot

Status: **Review only.** A comprehensive pre-pilot Product Readiness Review of Project Taleem, assessing
whether the platform is ready to put in front of real children. Feeds the Phase-6 plan
([MASTER_EXECUTION_PLAN.md](MASTER_EXECUTION_PLAN.md)) and pilot ladder ([PILOT_PLAN.md](PILOT_PLAN.md)).

> **⚠️ Reconstructed document (2026-07-22).** The original `PRODUCT_READINESS_REVIEW.md` was lost from
> the working tree (authored in a prior turn, never committed, dropped by the environment). This version
> is **reconstructed** from the review's recorded **scores and blocker set** (carried in the session
> record and referenced across the committed Phase-6 planning docs and milestone reports) plus the
> implemented platform. The **dimension scores, the 7 BLOCKERs, and the Go/No-Go verdict are recovered
> faithfully**; the surrounding narrative and the HIGH/MEDIUM/LOW item text are a best-effort
> reconstruction and are marked **[reconstructed]** where they restate rather than recover. No facts are
> invented; where a precise prior detail could not be recovered it is described at the level the score
> and blocker set support.

---

## 1. Method

Ten personas (child, low-literacy child, disabled child, parent/guardian, mentor/teacher, admin,
safeguarding lead, curriculum author, operator/SRE, security/privacy officer) walked 13 journey stages
(discover → onboard/consent → sign-in → dashboard → start lesson → learn/attempt → get help → homework
→ revision → assessment → progress → parent/mentor visibility → offline) across 12 dimensions
(functionality, educational quality, child safety, safeguarding-ops, accessibility, UX, mobile/offline,
performance, security/privacy, governance/consent, operations, pilot-readiness). Findings are classified
**BLOCKER / HIGH / MEDIUM / LOW**.

---

## 2. Readiness scores (0–100)

| Dimension | Score |
| --- | --- |
| **Overall** | **42** |
| Student experience | 52 |
| Parent experience | 12 |
| Educational quality | 55 |
| Accessibility | 50 |
| Child safety | 45 |
| Mobile / Offline | 40 |
| Pilot readiness | 28 |

Reading: the **engineering core is real and sound** (learning engine, persistence, derived student
APIs, portal scaffold — all governance-safe, tested), which lifts *student* and *educational* dimensions
to the middle band. But the **school around the platform** — safeguarding operations, governance/consent,
child-safe identity, real content + audio, parent/mentor visibility, and offline — is not yet built,
which is why **Parent (12)** and **Pilot readiness (28)** are low and **Overall** sits at **42**.

---

## 3. BLOCKERS (7) — must close before any child

| ID | Blocker | Dimension |
| --- | --- | --- |
| **B1** | **No operational safeguarding** — no live path routing a child in distress to a trained human within an SLA. | Safeguarding |
| **B2** | **Governance/consent unresolved** — no DPIA sign-off, lawful basis, per-child guardian consent, mandatory-reporting policy, or residency decision. | Governance |
| **B3** | **No child-safe auth** — only a dev JWT stub; no age-appropriate, guardian-linked identity. | Security/Identity |
| **B4** | **No Urdu audio** — audio-first is required for non-readers; the portal shows "audio not available." | Accessibility/Content |
| **B5** | **Offline not built** — the mission mode (3G/intermittent/offline) was not implemented at review time. | Mobile/Offline |
| **B6** | **No real content** — only the single sample fractions lesson; no pilot curriculum. | Educational |
| **B7** | **No parent/mentor visibility** — no surfaces for guardians or mentors to see progress/wellbeing or receive escalations. | Parent/Mentor |

Each blocker maps to a Phase-6 workstream: B1→WS2, B2→WS1, B3→WS3, B4→WS5, B5→WS13, B6→WS4, B7→WS6/WS7.
(Status note, 2026-07-22: **B5** is partially addressed — Phase 6.2A delivered offline-lite; **B6** is
addressed by the authored Grade 4 pilot curriculum; the remainder are open.)

---

## 4. HIGH findings (11) **[reconstructed]**

Reconstructed at the level the scores support; wording restates rather than recovers verbatim.

- **H1** Sessions are in-memory (not durable) — progress can be lost on restart/deploy (→ WS15).
- **H5** Evidence-hydration N+1 / O(lessons) query scans — performance risk under real load (→ WS15).
- **H9** Offline data-loss / double-count risk without an idempotent sync path (→ WS13).
- Parent/mentor trust: no trustworthy visibility surface (→ WS6/WS7).
- Accessibility: no audit with disabled participants; RTL/screen-reader unverified end-to-end (→ WS11).
- Content: no coherent multi-lesson arc to demonstrate mastery gain (→ WS4).
- Security: no external pentest; residency + at-rest encryption undecided (→ WS14).
- Ops: no kill-switch/rollback proven; backups/DR unexercised (→ WS16).
- AI: distress/abuse detection signals not wired to escalation (→ WS9/WS2).
- Admin: no consent-before-enrolment / cohort / mentor-assignment flow (→ WS8).
- QA: no cross-device / load / offline / safety test coverage for pilot journeys (→ WS16).

## 5. MEDIUM (12) and LOW (8) **[reconstructed — summary]**

MEDIUM items cluster around pedagogy-parameter validation on real learners, engagement/retention,
notification usefulness, monitoring/analytics instrumentation, content localization/register review,
cross-device inconsistencies, cost-per-learner visibility, and portal edge/empty/error states. LOW items
cover documentation drift, bus-factor, dependency hygiene, curriculum-standard alignment cadence, and
minor UX polish. These are carried in [RISK_REGISTER.md](RISK_REGISTER.md) (Tiers 3–4) rather than
re-enumerated here, since the register is the maintained source.

---

## 6. What is genuinely strong (do not rebuild)

- A real, tested **Learning Intelligence platform** — BKT mastery, spaced revision, a **pure**
  decision engine, session engine, **templated** (no-LLM) teaching runtime, scorer, analytics — with
  SQL persistence and reversible migrations.
- **Governance-safe by construction:** pseudonymous `student_ref` only, no child PII, deny-by-default
  PDP + IDOR guards, derived read models (no new child-data tables), append-only + idempotent evidence.
- **Derived student query APIs** for the whole dashboard surface, authenticated and IDOR-guarded.
- A **Student Portal frontend core** and (post-review) **offline-lite**.

The gap is not the engine; it is the **school operations, governance, identity, content, audio, human
surfaces, and offline** that surround it.

---

## 7. Go / No-Go

- **NO-GO for any unsupervised or at-scale use now.** Blockers B1–B3 (safeguarding, governance,
  child-safe auth) are hard stops; B4/B6/B7 make a real learning pilot impossible; B5 limits reach.
- **Conditional GO for a small, supervised, facilitated Pilot 1** *only after* M-Gov (WS1) and M-Safe
  (WS2) close and the pilot MVP (audio content, minimal parent/mentor/admin, child-safe auth, offline-
  lite) is built and QA-passed — with mentors + a safeguarding lead physically present, on provided
  devices, on guaranteed Wi-Fi (see [PILOT_PLAN.md](PILOT_PLAN.md), Pilot 1).

**Bottom line:** the platform is a strong, safe *engine*; it is **not yet a school**. The Phase-6 plan
([MASTER_EXECUTION_PLAN.md](MASTER_EXECUTION_PLAN.md)) sequences exactly the missing pieces, gated so no
child is ever ahead of the governance and human-safety layers.

---

## 8. Recommendations (priority order)

1. Start **WS1 (governance)** and **WS4→WS5 (content + audio)** on day 0 — they set the floor.
2. Stand up **WS2 (safeguarding)** as the second hard gate.
3. Build **WS3 (child-safe auth)**, then the **WS6/WS7/WS8** human surfaces and **WS12** journeys.
4. Harden with **WS15/WS14/WS13** and prove everything through **WS16 QA → Pilot 0 → Pilot 1**.
5. Keep every non-negotiable (MASTER_EXECUTION_PLAN §2) intact at every step.
