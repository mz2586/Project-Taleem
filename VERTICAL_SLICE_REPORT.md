# Vertical Slice Report — Phase 4.1

Project Taleem · First end-to-end Learning Intelligence vertical slice.
Status: **COMPLETE — all quality gates green.** Verified 2026-07-21.

One original lesson (Grade 4 · Mathematics · *Introduction to Fractions*) driven end-to-end through
every subsystem, on the real architecture (no mocks, no placeholder services, no fake APIs).

---

## 1. Quality gate summary

| Gate | Tool | Result |
| --- | --- | --- |
| Unit / domain / integration / API tests | pytest | **124 passed, 2 skipped** (Postgres-gated), 0 failed |
| Coverage | pytest-cov | **97% overall**; learning domain logic **≈98%** (≥95% bar met) |
| Lint | ruff (E,F,I,N,UP,B,S,C4,SIM,RET) | **All checks passed** |
| Format | black | **93 files unchanged** |
| Type check | mypy `--strict` | **Success: no issues in 77 source files** |
| OpenAPI validation | redocly lint | **3/3 contracts valid** (curriculum-studio, learning, platform) |
| Docs validation | markdownlint-cli2 @0.13.0 | **0 errors** |
| End-to-end slice | `python -m taleem_core.vertical_slice.runner` | **Runs clean; learner masters objective; session ends** |

The 2 skipped tests are the PostgreSQL-gated Curriculum Studio migration + FTS tests (run only when
`CS_DATABASE_URL` is set; verified separately against a real Postgres 16 container in Phase 3). The 1
pytest warning is a known upstream `StarletteDeprecationWarning` (surfaced, not suppressed).

---

## 2. Architecture summary

The slice exercises two bounded contexts and their real adapters:

- **Curriculum Studio** (`contexts/curriculum_studio`) — authors, reviews (5-gate chain), and
  **publishes** the lesson through its **SQLAlchemy persistence** (immutable versioning, quality
  gates, transactional outbox, hash-chained audit). The lesson is original, `authored-original`
  provenance, NCP-aligned.
- **Learning Intelligence** (`contexts/learning`) — one deployable context with internal modules:
  - `domain` (pure, framework-free): `values`, `knowledge` (Student Knowledge aggregate), `estimator`
    (BKT), `forgetting` (half-life spacing), `decision` (pure policy engine), `scorer`, `runtime`
    (templated AI teaching), `session` (saga state machine), `events`, `protocols`.
  - `application`: `KnowledgeService`, `SessionService`, `LearningAnalytics`, ports.
  - `adapters`: SQLAlchemy persistence for the Student Knowledge Model + immutable evidence +
    outbox; a curriculum read-model (integration seam); in-memory session repository; FastAPI router.

Design fidelity: the learning-science models sit behind ports (`MasteryEstimator`, `ForgettingModel`,
`DecisionPolicy`) exactly as designed, so pedagogy is swappable without touching aggregates or
callers. The AI teaching runtime is the **real templated (no-LLM) tier** operating strictly on
approved content — in-scope by construction (it can only emit content present in the `LessonView`).

```text
Curriculum Studio ──publish──▶ (SQL: lesson_version, outbox, audit)
        │  LessonPublished (design: event; slice: read-model)
        ▼
Learning: CurriculumReadModel ─▶ SessionService ─▶ DecisionEngine (pure)
                                      │                     │ Decision(+rationale)
                                      ▼                     ▼
                              TeachingRuntime          KnowledgeService ─▶ (SQL: student_knowledge,
                              (templated tier)              │                objective_mastery,
                                      │                     ▼                assessment_evidence,
                                   Scorer            StudentKnowledge         learning_outbox)
                                                      aggregate  ─▶ BKT + forgetting
                                                                          │
                                                              LearningAnalytics ◀─ events
```

Persistence footprint of the slice: **Curriculum Studio → SQLite (SQLAlchemy, real)**; **Student
Knowledge Model + evidence + events → SQLite (SQLAlchemy, real)**; **sessions → in-memory repository**
(transient saga state). Both SQL stores use the portable ORM that also targets PostgreSQL.

