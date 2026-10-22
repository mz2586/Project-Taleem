# AI Teacher — Architecture

Status: **Phase 8. Implemented + documented.** The AI Teacher delivers personalized instruction while
remaining **safe, curriculum-aligned, and explainable** — as a **templated, deterministic
orchestration** over components that already exist. It is **not** a generative model (audit AR-C-06:
no generative AI to children; the offline tier is identical). Companions:
[AI_TEACHER_INTERACTION_MODEL.md](AI_TEACHER_INTERACTION_MODEL.md),
[AI_TEACHER_SAFETY_MODEL.md](AI_TEACHER_SAFETY_MODEL.md), [AI_TEACHER_EVALUATION.md](AI_TEACHER_EVALUATION.md),
[AI_TEACHER_OFFLINE.md](AI_TEACHER_OFFLINE.md).

---

## 0. Reuse, not redesign

The AI Teacher composes existing pieces; it adds an orchestration + guardrail + explanation-style layer.

| Capability | Existing component reused | New (Phase 8) |
| --- | --- | --- |
| Approved teaching content | `TemplatedTeachingRuntime` (present/ask/hint/affirm/correct) | arrangement into styles |
| Grounding boundary | `CurriculumStudioReadModel` → `LessonView` (published only) | `is_grounded` self-check |
| Mastery / misconceptions / spacing | `StudentKnowledge` (BKT, memory) | confidence calibration |
| Next-step decisions | pure decision engine (`select_next`, `post_interaction`) | adaptive plan composition |
| Scoring | `evaluate` scorer + `AssessmentEvidence` | (reused as-is) |
| Session flow | `SessionService` (start/next/teach/answer/hint/end) | `:explain` layer |
| Offline delivery | offline packages (6.2A/B/C-1) | capability matrix |

Implementation: `contexts/learning/domain/ai_teacher.py` (pure), `application/ai_teacher_service.py`
(wiring), `adapters/ai_teacher_api.py` (endpoints). No schema change, no new child-data table.

---

## 1. Design principles

- **Templated, not generative.** Every word the teacher emits is authored lesson content (or a fixed
  system phrase). It **cannot invent a fact or source new curriculum** — grounding is structural. The
  generative tier (behind the `LLMGateway` port) is a rephrasing layer whose plumbing exists (§5) but
  which has no model connected; it never sources curriculum, is **off by default**, and is **off
  offline**.
- **Curriculum-aligned by construction.** The teacher only ever sees a published `LessonView` (the
  Curriculum Studio → learning read-model boundary). Off-curriculum content is unreachable.
- **Explainable by default.** Every response carries a **rationale** (why this style, why this next
  step) and a **guardrail report** (grounded / non-generative / in-curriculum / never-reveals-answer /
  age-appropriate / confidence). Personalization is deterministic *arrangement* + *selection* — a human
  can trace exactly why the teacher did what it did.
- **Deny-by-default safety.** IDOR-guarded, PDP-authorized, no child PII (pseudonymous `student_ref`),
  mentor-mediated summative, escalation-to-human on repeated confusion.

---

## 2. Component architecture

```text
                         AI Teacher (application)
                                  │
        ┌───────────────┬─────────┼───────────┬────────────────┐
        ▼               ▼         ▼            ▼                ▼
  TemplatedRuntime   LessonView  StudentKnowledge  DecisionEngine   Scorer
  (approved content) (grounding) (mastery/uncert)  (next step)      (grade)
        │               │             │              │
        └── arrange ─── ground ─── calibrate ─── select ──► Explanation + Plan
                     (styles)   (is_grounded) (confidence) (adaptive)
                                     │
                              GuardrailReport (self-certification)
```

The AI Teacher is a thin, pure orchestration: it **arranges** authored utterances into an explanation
style, **grounds** them (verifies every text is authored), **calibrates** a confidence from the BKT
uncertainty, and **selects** the next step / weak topics from the decision engine + knowledge — then
**self-certifies** the whole response with a guardrail report.

---

## 3. The five workstreams, mapped to code

- **WS1 Teaching Engine** (`ai_teacher.explain`, `choose_style`): lesson explanation, guided teaching
  (worked-example-led), step-by-step tutoring (session `:teach`/`:answer`/`:hint`, reused), **multiple
  explanation styles** (DIRECT / WORKED_EXAMPLE_LED / CONCRETE_TO_ABSTRACT / QUESTION_LED —
  deterministic arrangements of authored content), **age-appropriate responses** (style + register by
  `grade_band`).
- **WS2 Adaptive Learning** (`ai_teacher.adaptive_plan`): weak-topic detection (states + misconceptions),
  revision planning (`due_reviews`), personalized practice (per-objective difficulty + confidence),
  difficulty adaptation (`recommended_difficulty`), learning recommendations (`select_next` +
  rationale).
