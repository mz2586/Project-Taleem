# Student Knowledge Model

Status: Design (Phase 4, pre-implementation). Governance: design only; no child data is stored until
the Phase-1.5 gate clears. Grounded in [LEARNING_SCIENCE_FRAMEWORK.md](LEARNING_SCIENCE_FRAMEWORK.md).
This is the platform's memory of *one learner*: what they know, what they get wrong, how confident
they are, how fast they move, and the evidence behind every claim. Every decision the platform makes
(LEARNING_DECISION_ENGINE) reads from this model; every session (SESSION_ENGINE) writes to it.

Design stance: the model is **evidence-based and explainable**. Any mastery number can be traced to
the assessment evidence that produced it (Master Overview: "Educational decisions should be
explainable and measurable"). We do not use an opaque black-box estimate we cannot justify to a
mentor or a parent.

---

## 1. What the model must represent (from the brief)

Per learner, at the **learning-objective (SLO) granularity**:

- **Mastery** — a calibrated estimate of how well the objective is held, with uncertainty.
- **Strengths** — objectives/skills reliably demonstrated.
- **Misconceptions** — specific wrong mental models detected, with clearance state.
- **Revision history** — what was reviewed, when, with what result (drives spacing).
- **Confidence** — the learner's *self-reported* confidence, tracked separately from measured mastery
  (the gap between them is itself a signal).
- **Learning pace** — how quickly this learner reaches mastery / how much practice they need.
- **Assessment evidence** — the immutable trail of attempts that every estimate is derived from.

The unit of mastery is the **SLO** (the `curriculum_objective` from Curriculum Studio), because that
is the grain the curriculum, the prerequisite DAG, and assessments already use. Coarser (subject-
level) hides gaps; finer (per-item) is noise. SLO is the right, curriculum-aligned granularity.

---

## 2. Core representation — the Objective Mastery record

The heart of the model is one record per `(student, objective)`:

| Field | Type | Meaning / source |
| --- | --- | --- |
| `student_ref` | opaque id | The learner (pseudonymous; see §9 privacy). |
| `objective_code` | SLO code | The `curriculum_objective` this tracks. |
| `mastery` | 0.0–1.0 | Calibrated probability the learner has mastered the objective. |
| `mastery_uncertainty` | 0.0–1.0 | How sure we are of `mastery` (wide early, narrows with evidence). |
| `state` | enum | `not_started · in_progress · mastered · needs_review · at_risk` (derived, §4). |
| `memory_strength` | float | Retention parameter (a "stability"/half-life) driving spacing (§5). |
| `next_review_at` | timestamp | When this objective is next due for spaced retrieval. |
| `last_seen_at` | timestamp | Last interaction (for decay computation). |
| `attempts` | int | Count of assessment attempts (evidence volume). |
| `correct_streak` | int | Consecutive correct retrievals (a mastery signal). |
| `self_confidence` | 0.0–1.0 | Learner's self-report (§6), stored separately from `mastery`. |
| `pace_factor` | float | This learner's practice-to-mastery ratio vs cohort (§7). |
| `active_misconceptions` | list | Open misconceptions on this objective (§3). |
| `updated_at`, `version` | — | Optimistic-lock + audit bookkeeping. |

`mastery` is a **probability with uncertainty**, not a point score, because "you got 3/4 right" is
not the same as "you have mastered this" — the estimate must express how much evidence backs it.
This is what lets the Decision Engine avoid declaring mastery on one lucky attempt (§4).

### Initial estimate / cold-start policy (design-review F2)

A new learner has no evidence, so we **must not** default every objective to `mastery = 0`
(that would mis-teach a child who already knows the material). Instead:

- Each objective is initialized to `mastery = prior(grade, objective)` — a weak grade-appropriate
  prior — at **high `mastery_uncertainty`**. `state` is `not_started` (no evidence) but the estimate
  is a *hypothesis to test*, not a claim.
- The Decision Engine resolves this uncertainty with `Diagnose` decisions (a short adaptive
  diagnostic) before committing to a learning path, so the learner is placed **where they actually
  are** in the DAG. High uncertainty → diagnose; low uncertainty → teach/review.
- Uncertainty is what drives this: the model's job at onboarding is to **narrow uncertainty
  quickly** with minimal, low-stakes retrieval, not to assert mastery prematurely.

### Why a Bayesian estimate (and which one)

We evaluated three families for `mastery`:

1. **Simple running score** (e.g., % correct, or a points threshold). Transparent but no uncertainty,
   no decay, easily gamed by a lucky guess or punished by one slip.
2. **Bayesian Knowledge Tracing (BKT)** — a 2-state HMM per skill (`learned` probability updated by
   correct/incorrect with slip/guess parameters). Decades of use in ITS (Cognitive Tutor), highly
   explainable, cheap, gives a probability. Weakness: classic BKT ignores forgetting and item
   difficulty.
3. **Latent-trait / deep models** (IRT, DKT/deep knowledge tracing). More accurate in benchmarks but
   opaque, data-hungry, and hard to justify to a mentor.

**Decision: start with BKT-style mastery + an explicit forgetting term, behind a `MasteryEstimator`
interface.** Rationale: it satisfies "explainable and measurable" (every update is a legible Bayesian
step a mentor can be shown), is cheap enough to run on-device/offline, needs little data to be
useful, and gives the probability-with-uncertainty the Decision Engine needs. The interface lets us
upgrade to an IRT- or DKT-based estimator later *from our own data*, once we can prove it beats the
transparent baseline on retention outcomes — never before. Forgetting is layered in via
`memory_strength` (§5) so mastery **decays** between reviews, which classic BKT omits and our
population critically needs.

---

## 3. Misconceptions

A misconception is not "an error" — it is a **specific, recurring wrong mental model** the platform
can name and target (Curriculum Studio authors `common_misconceptions` and `misconception_detectors`
per lesson). Modeling them explicitly is what turns "got it wrong" into "believes you carry the
larger digit," which the AI Runtime can actually address.

Per `(student, misconception)`:

| Field | Meaning |
| --- | --- |
| `misconception_ref` | The authored misconception id (from the lesson/objective). |
| `objective_code` | The SLO it obstructs. |
| `state` | `suspected · confirmed · being_remediated · cleared · recurred`. |
| `evidence_count` | How many attempts triggered its detector (confidence it's real). |
| `first_detected_at`, `last_detected_at`, `cleared_at` | Timeline. |

- **Detection.** The AI Runtime + assessment scoring run the authored `misconception_detectors`
  against each response; a match raises `suspected`, repeated matches → `confirmed`. This keeps
  detection **authored and reviewable** (a human wrote the detector), not an unaccountable AI guess.
- **Clearance.** A misconception moves to `cleared` only after the learner succeeds on targeted items
  *that the misconception would have caused them to fail* — evidence of the corrected model, not just
  a later correct answer. `recurred` if it reappears (a strong signal to escalate to a mentor).
- **Effect.** An active/confirmed misconception on an objective **caps** its `mastery` and routes the
  learner into the authored `adaptive_remediation` for that misconception (Decision Engine). You
  cannot "master" an objective you hold a confirmed misconception about.

---

## 4. Derived mastery state (the state machine the Decision Engine reads)

`state` is a **pure function** of `mastery`, `mastery_uncertainty`, `active_misconceptions`,
`memory_strength`, and time — never set directly, always recomputed, so it is reproducible and
auditable.

```text
not_started   : no attempts yet
in_progress   : attempts exist, mastery below threshold OR uncertainty too high OR open misconception
mastered      : mastery >= threshold(objective) AND uncertainty low AND no confirmed misconception
needs_review  : was mastered, but decayed estimate has dropped toward the review line (due soon)
at_risk       : decayed estimate has crossed below the retention floor (likely forgotten) → prioritize
```

- Thresholds are **per-objective** (a foundational number fact demands higher, more certain mastery
  than an enrichment topic) and are defined in LEARNING_DECISION_ENGINE, not hard-coded here.
- The `mastered → needs_review → at_risk` slide is driven by the forgetting model (§5): mastery is
  not static; the model *predicts* decay so revision is scheduled *before* the child fails, which is
  the whole point of spacing.

---

## 5. Memory strength and the forgetting model (drives spacing)

Retention is modeled with an explicit, tunable decay so the Decision Engine can schedule spaced
retrieval (LEARNING_SCIENCE §2). Per objective we keep `memory_strength` (a stability/half-life
parameter):

- **Recall probability** at time *t* since `last_seen_at` decays as a function of elapsed time and
  `memory_strength` (a monotonically decreasing curve — e.g., an exponential/half-life form). This is
  the *predicted* mastery used to drive `needs_review`/`at_risk`.
- **On a successful spaced retrieval**, `memory_strength` **increases** (the interval to the next
  review expands — expanding intervals, the core spacing result). On a failure, it **contracts** (the
  objective returns sooner, and may drop out of `mastered`).
- `next_review_at` is set so the review lands when predicted recall dips to a target (a "desirable
  difficulty" retrieval — not so soon it's trivial, not so late it's forgotten).
- The whole memory model sits behind a `ForgettingModel` interface (half-life baseline → FSRS-style
  upgrade path) so it is **replaceable without touching callers**, and **computable offline** (the
  next-due date can be cached on-device and reconciled on sync).

This is deliberately separate from `mastery`: `mastery` is "did they learn it," `memory_strength` is
"how durably" — a child can learn something quickly (high mastery fast) yet forget it quickly (low
strength), and the platform must see both.

---

## 6. Confidence (self-report) — tracked apart from mastery

The brief lists **confidence** as a first-class dimension. We store the learner's *self-reported*
confidence (`self_confidence`) **separately** from measured `mastery`, because the **calibration gap**
between them is one of the most useful signals in education:

- **Over-confident** (high self-confidence, low mastery) → the child doesn't know they have a gap;
  the Runtime surfaces gentle corrective retrieval and the mentor is informed. This is a classic
  precursor to silent failure.
- **Under-confident** (low self-confidence, high mastery) → the child knows more than they think;
  the Runtime provides encouragement and success experiences to build efficacy (motivation is a
  safety/engagement concern, not just nice-to-have).
- Confidence is elicited lightly and non-punitively (e.g., a "how sure are you?" tap before/after an
  attempt), never as a grade. Calibration error is an analytics metric (LEARNING_ANALYTICS).

Keeping them separate avoids the trap of letting a child's self-assessment inflate the mastery
estimate the platform acts on — only *evidence* moves `mastery`.

---

## 7. Learning pace

`pace_factor` captures how much practice **this** learner needs to reach mastery on an objective,
relative to a cohort baseline, aggregated across objectives into a per-subject and overall pace:

- Computed from `attempts-to-mastery` and `time-to-mastery`, normalized against the objective's
  authored `estimated_duration` and cohort distributions.
- **Uses:** the Decision Engine sizes sessions and corrective budgets to the learner (a slower-pace
  child gets more scaffolding and smaller steps, not a harder push); Analytics reports **learning
  velocity**; the mentor sees pace trends to spot a child who is *slowing* (a wellbeing/‑difficulty
  signal).
- **Explicitly not** a label or a ceiling. Pace is descriptive and dynamic; it must never become a
  fixed "slow learner" tag. It informs support, never gatekeeps ambition. (This is a stated design
  constraint, checked in review.)

---

## 8. Assessment evidence — the immutable audit trail

Every estimate above is **derived**; the ground truth is the evidence. Per attempt we record an
immutable `AssessmentEvidence` entry:

| Field | Meaning |
| --- | --- |
| `evidence_id` | UUIDv7. |
| `student_ref`, `objective_code`, `item_ref` | What was attempted (item from a published lesson). |
| `session_id` | The session it happened in. |
| `outcome` | correct / incorrect / partial. |
| `response_summary` | De-identified features of the response (not raw free text with PII). |
| `misconception_hits` | Which detectors fired. |
| `hints_used`, `attempts_in_item`, `response_time_ms` | Effort/struggle signals. |
| `context` | first-exposure / practice / spaced-review / summative. |
| `estimator_before`, `estimator_after` | Mastery before/after (explainability: *why* mastery moved). |
| `occurred_at` | Timestamp. |

- **Append-only and immutable** — the evidence trail is never edited (same discipline as Curriculum
  Studio's audit log). Estimates can be **recomputed** from evidence (a new `MasteryEstimator` can be
  back-tested against history), which is why the raw evidence, not just the derived number, is the
  system of record.
- `estimator_before/after` makes every mastery change **explainable**: a mentor can see "mastery went
  0.62 → 0.78 because of this correct spaced retrieval." No unexplained jumps.
- This trail is also the **formative-assessment** feed (LEARNING_SCIENCE §5) the mentor dashboard and
  Analytics consume.

---

## 9. Privacy, safety, and data governance (non-negotiable)

The Student Model holds **child data** — the most sensitive data in the platform — so it is designed
to the strictest posture, and its *implementation is gated on the Phase-1.5 governance decisions*
(lawful basis, DPIA, residency). Design commitments:

- **Pseudonymous keys.** The model keys on an opaque `student_ref`, not a name/identity. Identity
  mapping lives in a separate, tightly controlled identity context — the learning brain never needs
  to know who the child *is*, only their learning state. (Contrast: Curriculum Studio holds **no**
  child data at all; the Student Model is the first context that does, hence the elevated controls.)
- **Data minimization.** We store learning-relevant features and de-identified response summaries —
  **not** raw chat transcripts with personal disclosures. Raw AI-session content is handled under the
  safety pipeline with its own retention, not persisted into the learning model.
- **Crypto-shredding / erasure.** Per-student data is encrypted with a per-student key so an erasure
  request is satisfiable by destroying the key (doc 56 BC/DR pattern), even across backups.
- **Least privilege + audit.** Every read/write of the Student Model is authorized (deny-by-default
  PDP) and audit-logged; mentors see only their assigned learners; RLS scopes rows.
- **Safety signals are first-class.** Distress/wellbeing signals detected in a session are routed to
  the safeguarding pipeline **immediately**, not buried as an analytics metric — child safety wins
  over learning optimization, always.
- **Sharding-ready.** The model is keyed and partitioned by `student_ref` (per doc 09) so it scales
  horizontally to millions of learners; the learning brain's write load is per-student and shards
  cleanly.

---

## 10. Relationship to other components

- **Reads from:** Curriculum Studio published objectives + assessment items + authored misconceptions
  (via events); the DAG for prerequisites.
- **Written by:** the Session Engine (after every interaction) through the Student Model repository in
  a Unit of Work (evidence + estimate update commit atomically).
- **Read by:** the Decision Engine (to choose next action), the Mentor Portal (to review), Analytics
  (to measure). All reads go through the repository/port — no context reaches into the model's tables.
- **Estimators/forgetting models are ports** (`MasteryEstimator`, `ForgettingModel`), so the learning
  science can evolve without a schema or caller change — the single most important extensibility seam
  in this model.

The domain types (aggregates/value objects/events/repositories) for everything above are specified
in [LEARNING_DOMAIN_MODEL.md](LEARNING_DOMAIN_MODEL.md); the decisions that consume this model are in
[LEARNING_DECISION_ENGINE.md](LEARNING_DECISION_ENGINE.md).
