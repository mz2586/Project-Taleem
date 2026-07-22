# Pilot Plan — Pilot 0 → National Scale

Status: **Plan only.** Companion to [MASTER_EXECUTION_PLAN.md](MASTER_EXECUTION_PLAN.md),
[ROADMAP.md](ROADMAP.md), [CRITICAL_PATH.md](CRITICAL_PATH.md), [RISK_REGISTER.md](RISK_REGISTER.md).
A staged ladder from internal testing to national scale. **Each pilot's success criteria gate the
next.** No pilot with children starts before the governance (M-Gov) and safeguarding (M-Safe) gates.

Governing principle: **grow slowly, prove safety and efficacy at each rung, and never scale ahead of
the human safety layer or the evidence.** Numbers are learners; ratios (mentor:learner, safeguarding
coverage) tighten deliberately, then relax only when proven.

---

## Pilot 0 — Internal testing (no children)

- **Who:** the team + trained facilitators + synthetic/consenting-adult testers. **No real children.**
- **Required features:** the full pilot MVP build end-to-end (onboarding → session → help → homework →
  revision → assessment → progress → completion); parent/mentor/admin minimal; templated AI teacher;
  audio on the pilot content; offline-lite graceful degradation.
- **Required governance:** internal only (no child data) — but the *safeguarding runbook and reporting
  workflow are drilled* here; consent/DPIA drafts reviewed.
- **Required infrastructure:** staging environment (IaC), CI/CD, monitoring/alerting, backups/DR
  configured, kill-switch, analytics dashboards.
- **Required staffing:** engineering + QA + a safeguarding lead (to drill), 2–3 facilitators.
- **Success criteria:** every journey passes E2E; accessibility audit passed; security review + pentest
  passed; a **safeguarding drill** routes a simulated distress signal to a human within SLA; offline-
  lite degrades gracefully; load test at Pilot-1 + headroom passes; kill-switch + rollback verified.
  **Exit = Pilot 1 authorized.**

## Pilot 1 — 20–50 learners (first real children, fully supervised)

- **Who:** 20–50 children, one subject, 1–2 grades, at a **community learning center** (or equivalent),
  on **provided devices**, mentors + a safeguarding lead **physically present**, guaranteed on-site
  Wi-Fi, a few weeks.
- **Required features:** the **MVP** (MASTER_EXECUTION_PLAN §2) — audio-first lessons, templated AI
  teacher, help→human, homework/revision/formative assessment, child-friendly UI; minimal parent
  (progress/attendance/wellbeing), mentor (assigned learners, escalation, mentor-mediated summative),
  and admin/enrolment; durable sessions; offline-lite.
- **Required governance:** **M-Gov closed** — lawful basis + **informed parental/guardian consent per
  child**, DPIA signed, mandatory-reporting policy live, residency compliant, independent child-safety
  review passed.
- **Required infrastructure:** pilot environment (small, HA Postgres + backups/PITR), monitoring +
  on-call alerting, provided devices provisioned + MDM, kill-switch, analytics.
- **Required staffing:** **on-site mentors (low ratio, ≈1:10)**, a **safeguarding lead on-call during
  all pilot hours**, a site coordinator, engineering on-call.
- **Success criteria (safety + efficacy + usability):**
  - **Zero unhandled safety incidents;** every help/distress signal reached a human within SLA.
  - No data/privacy incident; consent complete for every child.
  - Learners can complete a session unaided (audio-first works for low readers); measurable **mastery
    gain** on the taught objectives; positive engagement/return.
  - Accessibility works for any disabled participants; the app stays usable through Wi-Fi hiccups.
  - Mentors + parents find the visibility useful and trustworthy.
  - **Exit = the model is safe and shows learning → Pilot 2 authorized.**

## Pilot 2 — 100 learners (harden + iterate)

- **Who:** ~100 children, still supervised, possibly 1–2 sites; broaden to more lessons / a second
  grade; introduce **at-home use for a subset** (with full offline).
- **Required features:** Pilot-1 learnings applied; **full offline** (at-home, intermittent networks);
  more content; refined pedagogy parameters (validated on Pilot-1 data); richer engagement (surfaced
  achievements/streaks); notifications for return-next-day.
