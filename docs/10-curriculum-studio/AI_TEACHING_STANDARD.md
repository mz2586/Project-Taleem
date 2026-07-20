# AI Teaching Standard

| | |
|---|---|
| **Status** | Phase 3 · The structured AI instructions every lesson carries · Related: [24 AI Teacher](../05-education/24-ai-teacher-specification.md) · [15 Child Safety](../03-security-privacy/15-child-safety-framework.md) |
| **Date** | 2026-07-20 |

## 1. Why AI teaching objects

The AI Teacher must not improvise pedagogy. Each lesson ships a **structured AI Teaching Object** that
tells the AI *how to teach this specific lesson* — grounded, safe, and consistent. This makes the AI a
delivery mechanism for **authored, human-reviewed pedagogy**, not an open-ended chatbot.

## 2. AI Teaching Object schema (all fields required)

| Field | Purpose |
|---|---|
| `learning_goals` | The SLOs this interaction advances (bounds the AI to the lesson). |
| `teaching_strategy` | The pedagogical approach (e.g. concrete→pictorial→abstract; worked-example-first). |
| `questioning_strategy` | The Socratic sequence — what to ask, in what order, to build understanding. |
| `slow_down_signals` | Observations that mean "slow down / re-explain" (repeated errors, confusion, distress-adjacent). |
| `hint_policy` | When and how to hint — **graduated**, never the answer first; max hints before escalating. |
| `example_policy` | When to offer another worked example vs. more practice. |
| `misconception_detectors` | Patterns in a child's answers that reveal each named misconception + the targeted correction. |
| `critical_thinking_prompts` | Prompts that push reasoning ("why do you think…?"), age-appropriate. |
| `personalization_rules` | How to adapt tone/pace/examples to the child (culturally grounded, never stereotyping). |
| `escalation_rules` | When to hand off to a human Mentor (distress, safeguarding, repeated failure) — [15 §5](../03-security-privacy/15-child-safety-framework.md). |
| `forbidden_behaviours` | What the AI must never do in this lesson (give the answer, go off-syllabus, claim to be human, discuss unsafe topics). |
| `confidence_thresholds` | Minimum groundedness/confidence to answer; below it the AI says "I don't know / let's ask your Mentor". |

## 3. Binding safety rules (inherited, non-overridable)

Every AI Teaching Object operates **within** the platform's safety contract ([24 §2](../05-education/24-ai-teacher-specification.md),
[15](../03-security-privacy/15-child-safety-framework.md)) — the lesson-level object may *tighten* but
never *loosen* these:

- Grounded in this lesson's content (RAG); off-syllabus is redirected.
- Two-sided guardrails; nothing un-moderated reaches a child.
- **Distress → deterministic clinician-reviewed holding response + human escalation within SLA** (never
  model-generated crisis text).
- Honesty over hallucination; always labelled "AI Teacher"; never implies human.
- **No generative AI offline** — offline serves only pre-moderated cached hints from this object.

## 4. Authoring rules for AI Teaching Objects

- **Written/curated by a curriculum author, reviewed by the AI-safety gate** — not auto-generated without
  human sign-off ([QUALITY_ASSURANCE_STANDARD](./QUALITY_ASSURANCE_STANDARD.md)).
- `forbidden_behaviours` and `escalation_rules` are **mandatory and non-empty**.
- `misconception_detectors` must cover every misconception in the lesson's `common_misconceptions`.
- `hint_policy` must be graduated and cap hints before escalation.
- Urdu + English tone guidance; culturally grounded personalization; no gender/religion stereotyping.

## 5. Validation (machine-checked)

The Studio validator + AI-safety gate reject an AI Teaching Object that:

- is missing any required field, or has empty `forbidden_behaviours`/`escalation_rules`;
- has misconception detectors that don't cover the lesson's misconceptions;
- attempts to loosen an inherited safety rule;
- has a `hint_policy` that reveals the answer first or lacks an escalation cap.

## 6. Runtime contract

At runtime the AI Teacher loads this object as the authoritative instruction set for the lesson, bounded
by the global safety pipeline. Every turn is transcript-logged; the AI red-team eval set includes these
objects ([24 §10](../05-education/24-ai-teacher-specification.md)).

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-20 | AI teaching standard: 12-field object schema, inherited non-overridable safety rules, authoring + validation rules. | Curriculum Studio |
