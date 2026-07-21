# Learning Intelligence Platform — Architecture Review

Reviewer role: independent Principal Engineer + Learning Scientist (adversarial). Subject: the seven
Phase-4 design docs in this folder. Mandate (brief Part 8): **challenge every decision; if a better
design exists, replace it; do not preserve previous work for consistency.** Optimise for educational
quality, scalability, maintainability, simplicity, cost, safety.

Implementation may begin **only if this review passes**, and only within the Phase-1.5 governance
gate (nothing child-facing ships before those decisions).

A finding marked **REPLACED** means the design was changed as a result of this review (the change is
described and, where it affects a sibling doc, that doc was edited). **ACCEPTED** means the decision
survived scrutiny with rationale. Severity: **C**ritical / **H**igh / **M**edium / **L**ow.

---

## Findings

### F1 (H) — REPLACED: four "bounded contexts" was over-engineering for this phase

The domain model proposed four contexts (`knowledge`, `decision`, `session`, `analytics`). Challenged
against *simplicity*: `decision` is a pure library (not deployable), `analytics` is a downstream
warehouse (not an OLTP context), and splitting `knowledge` from `session` forces a distributed
interaction across an aggregate boundary on the hottest path (every turn). That is premature
distribution — it buys independent scaling we don't yet need and pays with cross-context complexity.

**Replacement:** a **single deployable `learning` bounded context** with internal modules
(`knowledge`, `decision` as a pure sub-package, `session`) sharing one schema and one Unit of Work,
plus analytics as a **downstream event consumer** (not a context of this service). `session` and
`knowledge` commit in the same UoW — no cross-aggregate distributed write per turn. If, at national
scale, session orchestration must scale separately from the knowledge store, the module seam allows
extraction later — but we do not pay for that now. LEARNING_DOMAIN_MODEL §1 updated accordingly.
*Status: resolved (simpler, still extensible).*

### F2 (C) — REPLACED: cold-start was undefined (a new learner had no mastery, no plan)

Every doc assumed a populated Student Model. But a brand-new KG child has **zero evidence** — the
Decision Engine as specified would either treat everything as `not_started` (teach grade-1 objective 1
to everyone, ignoring what they already know) or, worse, misread absence as non-mastery. For a
platform whose whole value is meeting a child where they are, this is a Critical gap.

**Replacement:** an explicit **placement/onboarding policy**. A new learner starts with
`mastery = prior(grade, objective)` at **high uncertainty** (not zero mastery), and the first
sessions run a **lightweight adaptive diagnostic** (retrieval over prerequisite objectives) that
rapidly narrows uncertainty before committing to a learning path. `MasteryState` distinguishes
"not_started (no evidence)" from a *diagnosed* estimate. The Decision Engine gains a
`Diagnose` decision for high-uncertainty objectives on the critical path. Added to
LEARNING_DECISION_ENGINE (a new decision + onboarding note) and STUDENT_MODEL (initial-estimate
policy). *Status: resolved — this was the most important gap the review found.*

### F3 (H) — ACCEPTED with guard: BKT is weaker than modern trackers

BKT ignores item difficulty and (classically) forgetting; deep knowledge tracing benchmarks higher.
Challenged: are we shipping a knowingly inferior estimator?

**Resolution:** yes, deliberately, and it is the right call. BKT + an explicit forgetting term is
**explainable to a mentor/parent** (a hard requirement), **cheap and offline-capable**, and works
with little data — while a DKT model is opaque, data-hungry, and unjustifiable to a parent asking
"why does it say my child hasn't mastered this?". The `MasteryEstimator` port means we can adopt
IRT/DKT **once our own data proves it beats the transparent baseline on retention outcomes** — never
on faith. The guard: LEARNING_ANALYTICS must actually run that comparison (a listed metric).
*Status: accepted (explainability > benchmark accuracy at this stage; upgrade path exists).*

### F4 (H) — ACCEPTED: internal probabilistic mastery vs simple presented state

A probability-with-uncertainty is right for *deciding* but confusing to *communicate* to low-literacy
parents. Risk: exposing "0.72 ± 0.1 mastery" to a parent is meaningless or alarming.

