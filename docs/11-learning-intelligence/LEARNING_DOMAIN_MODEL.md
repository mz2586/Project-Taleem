# Learning Domain Model

Status: Design (Phase 4, pre-implementation). The DDD model that makes the other Phase-4 docs
buildable: bounded contexts, aggregates, entities, value objects, domain events, repository ports,
and the API surface. It is the contract the implementation follows (Clean Architecture + DDD +
Repository + Unit of Work, per the Master Overview). Types are shown as language-neutral sketches
(the implementation is Python 3.12, pure-stdlib domain, exactly like `curriculum_studio`).

Naming: the bounded context is **`learning`** (the Learning Intelligence Platform). It is distinct
from `curriculum_studio` (authoring) — no cross-context foreign keys; it consumes curriculum via
events/read models and emits its own events.

---

## 1. Bounded contexts and boundaries

The Learning Intelligence Platform is **one deployable bounded context, `learning`**, with internal
modules — not four separate contexts (see design-review F1: four contexts was premature distribution
that forced a cross-aggregate write on every turn). Analytics is a **downstream event consumer**, not
a module of this service.

| Module (within the `learning` context) | Responsibility | Holds child data? |
| --- | --- | --- |
| `learning.knowledge` | Student Knowledge Model — mastery, misconceptions, evidence, schedule | **Yes** (pseudonymous) |
| `learning.decision` | Decision Engine — **pure** policy sub-package (no persistence, no I/O) | No (operates on passed-in state) |
| `learning.session` | Session Engine — orchestration/saga, AI Teaching Runtime driver | Transient session data |
| *(downstream)* `analytics` | Derived metrics (warehouse) — separate service/consumer | De-identified only |

`knowledge` and `session` share **one schema and one Unit of Work**, so a turn commits knowledge +
session state atomically with no distributed transaction. `decision` is a pure library reused by
`session`. Keeping `decision` + the knowledge estimators pure isolates the ≥95%-coverage "critical
learning logic" for fast, deterministic testing. The module seam still allows extracting `session`
into its own service at national scale — but we do not pay for that distribution now.

Upstream dependencies (read-only, via events/read models): Curriculum Studio published lessons,
objectives, assessment items, authored teaching/misconception objects, the prerequisite DAG.

---

## 2. Value objects (immutable)

```text
StudentRef        : opaque pseudonymous id (never a name)
ObjectiveCode     : SLO code (mirrors curriculum_objective.standard_code)
Mastery           : { value: 0..1, uncertainty: 0..1 }          # probability + confidence
MemoryStrength    : { stability: float, last_seen_at, next_review_at }
Confidence        : { self_reported: 0..1, sampled_at }
Pace              : { attempts_to_mastery, time_to_mastery_s, pace_factor }
MasteryState      : enum { not_started, in_progress, mastered, needs_review, at_risk }
MisconceptionState: enum { suspected, confirmed, being_remediated, cleared, recurred }
Outcome           : enum { correct, incorrect, partial }
InteractionContext: enum { first_exposure, practice, spaced_review, remediation, formative }
Decision          : tagged union (Teach|Review|Remediate|Assess|Consolidate|EscalateToMentor|Rest)
                    + rationale: Rationale
Rationale         : ordered list of {rule_id, inputs, note}     # explainability
MasteryThreshold  : { tau: 0..1, max_uncertainty: 0..1 }        # per-objective
```

Value objects have **no identity** and are freely copied; `Mastery` carrying `uncertainty` (not a
bare float) and `Decision` carrying `rationale` (not a bare tag) are the two most important — they
encode "explainable and measurable" into the type system.

---

## 3. Aggregates and entities

### 3.1 `StudentKnowledge` (aggregate root — context `learning.knowledge`)

The consistency boundary for one learner's learning state. One UoW mutates one `StudentKnowledge`.

```text
StudentKnowledge (root)
  student_ref: StudentRef
  objectives: map<ObjectiveCode, ObjectiveMastery>   # owned entities
  lock_version: int
  invariants:
    - an objective is `mastered` only if Mastery ≥ threshold, uncertainty ≤ max, no confirmed misconception
    - evidence is append-only; estimates are derived from evidence
    - state is always the pure function of (mastery, uncertainty, misconceptions, memory, now)

  ObjectiveMastery (entity, owned)
    objective_code, mastery: Mastery, state: MasteryState
    memory: MemoryStrength, confidence: Confidence, pace: Pace
    attempts, correct_streak
    misconceptions: list<MisconceptionRecord>
    recompute(evidence, estimator, forgetting_model, now) -> updates mastery/state/memory

  MisconceptionRecord (entity, owned)
    misconception_ref, objective_code, state: MisconceptionState, evidence_count, timestamps

  AssessmentEvidence (entity, owned, IMMUTABLE, append-only)
    evidence_id, objective_code, item_ref, session_id, outcome,
    misconception_hits, hints_used, response_time_ms, context,
    estimator_before: Mastery, estimator_after: Mastery, occurred_at
```

