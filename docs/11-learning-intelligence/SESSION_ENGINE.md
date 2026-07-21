# Session Engine

Status: Design (Phase 4, pre-implementation). The Session Engine is the **orchestrator** that runs a
learning session end to end, coordinating the [LEARNING_DECISION_ENGINE.md](LEARNING_DECISION_ENGINE.md)
(decides), the [AI_TEACHING_RUNTIME.md](AI_TEACHING_RUNTIME.md) (teaches), and the
[STUDENT_MODEL.md](STUDENT_MODEL.md) (remembers). It owns the session **transaction and lifecycle**;
it contains policy-free coordination logic (the policy lives in the Decision Engine).

Design stance: a session is a **saga** (a sequence of steps with a durable state machine and
compensations), not a single transaction — it spans multiple learner interactions, can be paused,
resumed, or interrupted (a child closes the app, loses signal), and must never leave the Student
Model half-updated. Resumability and crash-safety are first-order requirements, not add-ons, because
our learners are on flaky connections and cheap devices.

---

## 1. Lifecycle (the brief's flow, made durable)

```text
Start Session → Load Student → Load Lesson → Teach → Interact → Assess
   → Update Knowledge → Schedule Revision → Store Analytics → End Session
```

Realized as an explicit state machine (`SessionState`), each transition persisted so the session
survives a crash/disconnect:

```text
CREATED → LOADING → PLANNING → TEACHING ⇄ INTERACTING ⇄ ASSESSING
   → UPDATING → SCHEDULING → RECORDING → ENDED
                 │
                 └── (any state) → PAUSED  ── resume ──▶ back to prior state
                 └── (any state) → ESCALATED (mentor/safety) → ENDED_SAFELY
                 └── (any state) → ABANDONED (timeout) → reconcile on next start
```

The `TEACHING ⇄ INTERACTING ⇄ ASSESSING` cycle repeats per objective in the session plan; `UPDATING →
SCHEDULING → RECORDING` is the durable close-out that must complete atomically per interaction.

---

## 2. The steps in detail

**Start Session.** Create a `Session` aggregate (id, student_ref, started_at, device/offline context,
correlation id). Authorize (deny-by-default PDP): is this actor allowed to start a session for this
learner? Reconcile any `ABANDONED` prior session first (§6).

**Load Student.** Load the Student Model slice needed for planning (mastery states, due reviews, open
misconceptions, pace, confidence) through the Student Model repository. Read-only snapshot for
planning; writes happen at close-out.

**Load Lesson.** From the plan's first `Teach`/`Review` decision, load the **approved published
lesson** (and its `offline_package` if offline) via the Curriculum read model. Only published,
in-scope content is loadable (the runtime cannot teach a draft).

**Plan.** Ask the Decision Engine for a **session plan** — an ordered list of decisions
(`Teach`/`Review`/`Remediate`/`Assess`/`Consolidate`) sized to the learner's pace and a session
time/effort budget appropriate to age. The plan is advisory: it is re-evaluated after each
interaction (adaptivity), so a struggling child's plan shrinks/simplifies mid-session.

**Teach / Interact / Assess.** For each planned objective, invoke the AI Teaching Runtime to run the
bounded teaching loop (present → elicit → interpret → respond). Each interaction yields **formative
evidence** and, for assessment items, an outcome. Safety/wellbeing signals can interrupt at any point
→ `ESCALATED`.

**Update Knowledge.** After each interaction (not only at session end — so a crash loses at most one
interaction), commit the evidence + recomputed mastery/misconception/confidence updates to the
Student Model in **one Unit of Work**. This is the durability boundary: evidence and the estimate it
produced commit together, or not at all (matches STUDENT_MODEL §8 immutable evidence + §2 estimate).

**Schedule Revision.** On mastery/decay changes, (re)compute `next_review_at`/`memory_strength` via
the forgetting model and persist — in the *same* UoW as the knowledge update, so scheduling never
drifts from the mastery it's based on.

**Store Analytics.** Emit learning events (`InteractionRecorded`, `ObjectiveMastered`,
`MisconceptionDetected`, `SessionCompleted`, …) to the **transactional outbox** (same pattern as
Curriculum Studio) for the Analytics warehouse and mentor/parent read models. Analytics is
**event-derived and eventual** — the session never blocks on analytics, and analytics never sees raw
child PII (de-identified events only).