**Resolution:** the split already in the model is the answer, made explicit: the **internal**
representation is probabilistic (`Mastery{value,uncertainty}`); the **presented** metric is the
banded `MasteryState` (not_started → in_progress → mastered → needs_review) plus plain-language,
audio-first summaries (LEARNING_ANALYTICS §4). Parents never see raw probabilities. *Status: accepted
(clarified presentation boundary).*

### F5 (M) — ACCEPTED: the AI can't answer out-of-scope questions (by design)

The runtime refuses anything outside approved content and defers to a mentor. Challenged as a UX
weakness (a curious child asks "why is the sky blue?" and gets "ask your mentor").

**Resolution:** this is a **safety feature, not a bug**, and non-negotiable — an ungrounded generative
answer to a child is exactly the risk we must eliminate ("never invent curriculum"). The mitigation is
the **content-gap loop**: `ContentUncertaintyObserved` events cluster such questions and feed
Curriculum Studio's backlog, so genuinely valuable out-of-scope curiosity becomes *authored* content
over time. Short-term UX cost, long-term safety + curriculum growth. *Status: accepted (safety wins;
gap loop compensates).*

### F6 (M) — REPLACED: safeguarding on the outbox alone was too slow

Safety signals were listed among outbox events. A relay poll interval (seconds+) is unacceptable
latency for a distress/abuse signal.

**Replacement:** `SafeguardingSignalRaised` gets a **dedicated real-time delivery path** (synchronous
hand-off to the safeguarding pipeline at the moment of detection, *in addition* to a durable audit
record), and the AI Runtime's input-safety stage can **halt a turn before any teaching logic runs**.
Safety is not subject to eventual consistency. Reflected in AI_TEACHING_RUNTIME §7, SESSION_ENGINE §4,
and LEARNING_DOMAIN_MODEL §4. *Status: resolved.*

### F7 (M) — ACCEPTED: small/regional Urdu model may not exist yet

The layered AI architecture assumes a viable small/regional model tier. That may not be available for
Urdu-medium KG–10 today.

**Resolution:** the tiering **degrades gracefully** — tier 4a (templated, no-LLM) carries the majority
of turns regardless, and tier 4b is *optional*: if no adequate small model exists, adaptive rephrasing
falls through to a tightly-grounded frontier call (tier 4c) under the same scope/safety fences, or is
simply skipped (present authored content verbatim). The architecture doesn't *depend* on the small
tier; it *exploits* it when present. Cost/latency benefits when available, correctness never blocked.
*Status: accepted (graceful degradation designed in).*

### F8 (M) — ACCEPTED: "evidence de-identification" needs a precise definition before build

`AssessmentEvidence.response_summary` is "de-identified features, not raw text." That boundary must be
concrete before any child-facing code, or PII could leak into the learning store.

**Resolution:** made a **build precondition**: a data-classification spec (exactly which features are
stored, how free responses are reduced to non-PII signals, where raw text lives and its retention)
is required input to the Phase-1.5 DPIA and must be signed off before persistence is implemented.
STUDENT_MODEL §9 already forbids raw transcripts in the model; this finding elevates the precise spec
to a gating artifact. *Status: accepted (gated as a precondition, not hand-waved).*

### F9 (L) — ACCEPTED: determinism vs learner variety/monotony

A fully deterministic engine could feel repetitive. Challenged for engagement.

**Resolution:** variety is a **seeded, logged, explicit policy** (item-surface variation, ordering
within the same pedagogical choice), never hidden nondeterminism — so behavior stays reproducible and
testable while feeling fresh. Engagement analytics measures monotony/flow to tune it. *Status:
accepted.*

### F10 (L) — ACCEPTED: promotion decisions deliberately excluded from automation

No autonomous promotion/summative API exists. Confirmed intentional (doc 58 identity assurance;
mentor-confirmed). Recorded so a future phase doesn't "helpfully" add one. *Status: accepted.*

---

## Axis assessment