---

## 3. Complete execution trace

Verbatim from `python -m taleem_core.vertical_slice.runner` (timestamps are a deterministic clock):

```text
========================================================================
PROJECT TALEEM — VERTICAL SLICE EXECUTION TRACE
========================================================================
 1. Curriculum Studio: created draft lesson
      lesson: L-math-g4-intro-fractions
      objective: MATH-G4-FR-01
 2. Curriculum Studio: submitted + 5-gate review chain approved
 3. Curriculum Studio: PUBLISHED immutable version
      version: 1
      gates_green: True
 4. Learning: loaded student (cold-start)
      student: stu-0001
      initial_mastery: 0.3
      initial_state: not_started
 5. Session: started
      session_id: 019f80…  (UUIDv7)
      state: planning
 6. Decision Engine: select next
      decision: teach
      objective: MATH-G4-FR-01
      rationale: MATH-G4-FR-01 state=not_started
 7. AI Teaching Runtime: taught concept (approved content only, templated tier)
      utterances: 6
      session_state: interacting
 8. Interact: p1 answered correctly
      outcome: correct   mastery: 0.744   post: continue
 9. Interact: p2 answered wrong (misconception suspected); hint given
      hint: Think about pizza slices.   misconceptions: ['suspected']
10. Detect misconception: CONFIRMED
      confirmed: ['m-bigger-denominator-is-bigger']
      events: ['InteractionRecorded', 'MisconceptionDetected']
      post: remediate
11. Remediate: authored correction delivered
      correction: A bigger bottom number means more, smaller pieces. So 1/4 is SMALLER than 1/2.
12. Interact: p2 re-attempted correctly -> misconception CLEARED
      cleared: ['m-bigger-denominator-is-bigger']
      events: ['InteractionRecorded', 'MisconceptionCleared']
13. Update Knowledge: objective MASTERED
      item: p3-denominator   mastery: 0.951   uncertainty: 0.168   newly_mastered: True
      events: ['InteractionRecorded', 'ObjectiveMastered', 'ReviewScheduled']
14. Revision Scheduler: next review computed
      next_review_at: 15061.6   stability_s: 86400.0   state: mastered
15. Decision Engine: after mastery
      decision: complete   note: no eligible objective remains
16. Learning Analytics: progress summary
      objectives_mastered: 1   total_attempts: 5   accuracy: 0.6
      misconceptions_detected: 1   misconceptions_cleared: 1   reviews_scheduled: 1
      events_by_type: {InteractionRecorded:5, MisconceptionDetected:1, MisconceptionCleared:1,
                       ObjectiveMastered:1, ReviewScheduled:1, SessionStarted:1}
      objective_mastery: {MATH-G4-FR-01: 0.951}
17. Session: ended
      state: ended   interactions: 5

DECISION FLOW: teach -> continue -> remediate -> complete
MASTERED: True | SESSION: ended
```

### Required demonstration checklist (all proven above)

| Required step | Trace evidence |
| --- | --- |
| Curriculum lesson authored | step 1 |
| Lesson reviewed and approved | step 2 (5-gate chain) |
| Lesson published | step 3 (immutable version 1, gates green) |
| Student loaded | step 4 (cold-start, prior 0.3, high uncertainty) |
| Learning session started | step 5 |
| AI Teaching Runtime delivers lesson | steps 6–7 (decision `teach` → present) |
| Student completes assessment | steps 8–13 (answers scored) |
| Assessment engine evaluates | scorer → outcomes + misconception detection (steps 9–10) |
| Student Model updated | steps 8–13 (mastery 0.3 → 0.951; misconception confirmed→cleared) |
| Decision engine selects next action | steps 8/10/13/15 (`continue`/`remediate`/`advance`/`complete`) |
| Revision scheduled | step 14 (`next_review_at` computed on mastery) |
| Analytics recorded | step 16 (events + progress summary) |
| Session completed successfully | step 17 (`ended`) |

---

## 4. Test summary

