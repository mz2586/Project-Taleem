# Learning Decision Engine

Status: Design (Phase 4, pre-implementation). Grounds every automated learning decision in
[LEARNING_SCIENCE_FRAMEWORK.md](LEARNING_SCIENCE_FRAMEWORK.md) and reads the
[STUDENT_MODEL.md](STUDENT_MODEL.md). This is the **policy layer**: given a learner's state and the
curriculum, it decides *what happens next*. It contains no UI, no LLM, and no I/O — it is a set of
**pure, deterministic, testable decision functions**. That purity is deliberate: learning decisions
must be explainable, reproducible, and unit-testable to ≥95% (Master Overview quality bar), which is
impossible if they are tangled with prompts or database calls.

Core design rule: **the engine decides; it does not act.** It returns a `Decision` (a value); the
Session Engine and AI Runtime execute it. Every decision carries a `rationale` so it can be shown to
a mentor/parent ("why is my child doing this?") — explainability is a first-class output, not an
afterthought.

---

## 1. Responsibilities (from the brief)

1. **Lesson selection** — what to teach/learn next.
2. **Revision scheduling** — when a mastered objective returns for spaced retrieval.
3. **Difficulty adaptation** — keep practice at the edge of ability.
4. **Hint policy** — how much help, when.
5. **Explanation policy** — how to (re-)explain when the learner is stuck.
6. **Mastery thresholds** — when an objective counts as mastered.
7. **Completion rules** — when a lesson/session/objective is done.

Each is a pure function of `(StudentModel slice, Curriculum slice, policy config, clock)`. Policy
config is externalized (§9) so parameters are tuned from data, not code changes.

---

## 2. The decision inputs and output

```text
decide_next(student_state, curriculum_graph, config, now) -> Decision

Decision =
  | Diagnose(objective, item_selection)                  # narrow uncertainty (cold-start/placement)
  | Teach(objective, lesson_ref, presentation_plan)      # new learning
  | Review(objective, item_selection, mode=retrieval)    # spaced retrieval
  | Remediate(objective, misconception_ref, route)       # clear a misconception
  | Assess(objective, blueprint_ref)                      # formative check
  | Consolidate(objectives)                               # mixed practice / interleaving
  | EscalateToMentor(reason, evidence)                    # human handoff
  | Rest(reason)                                          # stop — wellbeing / daily cap reached
  + rationale: explainable trace of the rule(s) that fired
```

The **Rest** and **EscalateToMentor** outcomes are as important as the teaching ones: the engine can
decide the best next action is *to stop* or *to involve a human*. Child safety and wellbeing are
encoded as decisions, not exceptions.

### 2.1 Cold-start / placement (design-review F2 — the new-learner path)

A brand-new learner has **no evidence**, and absence of evidence must never be read as
non-mastery. The engine therefore treats a new learner explicitly:

- Objectives start at `mastery = prior(grade, objective)` with **high uncertainty** (STUDENT_MODEL
  initial-estimate policy) — a *guess we know we're unsure of*, not a claim of zero knowledge.
- When an objective on the critical path has high `mastery_uncertainty`, the engine emits
  **`Diagnose`** — a short adaptive retrieval over that objective (and its prerequisites) whose sole
  job is to **narrow uncertainty** before committing effort. `Diagnose` is preferred over `Teach`
  when uncertainty is high, so we don't re-teach what the child already knows or push past a hidden
  gap.
- As diagnostics resolve uncertainty, the learner "falls into" the right place in the DAG — the
  platform *meets the child where they are* rather than starting everyone at objective 1. Once
  uncertainty is low, normal selection (§3) resumes.

This makes onboarding a first-class, testable path, not an afterthought — and it is a prerequisite
for the platform's core promise of personalization.

---

## 3. Lesson selection (Mastery Learning + prerequisite DAG)

Selection walks the curriculum DAG and the Student Model to find the highest-value eligible next
objective. Algorithm (deterministic, ordered):

1. **Safety/wellbeing gate.** If a distress or frustration signal is active → `EscalateToMentor` or
   `Rest`. Nothing else runs first.
2. **Due reviews first (bounded).** If objectives are `at_risk`/`needs_review` and the daily review
   budget isn't spent → prefer `Review` (spacing wins over new material when retention is in danger —
   FRAMEWORK §9). Bounded by a daily cap so review debt can't starve progress.
3. **Open misconceptions.** If a confirmed misconception blocks an in-progress objective →
   `Remediate` via its authored route before anything new.
4. **Eligible new learning.** Among objectives whose prerequisites are all `mastered`, pick by a
   **value score**: `curriculum priority × readiness × (1 − mastery)`, tie-broken by DAG depth
   (unblock the most downstream work) and curriculum sequence. Never select an objective with an
   un-mastered prerequisite — the Mastery invariant.
5. **Interleaving.** Within a subject, once several related objectives are `in_progress`, prefer
   `Consolidate` (interleaved practice) over always pushing new material — interleaving improves
   discrimination and durable learning.
6. **Nothing eligible** (all mastered, none due) → `Consolidate` enrichment or `Rest`.

Eligibility = prerequisites mastered **and** not currently `at_risk` for a *prerequisite* (you don't
teach division to a child who has just been shown to have forgotten multiplication — you review
first). This is the DAG + forgetting model working together.

---

## 4. Revision scheduling (Spaced Repetition + Retrieval Practice)

