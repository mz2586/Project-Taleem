# Learning Intelligence Platform (Phase 4 — Design)

The educational brain of Project Taleem: it decides what a student learns, when they revise, how
mastery is measured, how misconceptions are detected, how explanations adapt, when a mentor is
involved, and what happens next — all evidence-based, explainable, and child-safe.

Status: **design complete, review passed, pre-implementation.** Implementation begins only within the
Phase-1.5 governance gate and starts with the pure, child-data-free core (see the review's conditions).

## Documents (read in order)

1. [LEARNING_SCIENCE_FRAMEWORK.md](LEARNING_SCIENCE_FRAMEWORK.md) — the evidence base (8 approaches
   compared) that everything else is held to.
2. [STUDENT_MODEL.md](STUDENT_MODEL.md) — the Student Knowledge Model (mastery, misconceptions,
   confidence, pace, evidence).
3. [LEARNING_DECISION_ENGINE.md](LEARNING_DECISION_ENGINE.md) — the pure policy layer that decides
   what happens next.
4. [AI_TEACHING_RUNTIME.md](AI_TEACHING_RUNTIME.md) — the layered, scope-bounded runtime that teaches
   from approved content only.
5. [SESSION_ENGINE.md](SESSION_ENGINE.md) — the crash-safe, resumable, offline-capable session saga.
6. [LEARNING_ANALYTICS.md](LEARNING_ANALYTICS.md) — what we measure and how we validate the pedagogy.
7. [LEARNING_DOMAIN_MODEL.md](LEARNING_DOMAIN_MODEL.md) — aggregates, entities, value objects, events,
   repositories, APIs.
8. [LEARNING_PLATFORM_DESIGN_REVIEW.md](LEARNING_PLATFORM_DESIGN_REVIEW.md) — adversarial review;
   verdict + the conditions gating implementation.

## Key design commitments

- **Explainable & measurable** — every mastery number traces to evidence; every decision carries a
  rationale. The learning science lives behind swappable ports (`MasteryEstimator`, `ForgettingModel`,
  `DecisionPolicy`) so pedagogy evolves without redesign.
- **Safety first, by construction** — the AI teaches only approved content (hallucination is
  unreachable by a child); safeguarding escalation is real-time; child data is pseudonymous,
  minimized, and crypto-shreddable.
- **Built for the bottom of the curve** — offline-capable, audio-/Urdu-first, low-end-device aware;
  scales to millions via shard-by-`student_ref` and event-sourced analytics.
