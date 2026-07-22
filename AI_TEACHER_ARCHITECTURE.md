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
  generative tiers (small/frontier model behind the `LLMGateway` port) are a *future* rephrasing layer
  that never sources curriculum; they are **off for children** and **off offline**.
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

## 5. Where the generative tiers fit (future, gated)

The Master AI strategy is *Curriculum → Retrieval → small model → safety → frontier LLM*. The AI
Teacher implements the **curriculum + templated** floor. A generative tier would plug in behind the
existing `LLMGateway` port to **rephrase** a teacher utterance for a struggling learner — **never to
source curriculum**, **never for children in the pilot**, and **never offline** (AR-C-06). It would sit
*after* the guardrail (grounded content in) and *before* delivery (safety-checked rephrase out), and is
out of scope for Phase 8. The templated tier is the safe, sufficient, explainable teacher for the pilot.
