# Learning Science Framework

Status: Design (Phase 4, pre-implementation). Governance: design only — no child-facing runtime is
built until the Phase-1.5 governance gate clears (see project memory + `docs/02-architecture`).
This document is the evidence base every other Phase-4 design doc cites. It grounds the Learning
Intelligence Platform in learning science rather than intuition, so that every automated decision
(what to teach, when to revise, how to explain, when to escalate) is defensible.

Context that shapes suitability throughout: Project Taleem serves KG–10 Pakistani children, many at
the bottom of the access curve — **low-end Android / 3G / intermittent-offline**, **Urdu-first**
with low household literacy, **mentor-mediated** (a human is in the loop for promotion-bearing
decisions), and **child-safety-first** (when quality and safety conflict, safety wins). These
constraints are not footnotes; they change which techniques dominate. A method that needs constant
high-bandwidth interaction or fluent-reader text loses points here even if its lab effect size is
large.

How to read the scores: **Suitability** is a 1–5 fit for *this* platform and population, not a
verdict on the science. **Evidence** summarizes the strength of the research base honestly, including
its limits — we do not overclaim effect sizes.

---

## 0. Summary map — which approach powers which component

| Approach | Primary owner component | What it decides/does |
| --- | --- | --- |
| Mastery Learning | Decision Engine + Student Model | Gate progression on prerequisite mastery; no advancing on sand |
| Spaced Repetition | Decision Engine (scheduler) + Student Model | *When* to resurface an objective for revision |
| Retrieval Practice | Session Engine + Decision Engine | Make revision an act of recall, not re-reading |
| Cognitive Load Theory | AI Teaching Runtime + Curriculum Studio authoring | *How* to present so working memory isn't overloaded |
| Formative Assessment | Session Engine + Analytics + mentor loop | Continuous low-stakes evidence → adjust next step |
| Worked Examples | AI Teaching Runtime + authoring | Teach new schemas via studied examples before problems |
| Deliberate Practice | Decision Engine (difficulty) | Keep practice at the edge of ability with tight feedback |
| Universal Design for Learning | Whole platform (cross-cutting) | Multiple means of representation/engagement/expression |

No single approach is sufficient; the platform is a **principled composition**. §9 defines how they
combine and how conflicts between them are resolved.

---

## 1. Mastery Learning

Idea (Bloom, 1968; "Learning for Mastery"): learning is held constant and *time* varies — a student
advances only after demonstrating mastery of prerequisites, with corrective feedback loops until
they do. Bloom's "2-sigma problem" (1984) framed one-to-one tutoring + mastery as the aspirational
ceiling; the platform's ambition is to approximate that tutor at scale.

- **Strengths.** Prevents accumulating gaps (the dominant failure mode in under-resourced systems).
  Aligns exactly with our prerequisite DAG (`docs/05-education/58-*`). Meta-analyses (Kulik, Kulik &
  Bangert-Drowns, 1990) report meaningful gains, strongest for lower-prior-attainment learners —
  precisely our population.
- **Weaknesses.** Pure mastery can **stall** a struggling student (endless corrective loops → demoralization) and can bore a fast one if thresholds are rigid. Time-variance complicates cohort
  scheduling. "Mastery" is only as good as the assessment that measures it (validity risk).
- **Suitability for Taleem: 5/5.** It is the backbone. The prerequisite DAG already exists; the
  bottom-of-curve population benefits most. The stall risk is real and is mitigated by a bounded
  corrective budget + mentor escalation (never trap a child in a loop).
- **Implementation proposal.** Mastery is a **per-objective state** in the Student Model (§2 of
  STUDENT_MODEL) with an explicit threshold. The Decision Engine refuses to select a lesson whose
  prerequisites are un-mastered and, after *N* failed corrective cycles, **escalates to a mentor**
  rather than looping forever. Mastery thresholds are evidence-based and per-objective, not a global
  magic number (LEARNING_DECISION_ENGINE §mastery thresholds).

## 2. Spaced Repetition