**Educational quality.** Every mechanism traces to a named, evidence-based principle
(LEARNING_SCIENCE_FRAMEWORK), composition and conflict-resolution are explicit, and the cold-start gap
(F2) — the one that would most have hurt real learners — is now closed. Mastery is evidence-derived
and explainable. **Pass.**

**Scalability.** Single context but **sharded by `student_ref`**; decision logic is pure/stateless;
analytics is event-sourced to a warehouse holding the student-scale data (kept out of the OLTP by
design). Per-turn writes are one local UoW, not a distributed transaction (F1). Scales to millions on
the same pattern already proven in Curriculum Studio. **Pass.**

**Maintainability.** The learning science lives behind three ports (`MasteryEstimator`,
`ForgettingModel`, `DecisionPolicy`) so pedagogy evolves without touching aggregates or callers —
the decade-longevity seam. Clean Architecture + DDD + Repository/UoW, consistent with the existing
codebase. **Pass.**

**Simplicity.** Improved by F1 (four contexts → one context + modules). The remaining complexity
(session saga, layered AI) is *essential* complexity justified by flaky connectivity and safety, not
accidental. **Pass.**

**Cost.** The layered AI runtime keeps the majority of turns on the free templated tier and reserves
frontier tokens for justified cases (F7 degradation keeps this robust); event-sourced analytics avoids
expensive OLTP scans. **Pass.**

**Safety.** Strongest axis by intent: grounding + output scope-check make hallucination unreachable by
a child; safeguarding is real-time (F6), not eventual; escalation and `Rest` are first-class decision
outcomes; child data is pseudonymous, minimized, crypto-shreddable, and its precise de-identification
spec is a build precondition (F8). **Pass.**

---

## Verdict

**PASS — cleared to implement, within the governance gate.**

One Critical finding (F2 cold-start) was found and **resolved by redesign**, not deferred — which is
exactly what this review existed to catch. Two decisions were **replaced** for the better (F1 context
collapse, F6 real-time safeguarding); the rest were accepted with rationale or elevated to gating
preconditions. No finding requires re-litigating the learning science; all sit behind swappable ports.

Conditions carried into implementation (acceptance criteria of the build):

1. **Governance gate first.** No child-facing runtime, no child-data persistence until Phase-1.5
   decisions (lawful basis, DPIA incl. the F8 de-identification spec, residency, safeguarding SLA)
   land. Until then, implementation is limited to the **pure, child-data-free core**: the
   `decision` policy library, the `MasteryEstimator`/`ForgettingModel` domain logic, the aggregates
   and state machines — all unit-testable to **≥95%** with synthetic states and **no** real child
   data. This is the governance-safe slice, mirroring how Phase 3 built Curriculum Studio.
2. **Cold-start/placement (F2)** is implemented as a first-class policy, with tests, before any
   "steady-state" path is considered done.
3. **Ports are real seams:** `MasteryEstimator`, `ForgettingModel`, `DecisionPolicy`,
   `TeachingRuntime`, and the repositories are interfaces with at least one fake + one real adapter;
   swapping the estimator must require no aggregate/caller change (asserted by a test).
4. **Determinism + explainability:** every `Decision` carries a `rationale`; the engine is
   deterministic given `(state, config, now)`; both are asserted in tests.
5. **Safety paths are tested as first-class:** input-safety halt, output scope-check fallback, and
   real-time safeguarding escalation each have explicit tests; no "optimal learning" branch can
   preempt them.
6. **Persistence design precedes persistence code:** a `learning/persistence/` design set
   (schema/ERD/events/review) is authored and reviewed **before** the SQLAlchemy layer, exactly as
   Phase 3 did — no schema by improvisation.
7. **Science is validated, not assumed:** LEARNING_ANALYTICS ships the metrics that test whether
   spacing reduces forgetting, remediation clears misconceptions, and any future estimator beats the
   transparent baseline — before those choices are trusted at scale.

Recommended first implementation slice (governance-safe, highest value, zero child data): the pure
**`decision` policy library + `MasteryEstimator`/`ForgettingModel`** with an exhaustive deterministic
test suite over synthetic learner states — the "brain" proven correct in isolation before any portal
or LLM is wired to it.