| Suite | File | Focus |
| --- | --- | --- |
| Learning domain (unit) | `test_learning_domain.py` | estimator, forgetting, knowledge aggregate, scorer, runtime, session state machine, decision engine (24 tests) |
| Learning persistence | `test_learning_persistence.py` | Student Knowledge round-trip, append-only evidence idempotency, outbox, no-PII schema |
| Vertical slice (integration/e2e) | `test_vertical_slice.py` | full flow, decision flow, events, mastery, trace renders |
| Learning API | `test_learning_api.py` | session lifecycle over the real services, misconception feedback, 404s |
| Curriculum Studio (Phase 3) | `test_studio_*.py` | domain, service, SQL persistence, migration (PG-gated) |
| Platform/M1 | prior suites | config, logging, sync, health, etc. |

Total: **124 passed, 2 skipped, 0 failed** in ~5 s.

---

## 5. Coverage summary

Overall: **97%**. Critical learning logic (the `domain` layer) is **≈98%**, above the ≥95% bar.

| Module | Coverage |
| --- | --- |
| `domain/estimator.py` (BKT) | 100% |
| `domain/scorer.py` | 100% |
| `domain/runtime.py` | 100% |
| `domain/values.py` | 100% |
| `domain/curriculum_view.py` | 100% |
| `domain/decision.py` (decision engine) | 99% |
| `domain/knowledge.py` (Student Model) | 97% |
| `domain/forgetting.py` | 97% |
| `domain/session.py` (saga) | 97% |
| `application/knowledge_service.py` | 100% |
| `application/analytics.py` | 100% |
| `application/session_service.py` | 95% |
| `adapters/persistence/*` | 92–100% |
| `adapters/api.py` | 97% |
| `vertical_slice/runner.py` | 99% |

Uncovered lines are defensive/error branches (e.g., unreachable "no lesson" guards) and the CLI
`main()`.

---

## 6. Performance metrics

Indicative (SQLite, single process, deterministic clock — not a load benchmark):

- Full end-to-end slice (author → publish → 5 reviews → teach → 5 answers → master → analytics →
  end): **< 1 s** wall-clock.
- Full automated test suite (126 tests): **~5 s**.
- Per-interaction path (score → BKT update → persist evidence + mastery + schedule → emit events, one
  Unit of Work): sub-millisecond in-process; dominated by the SQLite commit.
- The decision engine and estimators are **pure and allocation-light** (no I/O), so they are not the
  bottleneck at any realistic scale; cost lives in persistence + (future) LLM calls.

Formal load/latency testing against PostgreSQL at 1M-learner scale is **out of scope for the slice**
and listed as a pre-scale action (§8).

---

## 7. Remaining gaps (scope boundaries of the slice — intentional)

These are **known, intentional** boundaries of a vertical slice, not defects:

1. **Governance gate.** Real child data, accounts, and the child-facing runtime remain blocked by the
   Phase-1.5 governance decisions (lawful basis, DPIA, residency, safeguarding SLA). The slice uses a
   single **synthetic pseudonymous** learner (`stu-0001`).
2. **Single lesson / objective.** One lesson, one SLO, no prerequisites — by the stop condition. The
   decision engine's DAG, spacing, and diagnostic paths are unit-tested but not exercised at breadth.
3. **AI runtime = templated tier only.** The real no-LLM tier is implemented and in-scope by
   construction; the small/regional and frontier LLM tiers (behind the `LLMGateway` port) are **not**
   implemented in the slice.
4. **Sessions are in-memory.** The durable learning data (knowledge, evidence, events) persists to
   SQL; the session saga state persists to an in-memory repository (transient). A SQL session store +
   resume-after-crash path is designed but not built here.
5. **Read model reads the DB directly.** The curriculum read model queries the published lesson
   directly rather than being fed by the `LessonPublished` outbox event via a relay/projector (the
   event is emitted and asserted; the projector is not yet built).
6. **Analytics is in-process.** The progress summary is computed in-process from the learning store;
   the warehouse-based analytics pipeline (ClickHouse-compatible) is designed, not built.
