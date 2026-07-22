# AI Teacher — Evaluation Approach

Status: **Phase 8.** How we evaluate the AI Teacher — safety, correctness, pedagogy, and learning
outcome — before and during the pilot. Companion to [AI_TEACHER_SAFETY_MODEL.md](AI_TEACHER_SAFETY_MODEL.md).
Because the teacher is **deterministic and templated**, much of its behaviour is *provable*, not just
sampled — a major evaluation advantage over a generative system.

---

## 1. What we evaluate

| Dimension | Question | Method |
| --- | --- | --- |
| **Safety** | Does it ever emit non-authored content, reveal an answer, or fail to escalate? | Property tests (proofs) + red-team |
| **Grounding** | Is every utterance authored? | `is_grounded` unit tests + a batch scan over all published lessons |
| **Correctness** | Are explanations, hints, and corrections the authored, correct ones? | Golden tests + content QA (pipeline) |
| **Pedagogy** | Do styles, difficulty, and remediation help learning? | Mentor review + pilot outcome data |
| **Explainability** | Can a mentor reconstruct why the teacher acted? | Rationale + guardrail present on every response (tested) |
| **Learning outcome** | Do learners gain mastery? | Mastery-gain measurement in the pilot |

---

## 2. Deterministic property tests (proofs, not samples)

Because the teacher is pure + deterministic, we assert **invariants** that hold for *all* inputs, not
just examples:

- **Grounding invariant** — for every published lesson and every style, `is_grounded(...) is True`
  (no style ever emits non-authored text). A fabricated utterance is flagged ungrounded.
- **No-answer invariant** — no explanation contains an item's correct option; question-led never
  surfaces the answer.
- **Non-generative invariant** — `guardrail.generative is False` always; `source == "authored"`.
- **Confidence calibration** — HIGH requires precise estimate + evidence; LOW with no evidence.
- **Style determinism** — `choose_style` returns the same style for the same state (reproducible).
- **Escalation** — repeated failure / decision `ESCALATE` sets `escalate` with a reason.

These live in `tests/test_ai_teacher.py` and run on every commit (backend quality gate). A
**batch-grounding scan** over the whole published catalogue is a pipeline QA step before a grade ships.

---

## 3. Golden + regression tests

- **Golden explanations** — for representative lessons, the exact styled arrangement is asserted, so a
  content or ordering regression fails loudly.
- **Golden plans** — for a seeded learner state, the adaptive plan (weak topics, difficulty, next
  action) is asserted, so a policy change is caught.

---

## 4. Human review (the pipeline gates)

Every lesson the teacher can deliver has already passed the production pipeline
([CONTENT_PRODUCTION_PIPELINE.md](CONTENT_PRODUCTION_PIPELINE.md)): subject-expert, instructional-
design, accessibility, language, and **child-safety** review. The AI Teacher inherits that human
sign-off — it never delivers unreviewed content. Mentors additionally review the teacher's behaviour in
Pilot 0 (dry run) against the safety + pedagogy checklists.

---

## 5. Red-team / adversarial checks

- Attempt to make the teacher emit off-curriculum content (should be impossible — grounding).
- Attempt to extract an answer via explanations/hints (should never surface the correct option).
- Attempt to reach another learner's data (IDOR-guarded → 403).
- Drive repeated failure and confirm escalation fires with a reason.
- Confirm no generative path exists offline (capability matrix asserts `disabled_offline`).

---

## 6. Pilot-time evaluation (learning outcome + safety)

During the supervised pilot (PILOT_PLAN Pilot 1):

- **Mastery gain** — pre/post mastery on taught objectives (a Pilot-1 success criterion), from the
  append-only evidence.
- **Safety incidents** — target **zero unhandled**; every escalation reaches a present mentor within
  SLA.
- **Engagement** — session completion, return rate, hint usage patterns.
- **Confidence calibration in the field** — does the teacher's confidence track real learner
  performance? (compare confidence bands to subsequent outcomes).
- **Mentor feedback** — where the teacher's style/difficulty choices helped or hindered; feeds the next
  content + policy cycle.

---

## 7. Evaluation gates (before enabling anything new)

- **No content ships** unless it passes the pipeline + the batch-grounding scan.
- **No policy change** (styles, difficulty, escalation thresholds) ships unless golden tests + property
  tests pass and a mentor reviews the effect.
- **No generative tier** is enabled for children (AR-C-06) — its evaluation bar (independent safety
  review, red-team, human-in-loop) is a separate, later, gated exercise.

The AI Teacher is evaluated the way you evaluate a **calculator, not an oracle**: prove the invariants,
golden-test the behaviour, human-review the content, and measure the learning.
