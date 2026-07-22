# AI Teacher — Safety Model

Status: **Phase 8.** The guardrails that keep the AI Teacher safe, curriculum-aligned, and honest
(WS4). Companion to [AI_TEACHER_ARCHITECTURE.md](AI_TEACHER_ARCHITECTURE.md). The overriding rule:
**child safety first; the teacher never generates, never hallucinates, never reveals the answer, and
hands off to a human when uncertain.**

---

## 1. The safety envelope (every response is self-certified)

Each response carries a **`GuardrailReport`** — the teacher certifying its own output:

| Field | Guarantee | How it holds |
| --- | --- | --- |
| `grounded` | every utterance is authored content or a fixed system phrase | `is_grounded()` verifies each text ∈ the lesson's authored set ∪ system phrases |
| `generative` = false | no generative model produced any word | the runtime is templated; there is no model in this tier |
| `source` = "authored" | provenance is authored curriculum | content only ever comes from a published `LessonView` |
| `reveals_answer` = false | the correct option is never emitted | offline content has no answer keys; explanations use prompts, not answers |
| `within_curriculum` | the objective is a published, in-scope objective | the read model exposes only published lessons |
| `age_appropriate` | style + register match the learner's grade band | style chosen by `grade_band`; content authored per grade |
| `escalate` (+ reason) | uncertainty hands off to a human | decision `ESCALATE` or repeated failure |
| `confidence` | honest low/medium/high | calibrated from BKT uncertainty + evidence |

---

## 2. Curriculum grounding (WS4)

- The AI Teacher can only ever emit content present in the supplied `LessonView` (the Curriculum
  Studio → learning read-model boundary projects **published** lessons only). Off-curriculum content is
  structurally unreachable.
- `is_grounded(lesson, utterances)` is a runtime self-check: the set of emitted texts must be a subset
  of the lesson's authored texts (title, explanation, worked steps, item prompts, hints, corrections)
  plus a small whitelist of fixed system phrases (affirmation / generic re-try). A test asserts a
  fabricated utterance is flagged ungrounded.

## 3. No hallucinated facts (WS4)

- The teacher is **templated**: it arranges and selects authored content; it does not synthesize text.
  Hallucination is not "prevented" — it is **impossible** in this tier because there is no generator.
- The future generative tier (rephrasing only, behind the `LLMGateway` port) is **off for children and
  off offline** (AR-C-06). If ever enabled for a non-child surface, it would rephrase already-grounded
  content and be re-checked by the guardrail before delivery — it would never source curriculum.

## 4. Age-appropriate language (WS4)

- Content is authored per grade (framework §Content Standards); the teacher selects the **delivery
  arrangement** by `grade_band` (early → worked-example-led; senior → question-led). The register is
  the authored, child-safe, Urdu-first register that already passed the Language + Child-Safety review
  gates in the production pipeline.

## 5. Safety checks (WS4)

- **Never reveals the answer** — no response ever contains the correct option; hints are the authored
  graduated ladder and never state the answer before H3.
- **No child PII** — the teacher operates on the pseudonymous `student_ref` only; nothing it emits asks
  for or contains personal data.
- **No open generation, no external calls** — deterministic, offline-capable, no network dependency to
  teach.
- **Deny-by-default authorization** — PDP-authorized (`operate learning.session` / `read
  learning.knowledge`), IDOR-guarded (a learner reaches only their own data; mentors may read any).
- **Mentor-mediated summative** — the teacher never auto-promotes; summative identity is human.

## 6. Confidence indicators (WS4)

- `confidence_from(mastery, attempts)` calibrates the teacher's confidence in the *learner's state*
  from the model's **uncertainty** and the **evidence count**: HIGH only when the estimate is precise
  *and* backed by evidence; LOW with little evidence or a wide estimate (the honest default). The
  indicator is surfaced on explanations and in the adaptive plan so mentors + learners see how sure the
  teacher is.

## 7. Escalation when uncertain (WS4)

- The teacher hands off to a human when the decision engine returns `ESCALATE` (e.g. a safety signal)
  or after **repeated failures post-help** (default: 3 consecutive). The response sets `escalate` +
  `escalate_reason`. In the supervised pilot the mentor is physically present; offline, the escalation
  is **queued** and the child is directed to the present mentor (see
  [AI_TEACHER_OFFLINE.md](AI_TEACHER_OFFLINE.md)). Automated remote crisis-flag routing is the
  M-Safe-gated 6.2C item — not part of the teacher's own logic.

## 8. What the safety model deliberately does NOT do

- It does not generate, summarize, or paraphrase with a model (no LLM in this tier).
- It does not decide high-stakes outcomes (promotion is mentor-mediated).
- It does not replace the human safety layer — it escalates to it.

The AI Teacher is safe because it is **small, deterministic, grounded, and honest** — and because it
knows when to stop and call a human.