7. **Learning persistence has no Alembic migration yet.** Tables are created via `metadata.create_all`
   (SQLite) in the slice/tests; Curriculum Studio has a reviewed, reversible Postgres migration, but
   the `learning` schema does not yet. (Designed to follow the same design→review→build discipline.)
8. **Persistence verified on SQLite for `learning`.** Curriculum Studio's schema is additionally
   verified against real PostgreSQL 16; the `learning` schema is portable-typed but PG-verification is
   pending its migration.

---

## 8. Production risks / blockers (must resolve before scaling)

Ordered by severity. None are architectural — all are build-out or governance items.

1. **[BLOCKER] Governance & safeguarding (child safety).** No child-facing deployment until Phase-1.5
   lands: lawful basis + DPIA (incl. the evidence de-identification spec), data residency, and the
   24/7 safeguarding SLA. The real-time `SafeguardingSignalRaised` path is designed but must be built
   and independently reviewed before any child uses the runtime. *Child safety wins over velocity.*
2. **[HIGH] AI runtime safety at generative tiers.** The templated tier is safe by construction; the
   LLM tiers (4b/4c) introduce hallucination/prompt-injection surface. They must ship with the
   input/output safety layers, the scope-check + fallback-to-approved-content, and an independent red-
   team review before enabling.
3. **[HIGH] Learning persistence hardening.** Author + review a `learning/persistence/` design set and
   Alembic migration (mirroring Phase 3), verify reversibility on real PostgreSQL, add sharding by
   `student_ref`, RLS, and per-student crypto-shred keys before storing real learners.
4. **[HIGH] Session durability.** Move the session saga to a durable store with the resume/abandon
   reconciliation and offline-sync idempotency the design specifies, before real usage on flaky
   networks.
5. **[MED] Event delivery.** Build the outbox relay + read-model projector so cross-context integration
   is event-driven (not a direct DB read), and stand up the analytics warehouse consumer.
6. **[MED] Estimator validation.** The BKT + half-life models use default parameters. Before trusting
   mastery/spacing at scale, run the LEARNING_ANALYTICS validation (does spacing reduce forgetting? do
   thresholds calibrate?) and tune from real data — never assume lab values transfer.
7. **[MED] Scale/perf testing.** Load-test the per-interaction write path and the published-curriculum
   read path against PostgreSQL + cache at target concurrency; confirm the shard-by-`student_ref`
   model holds.
8. **[LOW] Content breadth.** The slice proves the machinery on one lesson; authoring the curriculum
   and exercising prerequisites/diagnostics/spacing at breadth is future phase work.

---

## 9. Recommendations before scaling

1. **Keep the design→review→build discipline.** It caught the cold-start Critical gap in Phase 4
   review; apply it to the learning persistence + session-durability build-outs.
2. **Build the governance-safe slices first.** The pure `decision`/`estimator`/`forgetting` core and
   the persistence are child-data-free and can harden now, behind the governance gate, exactly as this
   slice demonstrates.
3. **Wire events end-to-end early.** The outbox is already written on both sides; standing up the
   relay, projector, and warehouse consumer next makes the whole platform observable and decoupled
   before breadth is added.
4. **Validate the pedagogy with data, not faith.** Ship the LEARNING_ANALYTICS metrics that confirm
   spacing, remediation, and mastery thresholds actually work for Urdu-medium KG–10 learners; treat the
   estimators as replaceable (the ports already allow it).
5. **Do not enable generative AI tiers to children** until the safety layers + independent review are
   complete. The templated tier is enough to prove and even pilot the flow safely.

---

## 10. Verdict

Phase 4.1 is **complete and verified**. Every required step of the end-to-end flow is demonstrated by
the execution trace; every quality gate (tests, coverage, lint, format, strict types, OpenAPI, docs)
is green; the implementation uses the real architecture with no mocks or placeholders. The remaining
work is **build-out and governance**, not redesign — the architecture held.

**Stop point:** Phase 4.1 only. No Phase 5, no Student/Parent/Mentor portals, no additional lessons or
grades were built, per the stop condition.
