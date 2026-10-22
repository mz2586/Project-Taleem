# AI Teacher — Safety Model

Status: **Phase 8 (templated tier, live) + Phase D (generative tier: built, flag-off, no model
connected).** The guardrails that keep the AI Teacher safe, curriculum-aligned, and honest (WS4).
Companion to [AI_TEACHER_ARCHITECTURE.md](AI_TEACHER_ARCHITECTURE.md). The overriding rule: **child
safety first; what children receive is authored content; the teacher never reveals the answer, and
hands off to a human when uncertain.** §§1–8 describe the templated tier children use today; §9
describes the generative tier's controls, which exist in code but serve no child — no model is
connected ([FD-03](docs/decisions/FD-03-ai-provider-residency.md)).

---

## 1. The safety envelope (every response is self-certified)

Each response carries a **`GuardrailReport`** — the teacher certifying its own output:

| Field | Guarantee | How it holds |
| --- | --- | --- |
| `grounded` | every utterance is authored content or a fixed system phrase | `is_grounded()` verifies each text ∈ the lesson's authored set ∪ system phrases |
| `generative` = false | no generative model produced any of the `utterances` | the runtime is templated; generated text, if any, is reported separately (§9) and never certified here |
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
- The generative tier (rephrasing only, behind the `LLMGateway` port) exists but is **off** (feature
  flag default off; no provider configured in any environment) and **never runs offline** (AR-C-06).
  It can only rephrase already-chosen authored utterances, and every output is re-checked by the
  safety gate in §9 before delivery; it never sources curriculum. Hallucination is *not* impossible
  for that tier — the gate reduces it and is honest about its known gap (§9).

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
- **No open generation, no external calls** — the templated tier is deterministic, offline-capable,
  with no network dependency to teach. The generative tier has no network transport in this build.
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

- The templated tier does not generate, summarize, or paraphrase with a model. The generative tier
  (§9) may only paraphrase, behind every control listed there, and no model is connected to it.
- It does not decide high-stakes outcomes (promotion is mentor-mediated).
- It does not replace the human safety layer — it escalates to it.

The AI Teacher is safe because it is **small, deterministic, grounded, and honest** — and because it
knows when to stop and call a human.

## 9. The generative tier's controls (Phase D — implemented, not serving children)

Code: `application/ai_teacher_service.py` (wiring), `domain/ai_teacher_gate.py` (prompt + gate),
`ports/llm.py` + `ports/llm_inert.py` (gateway, stub, inert adapter, ledger, quota). Every control
fails **closed**, and every failure serves the authored response unchanged — refuse, never soften.

**Order of checks on each `:explain` request**

1. **Feature flag** `ai_teacher.generative_rephrase` — default **off**; with it off nothing else is
   consulted and the response is byte-identical to the templated tier (tested).
2. **Kill switch** disengaged (also enforced for the whole route by middleware).
3. **No pending escalation** — a learner being handed to a human is not given a model.
4. **Live `ai_teaching` consent** — read from the identity context per request; a withdrawal takes
   effect on the next request; an unreadable state counts as no consent.
5. **Per-learner quota** — calls/tokens per UTC day (`TALEEM_AI_LEARNER_DAILY_CALLS`/`_TOKENS`),
   counted in a shared ledger (`learning.ai_usage_ledger`) holding counts and the pseudonymous
   `student_ref` only. Exhaustion, or an unreadable ledger, means the authored engine — not an error.
6. **Grounded prompt** — built solely from published `LessonView` fields (each passage keeps its field
   path as provenance); never answer options, learner identifiers, mastery, or attempts. If no
   grounding can be established, the model is not called (`unverifiable`).
7. **Provider** — none is connected. With no provider configured (every environment) no generative
   tier is composed; a named provider is `InertProviderGateway`, which has no transport and refuses
   every call; the test stub is refused in production.
8. **Output safety gate** — any one violation refuses the output:
   - *grounding*: numbers (digits, Urdu digits, number words, fractions) not in the grounding; low
     content-word overlap; comparison/universality words ("always", "bigger") not in the grounding;
   - *answer leak*: answer-revealing phrasing, or an item's correct option appearing more than in the
     grounding (released only after that item's hint ladder is exhausted, which `:explain` never
     asserts because hint state is client-reported);
   - *age band*: total length, sentence length, novel long words;
   - *safety*: URLs, emails, phone numbers, social handles, requests for personal data, secrecy or
     meeting requests, claims to be human, prompt-injection echoes, markup, unsafe vocabulary;
   - *locale*: script mismatch; unsupported locales are refused.

**Labelling and logging.** An accepted rephrase appears only in a separate `generation` block with
`generated: true`, `verified: false`, `grounded_on` provenance, and a `notice_key` the client must
show; the verified `utterances` are untouched, so verified curriculum is always distinguishable from
generated text. Each decision emits a structured safety event (decision, rule ids, lesson, locale,
band, provider, counts, a truncated hash of the output) through the allow-list logger — no generated
text and no learner identifier.

**Known limits — why this is not yet safe for children.**

- The gate is lexical. A misstatement composed only of grounded words (e.g. swapping numerator and
  denominator roles) **passes**; a semantic grounding check is required.
- Its evaluation is against scripted stub outputs only
  ([AI_TEACHER_EVALUATION.md](AI_TEACHER_EVALUATION.md) §8), not a real model.
- Not implemented: distress detection, transcript retention and human review of AI turns, a set
  retention period for the usage ledger (a purge hook exists), and an external red-team.
- Enabling for children requires every approval listed in the FD-03 brief.