Idea (Ebbinghaus forgetting curve; Cepeda et al., 2006 meta-analysis of distributed practice):
memory decays predictably, and reviews spaced with expanding intervals dramatically improve
long-term retention versus massed study. Operationalized by Leitner boxes, SM-2 (Anki), and modern
FSRS.

- **Strengths.** Large, robust long-term-retention effect; cheap to schedule; **works offline** (the
  next-due date can be computed on-device and synced later). Directly attacks the real problem:
  children forget last month's material.
- **Weaknesses.** Scheduling optimally needs a memory model per item; naive fixed intervals are
  suboptimal. Can generate a "review debt" backlog that overwhelms if unmanaged. Interacts with
  curriculum pacing (a spaced review may collide with new teaching).
- **Suitability for Taleem: 5/5.** The offline-friendliness is decisive — a schedule computed once
  and cached lets a child revise on a 3G/no-G day. Backlog risk is managed by capping daily reviews
  and prioritizing high-value/at-risk objectives.
- **Implementation proposal.** A **scheduler** in the Decision Engine assigns each mastered objective
  a `next_review_at` using a transparent, tunable algorithm. **We start with a half-life / Leitner-
  style model (explainable, cheap), designed behind an interface so it can be upgraded to a FSRS-
  style model** once we have interaction data — without changing callers. Per-student memory
  strength lives in the Student Model. Reviews are capped per day and prioritized (§9 conflict rules).

## 3. Retrieval Practice (the testing effect)

Idea (Roediger & Karpicke, 2006; Adesope et al., 2017 meta-analysis): *retrieving* information
strengthens memory far more than re-studying it. Low-stakes quizzing is one of the highest-leverage,
best-evidenced techniques in the literature.

- **Strengths.** Strong, well-replicated effect; doubles as **formative evidence** (every retrieval
  is a data point for the Student Model); pairs naturally with spacing ("spaced retrieval").