- **Required governance:** consent model proven at slightly larger scale; safeguarding SLA holds with a
  subset off-site; data-retention operating.
- **Required infrastructure:** multi-site capable; content packaging/CDN for offline distribution;
  observability matured.
- **Required staffing:** mentor pool grown (ratio still tight, ≈1:15); safeguarding coverage extended
  to home users (clear escalation from home).
- **Success criteria:** offline works for real intermittent networks with **no data loss/double-count**;
  safety SLA holds off-site; mastery gains replicate; retention/engagement acceptable; support load
  manageable. **Exit → Pilot 3.**

## Pilot 3 — 500 learners (multi-site operations)

- **Who:** ~500 across several sites/communities; broader content (multi-topic within the subject or a
  second subject).
- **Required features:** admin suite matured (cohorts, mentor management, reporting, safeguarding
  dashboard at scale); **regional/small-model AI teacher tier** *if* independently safety-reviewed and
  approved (else stay templated); content breadth.
- **Required governance:** scaled consent + safeguarding operations; incident-response tested at
  multi-site; independent re-review before enabling any generative AI tier.
- **Required infrastructure:** infra scale-out proven (session store + persistence under real load;
  read replicas + cache + content CDN); cost model tracked.
- **Required staffing:** a small **operations org** (site coordinators, mentor leads, a safeguarding
  team, SRE on-call), training pipeline for new mentors.
- **Success criteria:** operations scale without safety degradation; mentor:learner ratio sustainable;
  efficacy holds across sites/content; cost-per-learner understood. **Exit → Pilot 4.**

## Pilot 4 — 5,000 learners (scale + cost)

- **Who:** ~5,000 across regions; largely at-home + community mix.
- **Required features:** the platform's scaling foundations proven (shard-by-`student_ref`, event-
  sourced analytics, partitioning) under real 5k load; CDN-delivered content/audio; automated
  provisioning; mature notifications/engagement.
- **Required governance:** regional/provincial compliance; safeguarding at regional scale with tiered
  escalation; audited data operations.
- **Required infrastructure:** production-grade HA + DR (RPO/RTO per doc 56) exercised; cost model
  validated and sustainable; capacity/scale model (doc 54) proven.
- **Required staffing:** regional operations + safeguarding teams; 24/7 on-call; support org.
- **Success criteria:** SLOs held under load; **safeguarding coverage never thinned by scale**; unit
  economics viable; measurable educational outcomes at scale. **Exit → Pilot 5.**

## Pilot 5 — National scale

- **Who:** national reach across provinces; homeschoolers, NGOs, community centers, refugee programs.
- **Required features:** multi-province **curriculum variants** + additional languages; full platform
  breadth; institutional integrations.
- **Required governance:** national data-protection + education compliance; **NCC/MoFEPT partnership /
  MoU** (desirable accelerator); national safeguarding framework + mandatory-reporting at scale.
- **Required infrastructure:** national-scale, multi-region, cost-optimized; disaster-tested; support
  and content-operations organizations.
- **Required staffing:** a national operations + safeguarding + content organization; partnerships and
  government-relations function.
- **Success criteria:** trusted, affordable, effective at national scale with **child safety and
  educational quality uncompromised** — the Definition of Success from the Master Overview.

---

## Cross-cutting pilot rules (every rung)

- **No rung starts before its predecessor's safety + efficacy criteria are met.** Growth is earned.
- **Safeguarding coverage tightens first, relaxes last** — never scale learners ahead of the human
  safety layer.
- **A kill-switch and rollback are always live**; any serious safety or data incident pauses the pilot.
- **Every rung measures:** safety incidents (target zero unhandled), mastery/learning gains, engagement
  /retention, accessibility inclusion, and (from Pilot 3) cost-per-learner.
- **Consent + governance re-validate at each scale**; assumptions that held at 50 are re-checked at 500
  and 5,000.
- **Non-negotiables (MASTER_EXECUTION_PLAN §2 "must never be compromised") apply identically at every
  scale** — from 20 learners to national.