- On mastery of an objective, the engine (via the Student Model's `ForgettingModel`) sets
  `next_review_at` so the review lands when predicted recall dips to the target retrievability band
  (challenging-but-recallable — a desirable difficulty).
- Each successful spaced **retrieval** expands the next interval; each failure contracts it and may
  demote the objective from `mastered`. Reviews are **retrieval-first** (recall before re-teach).
- **Prioritization when reviews compete** (more due than the daily cap): rank by
  `retention_risk × objective_value` — objectives most likely to be forgotten *and* most important
  (foundational, or prerequisites of upcoming work) go first. Overflow rolls to the next day; chronic
  overflow raises a mentor signal (the child may be over-loaded).
- **Interleaved review** mixes objectives rather than blocking by topic (better than massed review).
- All scheduling is **offline-computable**: `next_review_at` is a stored value; a device with no
  connectivity can still present due reviews and reconcile results on sync.

## 5. Difficulty adaptation (Deliberate Practice + desirable difficulty)

- The engine targets a **success-rate band** per learner × objective (e.g., keep observed success in
  a "productive struggle" window — high enough to sustain motivation, low enough to be learning). The
  exact band is policy config, tuned from data, not asserted here as gospel.
- Below the band (too hard → failure/frustration) → step down: more scaffolding, worked examples,
  smaller steps, easier item variants. Above the band (too easy → boredom, expertise reversal) → step
  up: fade support, harder variants, less scaffolding.
- Difficulty selection targets **known weaknesses/misconceptions** (deliberate practice), not random
  items — the engine asks the Student Model "what does this child get wrong?" and practices that.
- The **worked-example → completion → independent** fade (FRAMEWORK §6) is a difficulty rung driven by
  mastery: novices study examples; as mastery rises, steps are blanked, then removed.

## 6. Hint policy

Hints are **graduated and bounded** — the authored `hints` ladder from the lesson, governed by the
AI teaching object's `hint_policy` (never answer-first; cap before escalation).

- On an incorrect/uncertain attempt: give the **next** hint in the ladder (least-to-most help), not
  the answer. Escalate hint level only on repeated struggle on the same item.
- **Cap.** After a configured number of hints without success on an item, stop hinting and choose a
  different action: re-explain (§7), step difficulty down (§5), or — if struggle persists across
  items — `EscalateToMentor`. A child is never left grinding a single item indefinitely (wellbeing).
- Hint usage is **evidence** (Student Model): heavy hint reliance caps the mastery estimate (they
  didn't do it independently) and feeds difficulty adaptation.

## 7. Explanation policy

When the learner is stuck after hints, the engine decides *how to re-explain*:

- Prefer an **alternative representation** (UDL): if the first explanation was verbal, try a visual/
  worked example; switch modality (narrate + show) to cut extraneous load (CLT).
- Target the **specific misconception** if one is detected (use the authored correction), rather than
  repeating the same explanation louder.
- Explanations come **only from approved lesson content** (the authored `student_explanation`,
  `worked_examples`, `common_misconceptions` corrections) — the AI Runtime rephrases within scope but
  the engine never invents new curriculum (Master Overview: "The AI must never invent curriculum
  content"). If approved content is exhausted and the child is still stuck → `EscalateToMentor`.

## 8. Mastery thresholds and completion rules

- **Mastery threshold** is **per objective** (a `mastery_policy` attached to each SLO): a foundational
  numeracy fact requires higher mastery *and* lower uncertainty than an enrichment objective.
  Threshold = `mastery ≥ τ(objective) AND uncertainty ≤ u(objective) AND no confirmed misconception`.
  Requiring low uncertainty prevents "mastered on one lucky attempt."
- **Objective complete** = mastered (above) — then it enters the spaced-review lifecycle.
- **Lesson complete** = its target objectives reach `in_progress` with the session's teaching goals
  met (not necessarily mastered — mastery may take several sessions + reviews). Completion of *teaching*
  ≠ mastery; the model tracks both.
- **Session complete** = the session plan is done, or a time/effort budget is reached, or a
  wellbeing/Rest decision fires. Sessions are **time-and-effort-boxed** for young learners; the engine
  will end a session to protect attention/wellbeing even if the plan isn't finished.
- **Promotion / summative** decisions are **never** made autonomously — the engine can recommend
  readiness, but promotion-bearing assessment is **human-identity-assured and mentor-confirmed**
  (doc 58). The engine's authority stops at recommendation.

---

## 9. Policy configuration and explainability

- Every parameter (review caps, success bands, hint caps, thresholds, interval targets) lives in an
  **externalized, versioned policy config**, not in code. This is the FRAMEWORK §10 commitment:
  we tune from *our* data, and every change is auditable and A/B-testable.
- Every `Decision` carries a **rationale** — the ordered list of rules that fired and the inputs that
  triggered them ("2 objectives at_risk within review budget → Review; picked MATH-G2-N-03 by
  retention_risk 0.81"). This powers the mentor/parent "why" view and is asserted in tests.
- Decisions are **deterministic** given `(state, config, now)` — same inputs, same decision. No
  randomness in the core (any exploration/variety is an explicit, seeded, logged policy, not hidden
  nondeterminism), so behavior is reproducible and testable.

---

## 10. Boundaries and testability

- **Pure domain.** The engine imports no framework, no LLM, no DB — only domain types, policy config,
  and an injected clock. This is what allows ≥95% coverage on the "critical learning logic" the
  Master Overview demands, with fast, deterministic unit tests over hand-built student states.
- **The engine never talks to the child.** It emits `Decision` values; the AI Teaching Runtime
  (AI_TEACHING_RUNTIME) turns a `Teach`/`Review`/`Remediate` into an actual, safety-checked
  interaction, and the Session Engine sequences them.
- **Safety supersedes optimization** at every branch: the safety/wellbeing gate is evaluated first in
  every decision, and `EscalateToMentor`/`Rest` can preempt any "optimal" learning action.

Domain types for `Decision`, policies, and the engine's ports are in
[LEARNING_DOMAIN_MODEL.md](LEARNING_DOMAIN_MODEL.md).
