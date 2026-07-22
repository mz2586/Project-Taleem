# AI Teacher — Interaction Model

Status: **Phase 8.** How the AI Teacher interacts with a learner turn by turn — the teaching engine,
adaptive learning, and assessment support. Companion to
[AI_TEACHER_ARCHITECTURE.md](AI_TEACHER_ARCHITECTURE.md). Everything here is deterministic, grounded,
and explainable; nothing is generated.

---

## 1. The teaching loop (reuses the session flow)

```text
start → next (decide) → teach/explain → ask → answer → feedback → (continue | advance | remediate
        | review | escalate) → … → complete
```

- **next** — the decision engine picks the objective + intent (`diagnose/teach/continue/review/
  remediate/advance/revise/escalate`) with a rationale.
- **explain / teach** — the AI Teacher presents authored content in a chosen **explanation style**.
- **ask** — poses an authored item prompt (never the answer).
- **answer** — the scorer grades (server-side), evidence is recorded, mastery updates.
- **feedback** — authored affirmation (correct) or authored misconception correction (incorrect).
- **hint** — the authored graduated ladder (H1 → H2 → H3), never revealing the answer.
- **escalate** — hand off to a human on repeated confusion.

---

## 2. Explanation styles (WS1 — multiple explanation styles)

Four **deterministic arrangements** of the same authored content (title, explanation, worked steps,
and — for question-led — the first item prompt). No new content is created.

| Style | Arrangement | When chosen (policy) |
| --- | --- | --- |
| `direct` | title → explanation | default / middle learners, first pass |
| `worked_example_led` | title → explanation → worked steps | early-grade learners (show alongside telling) |
| `concrete_to_abstract` | title → worked steps → explanation | **after an incorrect attempt** (re-teach concretely, then the rule) |
| `question_led` | title → a leading question → explanation → worked steps | senior learners after a first pass (prompt retrieval first) |

`choose_style(grade_band, attempts, last_incorrect)` is a pure, explainable policy; a caller may also
request a specific style. The chosen style is returned in the response `rationale`.

**Age-appropriate responses** (WS1): the style + register are selected by `grade_band`
(`early`/`middle`/`senior`, from the learner profile). Younger learners get worked-example-led delivery;
stronger learners get question-led retrieval. The *content* is authored per grade; the AI Teacher
adapts only the *arrangement*.

---

## 3. Step-by-step tutoring (WS1)

The AI Teacher walks a learner through an objective item by item, reusing the session flow:

1. Explain (chosen style) → 2. Ask an item → 3. On a wrong answer, deliver the **authored misconception
   correction** + offer the next **graduated hint** → 4. Re-ask a parallel item → 5. On repeated
   failure after H3, **escalate to a mentor**. The teacher never states the answer before H3 and never
   reveals the correct option.

---

## 4. Adaptive learning (WS2)

`GET …/ai-teacher/plan` returns a derived, explainable plan:

- **Weak-topic detection** — objectives that are `in_progress`/`needs_review`/`at_risk` or carry an
  active misconception, weakest-mastery first, each with a reason.
- **Revision planning** — objectives whose spaced re-check is due (from the forgetting schedule).
- **Personalized practice** — for each objective, the recommended **difficulty** (`INTRO`/`CORE`/
  `STRETCH`, from mastery state) and the teacher's **confidence**.
- **Difficulty adaptation** — `recommended_difficulty(state, mastery)`: not-started → INTRO; shaky →
  INTRO; progressing → CORE; at-risk/needs-review → CORE (re-consolidate); mastered → STRETCH.
- **Learning recommendations** — the next action from `select_next`, with its rationale.

Everything is derived from the existing `StudentKnowledge` + decision engine — no new data, no
prediction beyond the calibrated model.

---

## 5. Assessment support (WS3)

Reuses the session/answer path and the templated runtime:

- **Explain incorrect answers** — the wrong option maps to an **authored** misconception; the runtime
  returns the **authored correction** (never an invented one).
- **Generate hints** — the **authored** graduated ladder, surfaced one level at a time.
- **Recommend remediation** — a confirmed misconception routes to `REMEDIATE` (decision engine /
  `RemediationRoute`).
- **Detect misconceptions** — the scorer + `StudentKnowledge` track suspected → confirmed → cleared
  (and recurrence).
- **Encourage mastery** — authored affirmations on success; the plan surfaces near-mastery objectives
  to consolidate. Encouragement is effort-focused and never comparative.

---

## 6. Confidence + escalation (surfaced every turn)

- **Confidence indicator** — `low`/`medium`/`high`, calibrated from the BKT **uncertainty** + evidence
  count. Low by default (little evidence) — the teacher is honest about what it doesn't yet know.
- **Escalation** — the teacher hands off to a human when the decision engine requests it or after
  repeated failures post-help; the response carries `escalate` + `escalate_reason`. In the supervised
  pilot the mentor is present; offline, the escalation is queued (see
  [AI_TEACHER_OFFLINE.md](AI_TEACHER_OFFLINE.md)).

---

## 7. Explainability contract

Every AI Teacher response includes:

- the **content** (authored utterances), the **style**, the **confidence**;
- a **rationale** (why this style, attempts, grade band, next action);
- a **guardrail report** (grounded / non-generative / in-curriculum / never-reveals-answer /
  age-appropriate / escalate).

A mentor or reviewer can reconstruct exactly why the teacher said what it said — the definition of
"explainable" for this platform.
