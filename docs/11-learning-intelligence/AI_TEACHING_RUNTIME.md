# AI Teaching Runtime

Status: Design (Phase 4, pre-implementation). Governance: **highest-risk component** — it is the
only part that talks to a child with a generative model. Its child-facing implementation is gated on
Phase-1.5 safety decisions (independent safety review, mandatory-reporting policy, safeguarding SLA).
This document specifies the runtime so those gates review a concrete, safe-by-construction design.

The runtime executes a **`Teach`/`Review`/`Remediate` decision** from the
[LEARNING_DECISION_ENGINE.md](LEARNING_DECISION_ENGINE.md) as an actual tutoring interaction, using
the **approved lesson** and its **authored AI teaching object** from Curriculum Studio. Its guiding
law: **the AI is an assistant, not an authority. It teaches from approved content, stays in scope,
and never invents curriculum** (Master Overview / AI Strategy).

---

## 1. What the runtime is (and is not)

- **Is:** a controlled orchestrator that turns approved lesson content + an authored teaching
  strategy into a safe, adaptive, Urdu-first conversation — choosing prompts, rephrasing within
  scope, detecting confusion, giving graduated hints, and escalating to a human when it should.
- **Is not:** an open-ended chatbot, a knowledge source, or an autonomous decision-maker. It cannot
  introduce facts, opinions, or content that were not authored and approved. It cannot decide
  mastery, promotion, or safety outcomes on its own.

Every generated utterance is **grounded in and constrained by** the authored lesson: the
`teacher_script`, `student_explanation`, `worked_examples`, `hints`, `common_misconceptions`, and the
`AITeachingObject` (`teaching_strategy`, `questioning_strategy`, `hint_policy`, `escalation_rules`,
`forbidden_behaviours`, `misconception_detectors`). The model **rephrases and sequences approved
content**; it does not originate curriculum.

---

## 2. The layered AI architecture (defense-in-depth, cost-aware)

Per the Master Overview AI Strategy — *Curriculum → Retrieval → small regional model (where
appropriate) → Safety layer → Frontier LLM only when justified by policy* — the runtime is a
pipeline of escalating capability, where **most turns never reach a frontier model**:

```text
            ┌─────────────────────────────────────────────────────────────┐
Student turn│                                                             │
   ─────────▶ 1. INPUT SAFETY  ─▶  2. GROUND (Curriculum + Retrieval)      │
            │        │                     │                              │
            │   (block/redact/           scope-bounded approved content    │
            │    escalate)                     │                          │
            │                          3. PLAN (authored teaching strategy)│
            │                                  │                          │
            │             ┌────────────────────┴───────────────┐          │
            │        4a. TEMPLATED           4b. SMALL MODEL    4c. FRONTIER│
            │        (no LLM: scripted       (regional/small    (only when │
            │         next step, hint,        LLM: rephrase,     policy    │
            │         MCQ, worked step)       simplify, adapt)   justifies)│
            │                          │                          │        │
            │                          5. OUTPUT SAFETY + SCOPE CHECK       │
            │                                  │                          │
            └──────────────────────────────────▼──────────────────────────┘
                                        Utterance to child
```

- **Tier 4a — Templated / no-LLM (the majority of turns).** Presenting the next authored step, a
  worked-example step, an MCQ, the next hint in the ladder, or an authored explanation needs **no
  generation at all** — it is deterministic sequencing of approved content. Cheapest, safest, fully
  offline-capable, perfectly in-scope. The runtime prefers this tier whenever it suffices.
- **Tier 4b — Small/regional model.** When adaptation is needed (rephrase an explanation more simply,
  translate register to a struggling reader, generate encouragement, vary an example's surface
  story), a **small, cheaper, possibly on-region model** does it — constrained to rephrasing supplied
  approved content, never to sourcing new facts.
- **Tier 4c — Frontier LLM.** Only when a turn genuinely requires stronger reasoning (e.g., diagnosing
  an unusual misconception from a free response) **and policy permits**, and always fenced by the
  same grounding + safety layers. Frontier use is logged, budgeted, and justified per policy — it is
  the exception.

