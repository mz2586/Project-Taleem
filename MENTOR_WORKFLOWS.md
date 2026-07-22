# Mentor / Supervisor Workflows

Status: **Phase 9 — Pilot Operations & Guardian Experience.** Designs the mentor/supervisor experience
for the first supervised pilot as a **composition of existing mentor-privileged surfaces** — the
Learning read models, the AI Teacher plan + guardrail escalation, and the Assessment engine. **No
architecture redesign; no new child-data table.** Companion to
[GUARDIAN_EXPERIENCE.md](GUARDIAN_EXPERIENCE.md), [PILOT_RUNBOOK.md](PILOT_RUNBOOK.md),
[END_TO_END_VALIDATION.md](END_TO_END_VALIDATION.md).

> **Reuse.** The `mentor` role already exists in the PDP with `read learning.knowledge` +
> `read learning.session` for **any** learner (privileged reads; a mentor is not IDOR-limited to one
> child). Every workflow below runs over surfaces that already exist. A **cross-cohort roster** (list
> all my learners) needs admin/enrolment (cohort = child-linkage) which is **governance-gated
> (M-Gov)**; per-learner intervention data is fully available today. In Pilot 1 the mentor is
> **physically present** — the primary safety layer.

---

## 0. Reuse map — every mentor view is an existing surface

| Mentor view | Existing surface reused |
| --- | --- |
| Learner overview (per child) | `GET …/{ref}/knowledge`, `…/progress`, `…/today`, `…/history` (mentor-privileged) |
| Students needing intervention | `GET …/{ref}/ai-teacher/plan` — `weak_topics` + escalation signals |
| AI Teacher escalation review | `guardrail.escalate` + `escalate_reason` from `:explain`; decision `ESCALATE`; `consecutive_failures` |
| Progress analytics | `GET …/{ref}/progress` (LearningAnalytics summary) |
| Assessment review | `GET …/{ref}/assessments` (`mentor_mediated` summative + constructed items) |
| Follow-up workflow | mentor loop over the above + on-site action + session notes |

Cohort/roster + assignment: **admin/enrolment (M-Gov)**. Per-learner data: **available now**.

---

## 1. Learner overview

- **Purpose:** understand one learner's state at a glance.
- **Content:** mastery model (`knowledge`), progress summary (`progress`), today's focus (`today`),
  and recent history (`history`) — objectives, states (`not_started`/`in_progress`/`mastered`/
  `needs_review`/`at_risk`), active misconceptions, attempts.
- **Data:** mentor-privileged reads (the mentor is not IDOR-limited). Pseudonymous `student_ref`; no
  PII.

## 2. Students needing intervention

- **Purpose:** triage — who needs help now.
- **Content:** for each learner, the AI Teacher's **weak topics** (state in
  `in_progress`/`needs_review`/`at_risk` or an **active misconception**, weakest-mastery first, each
  with a reason) and any **escalation** flag.
- **Signal source:** `ai-teacher/plan.weak_topics` + `guardrail.escalate`. Deterministic + explainable
  (the AI Teacher is templated) — the mentor can see *why* a learner is flagged.
- **Cross-cohort ranking** (all my learners, sorted by need) composes per-learner plans; the roster
  that enumerates "my learners" is admin/enrolment (M-Gov).

## 3. AI Teacher escalation review

- **Purpose:** review + act on every hand-off the AI Teacher makes to a human.
- **When the teacher escalates:** the decision engine returns `ESCALATE`, or a learner has **repeated
  failures after help** (default 3) — the response carries `escalate: true` + `escalate_reason`.
- **Mentor action:** read the escalate reason + the learner's recent interactions (`history`,
  `knowledge`), intervene **in person** (Pilot 1), and record the outcome. Offline, escalations queue
  and the child is directed to the **present** mentor immediately
  ([AI_TEACHER_OFFLINE.md](AI_TEACHER_OFFLINE.md)). Automated remote crisis-flag routing is the
  **M-Safe-gated** 6.2C item, not part of the teacher's logic.
- **Safeguarding:** a wellbeing/distress escalation always takes priority and follows the safeguarding
  runbook ([INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md)); the mentor never handles a serious concern
  alone.

## 4. Progress analytics

- **Purpose:** see how a learner (and, across learners, the cohort) is progressing.
- **Content:** the LearningAnalytics progress summary (`progress`) — mastered / in-progress counts,
  trajectory, review load.
- **Data:** derived from append-only evidence + outbox; the same source of truth the guardian sees.

## 5. Assessment review

- **Purpose:** the mentor owns the **mentor-mediated summative** and reviews constructed answers.
- **Content:** available assessments (`assessments`), with formative auto-graded and **summative
  flagged `mentor_mediated`**; constructed "explain / show your working" items are reviewed by the
  mentor, not auto-graded.
- **Non-negotiable:** the platform **never auto-promotes** a child; mastery confirmation at summative
  is the mentor's judgement over the auto-graded evidence + constructed answers.

## 6. Follow-up workflow

A simple, human loop over existing data (no new workflow engine — the mentor is present):

1. **Triage** — open "students needing intervention" (AI plan weak topics + escalations).
2. **Diagnose** — read the learner's `knowledge` + `history`; identify the misconception/objective.
3. **Act** — reinforce the **authored** misconception correction in person; route the learner to the
   right revision lesson/difficulty (the AI plan recommends it).
4. **Note** — record what happened (session note) — a primary pilot feedback signal (WS5 metrics).
5. **Re-check** — confirm on the next session (mastery re-check / cleared misconception).

The loop feeds the **mentor feedback** input to the next content + policy cycle
([PILOT_SUCCESS_METRICS.md](PILOT_SUCCESS_METRICS.md), [AI_TEACHER_EVALUATION.md](AI_TEACHER_EVALUATION.md)).

---

## 7. Mentor guardrails + load

- **Privileged, not unlimited:** a mentor reads any learner's *learning* data (C2) — never child PII
  (C3), never another mentor's private notes; deny-by-default PDP holds.
- **Workload is measured** (WS5): interventions per mentor per day, escalation response time, review
  time — to keep the mentor:learner ratio sustainable (Pilot 1 ≈ 1:10, tightened first, relaxed only
  when proven).
- **Present + primary:** in the supervised pilot, the mentor's attention is the primary safety
  mechanism; the software surfaces the signals, the human acts.

---

## 8. What lands with M-Gov / admin (not built here)

The **cohort roster + mentor↔learner assignment + a persisted follow-up/notes store** land with
admin/enrolment (M-Gov / WS8). Per-learner intervention, escalation, analytics, and assessment-review
data **already exist** and are mentor-readable today. Phase 9 designs the workflows over them; nothing
here requires new architecture.