- **Weaknesses.** Can induce anxiety if framed as high-stakes (mitigated by low-stakes framing);
  poorly written items measure recall of trivia, not understanding (validity risk); needs a bank of
  quality items (supplied by Curriculum Studio's assessment objects).
- **Suitability for Taleem: 5/5.** Converts revision from passive re-reading (useless on a tiny
  screen) into active recall, and yields the evidence the whole platform runs on. Low-stakes framing
  fits the mentor-mediated, non-punitive ethos.
- **Implementation proposal.** Revision sessions are **retrieval-first**: the Session Engine presents
  a recall attempt before any re-explanation. Each attempt updates mastery + memory strength.
  Spacing (§2) schedules *when*; retrieval defines *what happens* at that time. Summative,
  promotion-bearing retrieval remains human-identity-assured (doc 58) — automation handles formative
  retrieval only.

## 4. Cognitive Load Theory (CLT)

Idea (Sweller): working memory is severely limited; instruction should minimize **extraneous** load
(caused by poor presentation), manage **intrinsic** load (task complexity), and free capacity for
**germane** processing (schema building). Yields the worked-example, split-attention, redundancy,
modality, and expertise-reversal effects.

- **Strengths.** Directly actionable design rules with strong evidence; especially protective for
  novices, low-literacy learners, and small screens — our exact context.
- **Weaknesses.** Some load constructs are hard to measure precisely; rules are guidelines requiring
  judgement; the expertise-reversal effect means what helps a novice can hinder an expert (so load
  management must adapt to mastery).
- **Suitability for Taleem: 5/5.** On a low-end phone in a second language, extraneous load is the
  silent killer. CLT is less a "feature" than a **constraint on everything** the AI Runtime and
  authoring produce.
- **Implementation proposal.** CLT is encoded as **authoring constraints** (Curriculum Studio: short
  sentences, one idea per step, audio+visual not redundant text, worked examples) *and* as **runtime
  rules** (the AI Runtime presents one step at a time, avoids wall-of-text, uses the modality
  effect: narrate audio while showing a diagram rather than making the child read + look). Load
  adapts to mastery (fade support as competence grows — §6). Readability/PERFORMANCE quality gates
  already enforce parts of this.

## 5. Formative Assessment

Idea (Black & Wiliam, 1998, "Inside the Black Box"): frequent, low-stakes assessment *for* learning
— eliciting evidence and acting on it — produces some of the largest gains in education when the
feedback loop is tight and actionable.

- **Strengths.** Large effect when feedback drives the *next* action (which is exactly what a
  decision engine does); non-punitive; generates the data the platform needs.
- **Weaknesses.** Only works if the loop closes (evidence → adjusted instruction); feedback quality
  matters more than quantity; can degrade into "mini-summative" testing if mis-framed.
- **Suitability for Taleem: 5/5.** It is the connective tissue between the AI Runtime (elicits
  evidence), the Student Model (records it), the Decision Engine (acts on it), and the mentor (reviews
  it). The mentor loop makes the human feedback channel first-class.
- **Implementation proposal.** Every interaction emits **formative evidence** (correct/incorrect,
  hint usage, response time, misconception signals). The Decision Engine consumes it immediately
  (adapt difficulty, choose next). The mentor dashboard surfaces it for human feedback. Feedback to
  the child is **specific and forward-looking** ("try counting again from the last apple"), never
  just "wrong" (authored hint ladders enforce this).

## 6. Worked Examples

Idea (Sweller & Cooper, 1985): for novices acquiring a new schema, studying a fully worked example
is more effective and efficient than solving an equivalent problem (the worked-example effect).
Support should **fade** as competence grows (completion problems → independent problems), respecting
the **expertise-reversal effect**.

- **Strengths.** Efficient schema acquisition for novices; reduces the flailing that pure
  problem-solving causes in beginners; pairs with CLT.
- **Weaknesses.** Over-used past the novice stage it *harms* (expertise reversal) — so it must fade;
  passive study without self-explanation is weaker (pair with prompts).
- **Suitability for Taleem: 4/5.** Excellent for introducing KG–10 concepts to novices with low
  reading load (a narrated, step-by-step visual example). Slightly lower than 5 only because its
  benefit is stage-specific and must be actively faded, adding adaptation complexity.
- **Implementation proposal.** Curriculum Studio already authors `worked_examples`. The AI Runtime
  presents them **first** for a new objective, prompts **self-explanation** ("why did we carry the
  1?"), then **fades**: worked example → completion problem (some steps blanked) → full problem, with
  the fade point driven by the Student Model's mastery signal (§decision engine difficulty).

## 7. Deliberate Practice

Idea (Ericsson): expertise grows through focused, effortful practice at the **edge of current
ability**, with immediate feedback and repetition targeting specific weaknesses — not mere
repetition of what's already easy.

- **Strengths.** Focuses effort where it pays; the "edge of ability" principle is the basis for
  difficulty adaptation; immediate feedback aligns with formative assessment.
- **Weaknesses.** The strong "10,000 hours" popularization overstates it; Macnamara et al. (2014)
  show practice explains a variable, domain-dependent share of performance — it is necessary, not
  sufficient. Effortful practice risks demotivation if the difficulty band is mis-set.
- **Suitability for Taleem: 4/5.** The *principle* (target weaknesses at the right difficulty with
  tight feedback) is directly implementable and valuable; we adopt the mechanism, not the mythology.
  Motivation risk in a young population caps it below 5.
- **Implementation proposal.** The Decision Engine maintains a **difficulty target** per student ×
  objective aiming for a success band (§8) that is challenging-but-attainable (a "desirable
  difficulty," Bjork). Practice items are selected to hit **known weaknesses/misconceptions** (from
  the Student Model), not random review. Effort is bounded and encouraged, never punitive.

## 8. Universal Design for Learning (UDL)

Idea (CAST): design for learner variability from the start via multiple means of **engagement**
(the "why"), **representation** (the "what"), and **action & expression** (the "how"), rather than
retrofitting accommodations.

- **Strengths.** Inclusive by construction; maps precisely to our non-negotiables (Urdu-first, audio,
  WCAG 2.2 AA, low-literacy households, diverse devices). Reduces the need for separate "special"
  paths.
- **Weaknesses.** Broad principle, not a prescriptive algorithm; evidence is more about design
  quality than a single effect size; can be diluted into a checklist if not taken seriously.
- **Suitability for Taleem: 5/5.** For a population defined by variability and constraint, UDL is a
  first-order requirement, not an enhancement. It is why the Runtime is audio-first and why every
  representation has an alternative.
- **Implementation proposal.** UDL is **cross-cutting**: multiple representation (audio narration +
  visual + minimal text, authored as `LocalizedText` with mandatory Urdu audio); multiple expression
  (tap, voice, draw, choose — not only typing); multiple engagement (relevance, appropriate
  challenge via §7, encouragement). The accessibility quality gate enforces the representation floor;
  the Runtime chooses among available representations per student preference/ability.

---

## 9. Composition — how the approaches combine, and how conflicts resolve

The platform is not eight features bolted together; it is one loop where each approach plays a role:

1. **Mastery Learning** sets the *macro path* (what's eligible to learn/revise, gated on the DAG).
2. **Spaced Repetition** decides *when* mastered material returns for review.
3. **Retrieval Practice + Formative Assessment** define *what happens in a session* — recall attempts
   that both teach and generate evidence.
4. **CLT + Worked Examples + UDL** govern *how content is presented* so it's learnable on a cheap
   phone in Urdu.
5. **Deliberate Practice** *tunes difficulty* to the edge of ability using the evidence.

Conflicts are inevitable; the framework resolves them by explicit priority, encoded in the Decision
Engine and re-stated in its doc:

- **Child safety / wellbeing > learning gain.** A frustrated or distressed child triggers
  de-escalation or mentor handoff even if the "optimal" next item is harder. Always.
- **Prerequisite integrity > coverage speed.** Never advance past an un-mastered prerequisite to
  "keep up" — Mastery wins over pace.
- **Spaced review vs new learning (time budget).** When both compete for a session, **at-risk reviews
  (about to be forgotten, high-value) are prioritized over new material**, but a hard daily review
  cap prevents review debt from blocking all progress; overflow rolls forward and, if chronic,
  surfaces to a mentor.
- **Worked-example support vs deliberate-practice challenge.** Governed by mastery: novices get
  support (worked examples, lower difficulty); as mastery rises, support fades and challenge
  increases (expertise reversal respected).
- **Retrieval difficulty vs motivation.** Aim for "desirable difficulty" (a target success band,
  §decision engine), not maximum difficulty — effortful but attainable, because a demotivated child
  learns nothing.

These priorities are **testable rules**, not vibes: each becomes a policy in
LEARNING_DECISION_ENGINE with acceptance criteria, and each is measured for effectiveness in
LEARNING_ANALYTICS (e.g., is prioritizing at-risk reviews actually improving retention?).

---

## 10. Evidence honesty and evaluation

We commit to not overclaiming. Effect sizes in education are context-dependent and often smaller in
the field than in the lab. Therefore:

- Every technique above ships behind a **policy interface** with tunable parameters, so we can adjust
  intervals, thresholds, and difficulty bands from *our* data rather than assuming lab values
  transfer to Urdu-medium KG–10 learners on 3G.
- LEARNING_ANALYTICS defines the metrics that will **validate or refute** each choice (e.g.,
  revision-effectiveness measures whether our spacing schedule actually reduces forgetting; a
  misconception-clearance metric measures whether adaptive remediation works).
- Where evidence is strong and stable (retrieval practice, spacing, worked-example effect for
  novices, CLT presentation rules), we implement confidently. Where it is principle-level (UDL) or
  contested in magnitude (deliberate practice, the 2-sigma target), we implement the mechanism and
  **let measurement decide** how far to push it.

This framework is the standard the rest of Phase 4 is held to: if a design decision in any later doc
cannot point back to a principle here (or to a safety/constraint requirement), it does not ship.