**End Session.** Finalize the `Session` aggregate (ended_at, summary, outcomes), emit
`SessionCompleted`, release resources. `ENDED_SAFELY` if closed by escalation.

---

## 3. Transaction and consistency model

- **Per-interaction atomicity.** Each `Update Knowledge (+ Schedule Revision)` is one UoW: evidence
  append + estimate update + schedule update + outbox events commit together. A crash mid-session
  loses at most the *current* in-flight interaction, never corrupts the model.
- **Session state is durable.** `SessionState` transitions are persisted, so a resumed session knows
  exactly where it was. The session record + its interactions are the saga log.
- **Outbox for egress.** All cross-context effects (analytics, mentor notifications, safeguarding)
  go through the outbox — never a synchronous cross-context write — so the session is decoupled from
  downstream availability and DR-replay-safe (idempotent consumers keyed on interaction/session id).
- **Idempotency.** Interactions carry client-generated ids; replaying a synced offline interaction is
  a no-op if already applied (critical for offline sync — §5).

---

## 4. Adaptivity within a session

The plan is not fixed at the start:

- After each interaction, the engine **re-plans** from the freshly updated Student Model: shorten the
  session if fatigue/frustration shows, insert remediation if a misconception is confirmed, step
  difficulty, or end early (`Rest`).
- The Session Engine holds a **budget** (time, number of items, consecutive-failure limit) suited to
  the learner's age/pace; when the budget is hit it moves to close-out even if the plan isn't finished
  — protecting attention and wellbeing over "finishing the plan."
- **Escalation preempts.** A safety signal from the runtime transitions the session to `ESCALATED`
  immediately; teaching stops, the safeguarding pipeline is invoked, and the session ends safely with
  a full audit trail.

---

## 5. Offline and sync

- A session can run **fully offline** from cached content (`offline_package`) using the runtime's
  templated tier. Interactions, evidence, and state transitions are written to a **local durable log**
  (the platform's existing offline sync engine from M1).
- On reconnect, the local log **syncs** to the server, which applies interactions idempotently
  (§3), recomputes server-side estimates from evidence (the server is the system of record), and
  reconciles `next_review_at`. Conflict policy: **evidence is append-only and never conflicts**
  (two devices' attempts both count); derived estimates are recomputed server-side from the merged
  evidence, so there is no "last writer wins" on mastery.
- Offline sessions cap at the templated tier; adaptive rephrasing (LLM tiers) resumes online.

---

## 6. Crash, resume, and abandonment

- **Resume.** Reopening returns the learner to a `PAUSED`/last-persisted state with prior progress
  intact (per-interaction durability). No repeated work, no lost evidence.
- **Abandonment.** A session with no activity past a timeout is marked `ABANDONED`; the next
  `Start Session` reconciles it (finalizes analytics for what happened, closes it) before starting
  fresh — so dangling sessions don't accumulate and analytics stay accurate.
- **Exactly-once effects.** Because knowledge updates are idempotent and outbox events are
  deduplicated by consumers, neither a crash-resume nor an offline re-sync double-counts an attempt or
  double-fires a mastery event.

---

## 7. Boundaries, ports, and testability

- The Session Engine is **application-layer orchestration**: it depends on ports —
  `DecisionEngine` (pure, injected), `TeachingRuntime`, `StudentModelRepository`, `CurriculumReadModel`,
  `EventPublisher` (outbox), `Clock`, `SessionRepository` — and owns no learning policy or generative
  content itself.
- **The state machine and saga logic are deterministic and unit-testable** with fakes for the runtime
  and estimators: we can test "crash after Update, before Schedule → resume completes correctly,"
  "safety signal mid-Interact → ESCALATED + no further teaching," and "offline replay is idempotent"
  without a real LLM or DB. This is where the ≥95%-coverage learning-logic bar is met for
  orchestration.
- **Child safety is structural:** escalation is a top-level transition reachable from any state and
  is exercised in tests as a first-class path, not an error case.

Domain types for `Session`, `SessionState`, `Interaction`, and the session events are in
[LEARNING_DOMAIN_MODEL.md](LEARNING_DOMAIN_MODEL.md); the analytics derived from session events are in
[LEARNING_ANALYTICS.md](LEARNING_ANALYTICS.md).