Mastery/memory are **recomputed** by injected `MasteryEstimator` / `ForgettingModel` ports (§6),
never hand-set — so the learning science is swappable without touching the aggregate.

### 3.2 `Session` (aggregate root — context `learning.session`)

The saga for one learning session (SESSION_ENGINE).

```text
Session (root)
  session_id, student_ref, state: SessionState, plan: SessionPlan
  interactions: list<Interaction>        # owned, append-only
  budget: SessionBudget, offline_context, correlation_id, started_at, ended_at
  invariants:
    - state transitions follow the SessionState machine (illegal transitions rejected)
    - ESCALATED/ENDED_SAFELY reachable from any state (safety)
    - interactions are append-only; each is idempotent by client id

  Interaction (entity, owned, append-only)
    interaction_id (client-generated, idempotent), objective_code, decision: Decision,
    turns: list<Turn>, outcome: Outcome?, evidence_ref, applied: bool, occurred_at

  SessionPlan (value)      : ordered list<Decision> (advisory, re-planned each step)
  SessionBudget (value)    : { max_duration_s, max_items, max_consecutive_failures }
  SessionState (enum)      : CREATED..ENDED (+ PAUSED, ESCALATED, ENDED_SAFELY, ABANDONED)
```

### 3.3 `RevisionSchedule` — modeled *within* `StudentKnowledge`

Revision due-dates live on `ObjectiveMastery.memory.next_review_at` rather than a separate aggregate,
because a review decision needs mastery + memory together atomically. "Due reviews" is a **query**
over `StudentKnowledge`, not its own aggregate — avoids a two-aggregate transaction on every review.

---

## 4. Domain events (emitted via the transactional outbox)

Past-tense facts; de-identified payloads (pseudonymous ref, no raw content); consumed idempotently.

| Event | Emitted when | Key consumers |
| --- | --- | --- |
| `InteractionRecorded` | each interaction committed | Analytics warehouse |
| `ObjectiveMasteryChanged` | mastery/state crosses a boundary | mentor read model, Analytics |
| `ObjectiveMastered` | objective reaches `mastered` | Analytics, progression, parent report |
| `MisconceptionDetected` | detector confirms a misconception | mentor alert, Analytics, Curriculum gap |
| `MisconceptionCleared` / `MisconceptionRecurred` | remediation outcome | mentor, Analytics |
| `ReviewCompleted` | spaced retrieval attempted | Analytics (revision effectiveness) |
| `ReviewScheduled` | `next_review_at` set/updated | offline scheduler, reminders |
| `SessionStarted` / `SessionCompleted` / `SessionEscalated` | lifecycle | Analytics, mentor, safeguarding |
| `MentorEscalationRaised` | pedagogical/scope escalation | Mentor Portal |
| `SafeguardingSignalRaised` | wellbeing/safety signal | **safeguarding pipeline (real-time)** |
| `ContentUncertaintyObserved` | runtime model-uncertainty / out-of-scope cluster | Curriculum Studio backlog |

Inbound (consumed): Curriculum Studio's `LessonPublished`/`ObjectiveAdded` (update read models);
Analytics' `ItemStatisticsUpdated` (already defined in the persistence EVENT_MODEL) is consumed by
Curriculum Studio, not here — `learning` *produces* the raw evidence that computes it.

`SafeguardingSignalRaised` is special: it is **also** delivered on a real-time path (not only the
batch outbox drain), because safety cannot wait for a relay poll — child safety wins over
architectural uniformity.

---

## 5. Repository ports (Clean Architecture — interfaces in the application layer)

```text
StudentKnowledgeRepository
  get(student_ref) -> StudentKnowledge | None
  save(knowledge) -> None                       # optimistic-locked, audited, atomic with evidence
  due_reviews(student_ref, now, limit) -> list<ObjectiveCode>   # query, not load-all

SessionRepository
  get(session_id) -> Session | None
  save(session) -> None
  find_abandoned(student_ref, older_than) -> list<Session>

CurriculumReadModel            # read-only projection of published curriculum (from events)
  lesson_for(objective_code) -> PublishedLesson
  objective(objective_code) -> ObjectiveView
  prerequisites(objective_code) -> list<ObjectiveCode>          # the DAG
  assessment_items(objective_code, selection) -> list<ItemView>

EventPublisher                 # transactional outbox
  publish(events) -> None      # committed in the same UoW as the aggregate write
```

Everything above is a **port**; adapters (SQLAlchemy repositories, outbox publisher, curriculum read
model) live in infrastructure and are injected — the same pattern proven in `curriculum_studio`.

## 6. Learning-science ports (the extensibility seams)

```text
MasteryEstimator     : update(prior: Mastery, evidence, item_difficulty) -> Mastery
ForgettingModel      : decay(mastery, memory, elapsed) -> Mastery ; on_review(memory, outcome) -> MemoryStrength
DecisionPolicy       : decide_next(state_slice, curriculum_slice, config, now) -> Decision   # pure
```

These are **injected pure functions**, so the pedagogy (BKT→IRT/DKT, half-life→FSRS, policy tuning)
evolves without changing aggregates, repositories, or callers. This is the single most important
design decision for a "maintainable for the next decade" learning platform: **the science is a
plugin, the domain is stable.**