- **WS3 Assessment Support** (reused `SessionService.submit_answer` + `runtime.correct`/`hint`):
  explain incorrect answers (authored misconception corrections), generate hints (authored graduated
  ladder), recommend remediation (`RemediationRoute` / decision `REMEDIATE`), detect misconceptions
  (`evaluate` + `StudentKnowledge`), encourage mastery (affirmations + mastery signals).
- **WS4 Guardrails** (`ai_teacher.guardrail_report`, `is_grounded`, `escalation_for`): curriculum
  grounding, no hallucinated facts (templated → structurally impossible), age-appropriate language,
  safety checks (never reveals the answer; no PII), **confidence indicators** (`confidence_from`),
  **escalation when uncertain** (repeated failure / decision `ESCALATE`).
- **WS5 Offline** (`ai_teacher.offline_capabilities`): the AI Teacher runs fully offline (templated +
  packaged); see [AI_TEACHER_OFFLINE.md](AI_TEACHER_OFFLINE.md).

---

## 4. API surface (derived; no new child tables)

- `POST /v1/learning/sessions/{id}:explain` `{objective_code, style?, grade_band?, locale?}` →
  `{utterances, style, confidence, grounded, guardrail, rationale}`.
- `GET /v1/learning/students/{ref}/ai-teacher/plan` → the adaptive plan.
- `GET /v1/learning/students/{ref}/ai-teacher/capabilities` → the offline capability matrix.

All authenticated, authorized, and IDOR-guarded (mirrors the existing session/student routers).
Contract: `packages/contracts/ai-teacher.openapi.yaml`.

---

## 5. Where the generative tier fits (Phase D: built, off, no provider connected)

The Master AI strategy is *Curriculum → Retrieval → small model → safety → frontier LLM*. The
templated tier above is the floor, and it is what children receive today. Phase D adds the
**plumbing** for a generative tier that can only **rephrase** the utterances the templated teacher
already chose. It is not connected to any model.

**Status, stated precisely.**

- **No model is connected anywhere.** Provider selection is blocked on
  [FD-03](docs/decisions/FD-03-ai-provider-residency.md). `TALEEM_AI_PROVIDER` is unset in every
  environment, so the composition root wires **no generative tier at all**.
- A named provider gets `InertProviderGateway` (`ports/llm_inert.py`). It refuses to construct
  without a name, has no network transport, and refuses every call.
- The deterministic `StubLLMGateway` exists for tests and the evaluation harness. Production
  refuses to boot with it.

**Request path** (`application/ai_teacher_service.py`). On `:explain`, the templated response is
built exactly as before. A rephrase is then attempted only if every check passes, in this order:

1. **Feature flag** `ai_teacher.generative_rephrase` is on. It is off by default, and per-learner
   rollout is possible. With the flag off nothing else is consulted, and the response is
   byte-identical to the templated tier (tested).
2. **Kill switch** is disengaged.
3. **No escalation** is pending: after repeated failure the learner is handed to a human, not to a
   model.
4. **Live `ai_teaching` consent** exists, read from the identity context on every request.
5. **Per-learner quota** is not exhausted. Usage lives in the `learning.ai_usage_ledger` table on
   PostgreSQL, with counts and a pseudonymous ref only.
6. **Grounded prompt** (`domain/ai_teacher_gate.py`). It is built only from published `LessonView`
   fields, each with its field path. It never includes answer options, learner refs or learner
   state. If no grounding can be established, the model is not called.
7. **Safety gate** on the output. It checks grounding, answer leak, age band, disallowed content
   and locale. The rules are in [AI_TEACHER_SAFETY_MODEL.md](AI_TEACHER_SAFETY_MODEL.md) §9.

Every check fails closed. Any failure serves the authored response unchanged, with no error and no
weaker path. An accepted rephrase is returned only in a separate `generation` block, marked
`generated: true` and `verified: false`. It carries `grounded_on` provenance and a `notice_key` the
client must display. The verified `utterances` are never altered. There is still **no generation
offline**: the capability matrix reports `disabled_offline`, and the tier runs server-side only.

**What this does not establish.** The gate has been evaluated only against scripted stub outputs
([AI_TEACHER_EVALUATION.md](AI_TEACHER_EVALUATION.md) §8). It is lexical, and it has a known gap: a
misstatement built entirely from grounded words passes. Enabling the tier for children requires all
of the following:

- the FD-03 approvals;
- a real-model red-team;
- a semantic grounding check;
- independent safety review;
- transcript review.

None of these exist yet.
