# Learning Analytics

Status: Design (Phase 4, pre-implementation). Defines what the platform **measures**, how it computes
it, who sees it, and how it stays privacy-safe. Analytics closes the loop the
[LEARNING_SCIENCE_FRAMEWORK.md](LEARNING_SCIENCE_FRAMEWORK.md) demands: it is how we **validate or
refute** each learning-science choice from *our own* data rather than assuming lab effect sizes
transfer to Urdu-medium KG–10 learners on 3G.

Two audiences, two purposes: (1) **per-learner** insight for mentors/parents/the learner (formative,
actionable), and (2) **aggregate** insight for the platform (is the pedagogy working? where are the
content gaps?). Both are **evidence-derived and explainable**, and both **respect privacy** (Master
Overview: "support product improvement while respecting user privacy").

---

## 1. Architecture — event-sourced, warehouse-computed, never in the OLTP hot path

- Analytics is **derived from the session events** emitted through the outbox
  (`InteractionRecorded`, `ObjectiveMastered`, `MisconceptionDetected/ Cleared`, `ReviewCompleted`,
  `SessionCompleted`, …). The Session Engine never computes analytics inline.
- Events flow to a **column-store warehouse** (ClickHouse-compatible, doc 31), where the millions–
  billions of interaction rows live — **not** in the Student Model OLTP (that stays per-learner and
  small; this mirrors the Curriculum Studio §0 boundary: student-scale data lives in the warehouse).