## 7. Application services (use-case orchestration, Unit of Work)

```text
learning.knowledge.KnowledgeService
  record_interaction(student_ref, interaction) -> updates estimates + schedule, emits events   # 1 UoW
  snapshot(student_ref) -> StudentKnowledgeView

learning.session.SessionService
  start(student_ref, context) -> Session
  next(session_id) -> Decision                         # asks DecisionPolicy over current knowledge
  submit_turn(session_id, turn) -> RuntimeResponse     # drives AI Teaching Runtime, records evidence
  end(session_id) -> SessionSummary
  # each mutating call = one UoW; safety/escalation handled as first-class outcomes
```

Services own transactions (UoW), authorization (deny-by-default PDP), and event emission; the domain
stays pure; the runtime/LLM lives behind the `TeachingRuntime` port.

---

## 8. API surface (contract-first, OpenAPI 3.1; internal + portal-facing)

All child-data endpoints are authenticated, authorized (PDP), audited, and **gated on Phase-1.5**.
Verbs use the platform's action-style convention.

```text
# Session (Student Portal / runtime)
POST   /v1/learning/sessions                      -> start a session            (201 Session)
POST   /v1/learning/sessions/{id}:next            -> get next Decision          (200 Decision+rationale)
POST   /v1/learning/sessions/{id}:turn            -> submit a learner turn      (200 RuntimeResponse)
POST   /v1/learning/sessions/{id}:end             -> end a session              (200 SessionSummary)
GET    /v1/learning/sessions/{id}                 -> session state (resume)     (200 Session)

# Knowledge (Mentor/Parent Portals, read-mostly)
GET    /v1/learning/students/{ref}/knowledge      -> mastery summary + evidence (200 KnowledgeView)
GET    /v1/learning/students/{ref}/reviews        -> due reviews                (200 list)
GET    /v1/learning/students/{ref}/misconceptions -> active misconceptions      (200 list)

# Mentor workflow
GET    /v1/learning/mentor/escalations            -> pending escalations        (200 list)
POST   /v1/learning/mentor/escalations/{id}:resolve -> resolve                  (200)

# Explainability (mentor/parent "why")
GET    /v1/learning/students/{ref}/objectives/{code}/rationale -> decision trace (200 Rationale)
```

Errors are RFC 9457 problem+json (platform convention). Every endpoint's authorization scopes to the
caller's relationship to the learner (mentor→assigned learners, parent→own child). Promotion/summative
endpoints are deliberately **absent** from autonomous APIs — those go through the mentor-confirmed,
identity-assured assessment path (Phase 7), never an automated call.

---

## 9. Persistence shape (consistent with the Curriculum Studio persistence design)

- Schema-per-context: `learning` schema (no cross-context FK), UUIDv7 keys, optimistic locking,
  append-only immutable `assessment_evidence` (+ hash-chain audit), transactional `outbox`, RLS,
  **sharded/partitioned by `student_ref`** (the student-scale data the Curriculum Studio design
  deliberately kept out lives *here*, and is built to shard from day one).
- Per-student **crypto-shredding** key for erasure (STUDENT_MODEL §9).
- The physical schema, ERD, and event envelopes will be specified in a `learning/persistence/` design
  set (mirroring `docs/10-curriculum-studio/persistence/`) **before** implementing persistence — same
  discipline: design → review → build.

---

## 10. Mapping back to the briefs (traceability)

| Requirement | Modeled by |
| --- | --- |
| Track mastery per objective | `ObjectiveMastery.mastery` (+uncertainty) in `StudentKnowledge` |
| Misconceptions | `MisconceptionRecord` + `MisconceptionDetected/Cleared` events |
| Revision history / scheduling | `AssessmentEvidence` (history) + `MemoryStrength.next_review_at` |
| Confidence | `Confidence` value object (separate from mastery) |
| Learning pace | `Pace` value object + velocity analytics |
| Assessment evidence | immutable `AssessmentEvidence` entity (system of record) |
| Lesson selection / decisions | `DecisionPolicy` (pure) → `Decision` (+rationale) |
| AI teaching within scope | `learning.session` + `TeachingRuntime` port (AI_TEACHING_RUNTIME) |
| Session lifecycle | `Session` aggregate + `SessionState` saga |
| Analytics | domain events → warehouse (LEARNING_ANALYTICS) |
| Explainability | `Rationale` on every `Decision`; `estimator_before/after` on evidence |
| Extensible pedagogy | `MasteryEstimator`/`ForgettingModel`/`DecisionPolicy` ports |
| Child safety first | `SafeguardingSignalRaised` (real-time) + escalation as first-class outcomes |
| Scale to millions | context split + shard-by-`student_ref` + event-sourced analytics |

The design review that stress-tests all of this is in
[LEARNING_PLATFORM_DESIGN_REVIEW.md](LEARNING_PLATFORM_DESIGN_REVIEW.md); implementation begins only
after it passes.
