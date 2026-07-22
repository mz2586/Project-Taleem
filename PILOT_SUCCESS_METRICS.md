# Pilot Success Metrics

Status: **Phase 9 — Pilot Operations.** Measurable metrics for the first supervised pilot, each with a
**definition, data source (existing), target, and how it is measured** — sourced entirely from data the
platform already produces (append-only evidence, sync diagnostics, derived read models). No new data
pipeline. Companion to [PILOT_RUNBOOK.md](PILOT_RUNBOOK.md), [END_TO_END_VALIDATION.md](END_TO_END_VALIDATION.md).

> **North star (non-negotiable):** **zero unhandled safety incidents.** Every other metric is
> secondary to child safety. A pilot with strong learning numbers but any unhandled safety incident is
> a **failure**.

---

## 0. Data sources (all existing)

| Source | Provides |
| --- | --- |
| `AssessmentEvidence` (append-only) + outbox | attempts, outcomes, mastery, misconceptions, events |
| Derived read models (`today`/`history`/`progress`/`reviews`/`recommendations`) | completion, progress, activity |
| Sync diagnostics (6.2B/6.2C-1, local C1 counters) | sync success, retries, conflicts, integrity/eviction |
| AI Teacher plan + guardrail | weak topics, escalations, confidence |
| Mentor session notes (follow-up loop) | interventions, escalation outcomes |

All pseudonymous (`student_ref`) — **no child PII** in any metric.

---

## 1. Lesson completion

- **Definition:** the % of started lessons a learner completes (reaches end-of-lesson).
- **Source:** `history.sessions` / local `lesson_completed` progress events (6.2A) vs started.
- **Target (Pilot 1):** most started lessons completed; low mid-lesson abandonment.
- **How measured:** completed ÷ started, per learner + cohort, over the pilot; trend by week.

## 2. Learning progress (mastery gain)

- **Definition:** measurable **mastery gain** on taught objectives (the primary efficacy signal).
- **Source:** BKT mastery in `StudentKnowledge` (via `progress`) + `ObjectiveMastered` events; pre/post.
- **Target:** a positive, statistically meaningful mastery gain on the objectives taught; objectives
  reaching **confirmed mastery** (≥ 4/5 distinct) for most learners.
- **How measured:** per-objective mastery delta (start → end) + count of newly-mastered objectives;
  mentor-confirmed at the mentor-mediated summative (never auto-promoted).

## 3. Sync success rate

- **Definition:** the % of queued attempts that sync successfully (applied/duplicate) without loss.
- **Source:** sync diagnostics (`applied` + `duplicate` vs `deadLettered`) + queue drain.
- **Target:** **100% no-loss, no double-count** (idempotency guarantees this — the metric confirms it in
  the field); near-zero dead-letters.
- **How measured:** (applied + duplicate) ÷ total queued; dead-letter count; time-to-drain after
  reconnect.

## 4. Offline reliability

- **Definition:** how well the app works offline — sessions completed offline, packages verified,
  crash-free resume.
- **Source:** offline session counts (local), package verify success (signature/hash), resume events
  (checkpoints), integrity/eviction counters (6.2C-1).
- **Target:** offline sessions complete end-to-end; **zero un-synced-write loss**; signature/hash
  verification always enforced; graceful degradation (no dead ends).
- **How measured:** offline-completed ÷ offline-started; verification-failure count (should be ~0 for
  legitimate packages); queued-write-loss count (**must be 0**).

## 5. Guardian engagement

- **Definition:** whether guardians engage with reporting (dashboard views, weekly summaries read,
  home-help follow-through).
- **Source:** guardian-surface views (once guardian auth lands, M-Gov) + mentor-relayed engagement in
  Pilot 1; homework completion as a proxy for home follow-through.
- **Target:** most guardians view progress at least weekly; positive qualitative feedback on trust +
  usefulness.
- **How measured:** dashboard/weekly-summary views per guardian per week; homework completion rate;
  guardian survey (consented, no PII).

## 6. Mentor workload

- **Definition:** how much load the mentor carries — interventions, escalation responses, review time —
  to keep the mentor:learner ratio sustainable.
- **Source:** mentor session notes (follow-up loop) + AI plan intervention counts + escalation counts.
- **Target:** sustainable at the Pilot-1 ratio (≈ 1:10); escalation response within the safeguarding
  SLA; no mentor overwhelmed.
- **How measured:** interventions per mentor per day; escalation response time; mentor-reported load;
  ratio held without safety degradation.

## 7. AI Teacher intervention quality

- **Definition:** does the AI Teacher help — good style/difficulty choices, accurate weak-topic +
  misconception detection, well-timed escalation, calibrated confidence.
- **Source:** AI plan (weak topics, difficulty), guardrail (escalate, confidence), outcomes after an
  intervention (mastery re-check / cleared misconception), mentor review.
- **Targets:**
  - **Grounding:** 100% grounded, non-generative, no-answer (proven by invariants — confirmed in field
    by zero grounding/answer incidents).
  - **Detection:** flagged weak topics + misconceptions match mentor judgement (precision/recall via
    mentor review).
  - **Escalation:** fires when (and only when) a learner is genuinely stuck; low false-negative rate
    (a missed stuck-learner is the failure mode to watch).
  - **Confidence calibration:** the teacher's confidence tracks actual subsequent performance.
- **How measured:** mentor agreement rate on flags/escalations; post-intervention mastery movement;
  confidence-band vs outcome; incident count for grounding/answer-leak (**target 0**).

---

## 8. Metric governance

- **Pseudonymous + consented:** every metric uses `student_ref` only, under guardian consent (M-Gov),
  in-region (FD-02), retention-bounded.
- **Safety overrides:** any **Tier-1 safety/governance issue open ⇒ pilot NO-GO**, regardless of the
  numbers ([RISK_REGISTER.md](RISK_REGISTER.md)).
- **Feeds the next cycle:** metrics + mentor feedback + AI Teacher evaluation
  ([AI_TEACHER_EVALUATION.md](AI_TEACHER_EVALUATION.md)) decide what content/policy is fixed before
  Pilot 2.

## 9. Pilot 1 success definition (summary)

Pilot 1 **succeeds** if: **zero unhandled safety incidents**; **no data loss / double-count**;
**measurable mastery gain**; lessons complete (online + offline); guardians + mentors find it useful +
trustworthy; accessibility includes every participant; and the mentor:learner ratio holds without
safety degradation. Then, and only then, → **Pilot 2** ([PILOT_PLAN.md](PILOT_PLAN.md)).