This layering is simultaneously a **cost** control (frontier tokens are rare), a **latency/offline**
control (templated tiers work on-device), and a **safety** control (less generative freedom = less
risk). Each tier is a swappable adapter behind an `LLMGateway` port (the platform already has this
port from M1).

---

## 3. Grounding — scope enforcement (the anti-hallucination core)

The single most important guarantee: **the AI cannot leave the lesson's scope.**

- **Retrieval is restricted to the approved lesson (and its objective's approved neighborhood).** The
  runtime assembles context *only* from the current published lesson's fields + tightly-scoped
  related approved content (e.g., the prerequisite's summary). It does **not** retrieve from the open
  web or unapproved material. (This mirrors Curriculum Studio's provenance gate: approved,
  original content only.)
- **Prompts are constructed, not free.** For tiers 4b/4c the system prompt hard-codes: the objective,
  the authored teaching strategy, the allowed content, the `forbidden_behaviours`, and an explicit
  instruction that the model may only rephrase/sequence the provided content and must respond
  "let's ask your mentor" when asked something out of scope. The child's input is data, never
  instruction (prompt-injection resistant).
- **Output scope check (step 5).** Every generated utterance is checked back against scope before it
  reaches the child: a classifier/rules pass verifies it does not introduce unapproved facts, does not
  violate `forbidden_behaviours`, and stays on the objective. On failure → fall back to templated
  approved content (tier 4a) and log the incident. The child **never** sees an ungrounded generation.

Result: even if a model tried to hallucinate, the grounding restriction + output scope check + fall-
back-to-approved-content mean an ungrounded claim cannot reach a child. Scope is enforced by
construction, not by trusting the model.

---

## 4. The teaching loop (one interaction)

For a single decision (`Teach`/`Review`/`Remediate`), the runtime runs a bounded loop:

1. **Present** — deliver the next authored step per the teaching strategy (worked example first for a
   new objective; retrieval prompt first for a review). Audio-first, Urdu-first, one idea per step
   (CLT). Tier 4a by default.
2. **Elicit** — ask an authored/strategy-driven question (the `questioning_strategy`), or present an
   assessment item. Multiple means of expression (tap/voice/choose/draw — UDL).
3. **Interpret** — score the response; run the authored `misconception_detectors`; measure
   uncertainty (§5). This produces **formative evidence** for the Student Model.
4. **Respond** — choose per Decision-Engine policy:
   - correct + confident → affirm, advance;
   - correct + low confidence → affirm + brief consolidation (calibration);
   - incorrect → next graduated **hint** (not the answer), or targeted misconception correction;
   - stuck after hint cap → **re-explain** via alternative representation, or **escalate**.
5. **Loop or exit** — continue until the step's goal is met, the effort budget is reached, or an exit
   condition fires (mastery signal, Rest, or escalation).

The loop is **bounded** (max turns/hints/time per step) so a child is never trapped; exhaustion is an
exit to re-explanation, difficulty step-down, or mentor — decided by the engine, executed here.

---

## 5. Uncertainty detection

The runtime detects two kinds of uncertainty and treats them differently:

- **Learner uncertainty** — the child is confused/struggling. Signals: wrong answers, long hesitation,
  repeated hints, self-reported low confidence, misconception-detector hits, help-seeking language.
  Response: more scaffolding, alternative representation, or escalation (never push harder into
  confusion). Persistent learner distress → **safety escalation**, not just pedagogical adjustment.
- **Model uncertainty** — the runtime/model is not confident it can respond *within scope and
  correctly*. Signals: low retrieval relevance (the question isn't covered by approved content),
  out-of-scope classification, low model confidence, safety-classifier ambiguity. Response: **do not
  guess.** Fall back to approved content, say "that's a great question for your mentor," and/or
  `EscalateToMentor`. Model uncertainty must never be resolved by inventing an answer — this is the
  hard line that keeps a well-meaning hallucination from reaching a child.

Both feed the Student Model (learner uncertainty) and the ops/quality metrics (model uncertainty →
content-gap signal for Curriculum Studio: "children keep asking X and it isn't authored").

---

## 6. Hints and explanations (executing engine policy within authored bounds)

- Hints are the **authored ladder**, delivered least-to-most, capped per the `hint_policy`. The
  runtime executes the count/cap the Decision Engine set; it does not invent new hints beyond the
  ladder (it may *rephrase* an authored hint more simply via tier 4b).
- Explanations are **authored** (`student_explanation`, `worked_examples`, misconception corrections);
  the runtime may rephrase/switch modality within scope. When approved explanations are exhausted and
  the child is still stuck, it escalates — it does not manufacture a new explanation.
- Everything respects CLT + UDL at delivery: short, audio-first, one step at a time, alternative
  representations available.

## 7. Escalation (child safety first)

Escalation is a **first-class runtime output**, and safety escalation is **immediate and
non-negotiable**:

- **Safety/wellbeing escalation** — any signal of distress, harm, abuse disclosure, or crisis routes
  to the **safeguarding pipeline immediately** (per the authored `escalation_rules` + the platform
  crisis protocol/doc 53), pausing teaching. This is not a pedagogical decision and is never
  overridden by learning goals. The runtime is designed so a safety signal short-circuits everything
  else in the pipeline (step 1 input safety can halt a turn before any teaching logic runs).
- **Pedagogical escalation** — persistent inability to progress despite hints/re-explanation → hand
  off to a **mentor** with the evidence trail, so a human helps.
- **Scope/uncertainty escalation** — repeated out-of-scope questions or model uncertainty → defer to
  mentor and flag a possible content gap.

The authored `forbidden_behaviours` (e.g., "give the answer," "claim to be human," "discuss X") and
`escalation_rules` are **enforced at runtime**, not merely advisory — output that would violate them
is blocked by the safety/scope layers.

## 8. Safety layers (input and output)

- **Input safety (step 1):** classify the child's message for distress/safety concerns and
  prompt-injection before it influences any teaching logic; block/redact/escalate as policy dictates.
- **Output safety (step 5):** every utterance passes age-appropriateness, `forbidden_behaviours`,
  and scope checks before delivery; failures fall back to approved templated content and are logged.
- **Non-persistence of raw sensitive content:** raw session text is handled under the safety
  pipeline's retention, and only **de-identified** learning features flow to the Student Model
  (STUDENT_MODEL §9). The learning brain does not archive children's raw disclosures.
- **Full auditability:** every turn logs which tier handled it, what content grounded it, what safety
  checks ran, and the outcome — so any interaction can be reconstructed and reviewed (child-safety +
  Master Overview audit requirements).

---

## 9. Offline and low-resource operation

- Tier 4a (templated approved content) runs **fully offline** from a cached lesson package
  (Curriculum Studio's `offline_package`), so a child on a no-connectivity day still gets a real,
  in-scope lesson and formative practice; evidence is queued and synced later.
- Tiers 4b/4c require connectivity (or an on-device small model where feasible) and degrade
  gracefully: offline, the runtime stays on tier 4a and defers adaptive rephrasing until online.
- Audio-first delivery suits low-literacy households and small screens; assets are pre-bundled for
  low bandwidth.

---

## 10. Ports and testability

- The runtime depends on ports, not implementations: `LLMGateway` (tiered), `SafetyClassifier`,
  `ContentRetriever` (scope-restricted), `EscalationChannel`, `Clock`, and the `StudentModel`
  repository. Each is injected, so the runtime is testable with fakes and the models are swappable.
- **Deterministic control logic is separated from generative content.** The loop, tier selection,
  scope checks, hint/escalation control flow are pure/testable to high coverage; only the actual
  rephrasing calls out to a model. This lets us prove the *safety and scope guarantees* in tests
  without a live LLM — the guarantees are in the deterministic layers, exactly where they belong.

Domain types for the runtime (session turn, teaching plan, escalation event) are in
[LEARNING_DOMAIN_MODEL.md](LEARNING_DOMAIN_MODEL.md); the runtime is driven by the
[SESSION_ENGINE.md](SESSION_ENGINE.md).