- Metrics are computed as warehouse roll-ups and materialized read models; a small set of
  **aggregates is pushed back** to the OLTP/mentor read models for low-latency display (e.g., a
  learner's current mastery summary). Heavy OLAP never touches the learner-facing write path.
- Events carry **de-identified** payloads (pseudonymous `student_ref`, feature summaries — no raw chat
  text, no PII); the warehouse operates on pseudonymous data, and cohort reporting is aggregated with
  small-cohort suppression (§6).

---

## 2. The six required metric families

### 2.1 Mastery

- **Objective mastery** — the calibrated estimate per SLO (from the Student Model), rolled up to
  chapter/subject/grade. Reported *with uncertainty* (never a bare percentage that hides thin
  evidence).
- **Mastery breadth vs depth** — how many objectives reached mastery (breadth) and how durably they
  are held (depth = retained mastery over time, §2.3).
- **Curriculum coverage** — proportion of the grade's SLOs mastered / in-progress / not-started.
- Explainability: every mastery figure drills down to the assessment evidence (STUDENT_MODEL §8).

### 2.2 Engagement

- **Active learning time** (attention-on-task, not just app-open), **session frequency/regularity**
  (consistency beats bingeing for retention), **completion of started sessions**, **return rate**.
- **Struggle/flow balance** — share of interactions in the productive-difficulty band vs
  frustration vs boredom (from success rates + hint/response-time signals). Engagement here is a
  **wellbeing and learning** signal, not a vanity/DAU metric — a falling engagement trend for a child
  is a mentor alert, not a growth-dashboard number.

### 2.3 Revision effectiveness

The metric that **validates spaced repetition** for our population:

- **Retention curve** — recall success on spaced reviews as a function of interval; is our schedule
  actually landing reviews at the right time (success in the target band)?
- **Forgetting reduction** — do objectives that go through spaced review decay slower than a
  counterfactual? (Measured via review outcomes over time; A/B on interval policy.)
- **Review-debt health** — are due reviews being served within budget, or is debt accumulating (a
  sign to tune caps or flag overload)?
- If revision effectiveness is poor, the `ForgettingModel` parameters/algorithm are wrong for us and
  are retuned/replaced — the whole point of the pluggable estimator (FRAMEWORK §10).

### 2.4 Learning velocity

- **Attempts-to-mastery** and **time-to-mastery** per objective, normalized by objective difficulty
  and cohort (the Student Model `pace_factor`).
- **Velocity trend** — is a learner speeding up (building fluency) or slowing (a difficulty/wellbeing
  signal)? A *slowing* trend is surfaced to mentors.
- Velocity is **descriptive**, never a label or a ranking of children — it informs support, and its
  misuse (labeling a child "slow") is an explicit anti-goal checked in review.

### 2.5 Completion

- **Lesson/objective/session completion rates**, **plan adherence** (did adaptive re-planning help or
  hurt completion?), and **drop-off points** (where do children abandon — a UX/content-gap signal).

### 2.6 Progression

- **Curriculum progression** through the grade's DAG (objectives unlocked/mastered over time),
  **readiness for next grade** (mentor-reviewed, never auto-promotion), and **milestone attainment**.
- Progression is reported against the **prerequisite DAG**, so "progress" means real unlocking of
  downstream capability, not just activity.

---

## 3. Derived/diagnostic analytics that make the platform smarter

Beyond the six families, analytics feeds the improvement loops:

- **Misconception analytics** — prevalence, clearance rate, recurrence per authored misconception →
  tells Curriculum Studio which misconceptions are common and whether the authored remediation
  actually clears them.
- **Content-gap signals** — where the AI Runtime hit *model uncertainty* / out-of-scope questions
  cluster → "children keep asking X and it isn't authored" → a Curriculum Studio backlog item.
- **Item psychometrics** — the aggregated, de-identified `item_statistics` (difficulty, discrimination,
  mis-key detection) pushed **back to Curriculum Studio** (the inbound `ItemStatisticsUpdated` event
  from the persistence design) so authors fix bad items. Analytics is the source of that feedback.
- **Calibration** — the confidence-vs-mastery gap (STUDENT_MODEL §6) aggregated, to see if learners
  are systematically over/under-confident (a metacognition target).
- **Policy effectiveness (A/B)** — every Decision-Engine policy parameter (interval targets, success
  bands, hint caps, thresholds) is measurable and experimentally tunable; analytics is how we prove a
  change in policy improved retention/mastery before rolling it out.

---

## 4. Audience views

- **Learner** — a simple, encouraging, Urdu-first progress view (mastery grown, streaks, next goals);
  age-appropriate, never a discouraging ranking.
- **Parent** (Parent Portal) — progress, consistency, and plain-language reports ("your child has
  mastered counting to 20 and is working on addition"), designed for **low-literacy** households
  (audio/visual summaries). Privacy-scoped to their own child.
- **Mentor** (Mentor Portal) — the actionable formative view: who needs help, active misconceptions,
  slowing velocity, wellbeing/engagement alerts, and the evidence to act. This is the human side of
  formative assessment.
- **Curriculum Studio** — content-gap and item-quality feedback (above).
- **Platform/leadership** — aggregate, privacy-safe outcomes (mastery, retention, progression at
  cohort/region level) to steer the product and prove educational impact.

---

## 5. Explainability and honesty

- Every learner-facing metric is **traceable to evidence** (no unexplained numbers). A mentor can
  always answer a parent's "why does it say this?"
- We **report uncertainty** and avoid false precision (mastery with confidence intervals; small-sample
  metrics flagged as provisional).
- Analytics **measures the pedagogy, including its failures**: if spacing isn't reducing forgetting,
  or adaptive remediation isn't clearing misconceptions, the dashboards must show it (Master Overview:
  "Never hide risks"). Metrics that could only ever flatter the product are not built.

---

## 6. Privacy, safety, and governance

- **Pseudonymous + de-identified.** The warehouse holds pseudonymous `student_ref` and feature
  summaries, not names or raw content. Identity re-association is a separate, tightly controlled path.
- **Small-cohort suppression.** Aggregate/cohort reporting suppresses or noises groups below a
  threshold so individuals cannot be re-identified from "aggregates."
- **Purpose limitation + minimization.** Analytics data is used for learning improvement and safety,
  not sold or repurposed; only learning-relevant features are collected.
- **Wellbeing signals are not "just analytics."** Distress/safeguarding signals route to the
  **safeguarding pipeline in real time** (SESSION_ENGINE §4), independent of the analytics batch path —
  child safety is never gated behind a nightly roll-up.
- **Retention + erasure.** Analytics data honors the retention policy (doc 57) and per-student erasure
  (crypto-shred), consistent across warehouse and OLTP.
- **Access control + audit.** Every view is authorized (mentors see only their learners; parents only
  their child) and access is audit-logged.
- Implementation is **gated on Phase-1.5 governance** (lawful basis, DPIA) exactly like the Student
  Model — analytics over child data does not ship before those decisions land.

Domain events that analytics consumes, and their schemas, are listed in
[LEARNING_DOMAIN_MODEL.md](LEARNING_DOMAIN_MODEL.md).
