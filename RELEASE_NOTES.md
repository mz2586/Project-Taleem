# Release Notes

Human-readable notes per milestone. Newest first. Detailed change lists live in
[CHANGELOG.md](CHANGELOG.md); versions and tags in [VERSION.md](VERSION.md). Maintained locally —
this repository has no remote and the local Git history is authoritative.

---

## 0.11.0 — Phase 11: Pilot 0 Execution Readiness (2026-07-23)

Tag: `phase-11`

Turning the Go/No-Go conditions into an honest, turnkey execution package — and completing the
engineering that code can complete.

### Highlights

- **The assurance pass, automated.** A new repeatable suite proves the platform-level guarantees a pilot
  depends on: authentication + IDOR, **no child PII in any response**, signed offline packages verify,
  a 100-attempt sync batch applies **exactly once with idempotent replay** (no double-count), and the
  AI Teacher stays grounded / non-generative / answer-free (disabled offline).
- **A turnkey pilot package.** Deployment, operator, mentor, guardian, rollback, and support checklists,
  plus a go-live + monitoring + safeguarding-drill operations guide — everything a human team needs to
  run Pilot 0.
- **An honest final verdict: NOT READY to *start* the dry run — but the gap is execution, not
  engineering.** There's no recorded audio, no deployed environment, and the session UI isn't complete;
  the live a11y audit, pentest, and safeguarding drill run during Pilot 0. Three conditions are blocked
  on human/ops work (audio, deploy, drill) and three are partially complete (content, UI, assurance).
  No open Critical risk; Go/No-Go stays GO WITH CONDITIONS.

### Quality

- Backend: 170 passed, 8 skipped at 97% coverage; frontend 78 vitest tests; 6 OpenAPI contracts valid;
  all gates green. See `PHASE_11_REPORT.md` and `FINAL_READINESS_REPORT.md`.

---

## 0.10.0 — Phase 10: Pilot Validation (2026-07-22)

Tag: `phase-10`

The honest verdict on whether Taleem is ready for its first internal dry run — grounded in the real,
measured state of the platform.

### Highlights

- **GO WITH CONDITIONS for Pilot 0.** The engineering core is complete and proven: architecture, the
  AI Teacher, the offline platform, and synchronization are validated, and their hardest guarantees —
  no data loss / no double-count, no hallucination / no answer leak, no child PII — are demonstrated by
  tests and invariants. **No open Critical risk.**
- **The conditions are execution, not architecture.** Pilot 0 runs once six bounded items land: recorded
  Urdu audio, a published content arc, the student-session UI, deployed infra + kill-switch, the
  assurance pass (accessibility / security / load), and a safeguarding drill.
- **Pilot 1 (real children) stays NO-GO** until the governance and safeguarding gates (M-Gov, M-Safe)
  close — unchanged and clearly separated from the Pilot-0 conditions.
- **Everything else is triaged into a post-pilot backlog** (must-have-before-Pilot-1 / should-have /
  future) — a triage of known work, not a new roadmap.

### Evidence

- 10 phases; backend 169 passed / 7 skipped at 97% coverage; frontend 78 vitest tests; 6 OpenAPI
  contracts valid; all gates green. No source code changed. See `PHASE_10_REPORT.md`.

---

## 0.9.0 — Phase 9: Pilot Operations & Guardian Experience (2026-07-22)

Tag: `phase-9`

Everything a supervised pilot needs around the learner — the guardian and mentor experience, the
operational runbooks, and the proof that the whole journey already works.

### Highlights

- **Guardians and mentors, over data that already exists.** Every guardian panel (dashboard, progress
  timeline, weekly summary, recommendations, sync visibility, notifications) and every mentor workflow
  (learner overview, intervention triage, escalation review, assessment review, follow-up) maps to a
  derived read model or AI Teacher output the platform already produces — no new architecture.
- **Ready to run.** Pilot runbook, device preparation, offline deployment, support guide, incident
  response (safety-first), and a data-collection plan — all reusing the signed offline packages,
  durable sync, kill-switch, and safeguarding runbook.
- **Proven end to end.** Guardian → Student → Lesson → Offline study → Assessment → Synchronization →
  Guardian reporting → Mentor intervention — every step mapped to an existing, tested component.
- **Measured honestly.** Seven pilot success metrics from existing data, under one north star: **zero
  unhandled safety incidents.** The only things left before real children are the governance and safety
  gates (M-Gov, M-Safe) and the on-site Pilot 0 dry run — not engineering.

### Quality

- No source code changed. All gates green: ruff/black/mypy(strict); pytest 169 passed / 7 skipped;
  OpenAPI valid; frontend tsc clean, 78 vitest tests, build green; markdownlint clean. See
  `PHASE_9_REPORT.md`.

---

## 0.8.0 — Phase 8: AI Teacher (2026-07-22)

Tag: `phase-8`

Taleem gets its teacher — one that personalizes instruction while staying **safe, curriculum-aligned,
and explainable**, without a single line of generated text.

### Highlights

- **A teacher you can trust because it can't make things up.** The AI Teacher is templated and
  deterministic: every word it says is authored, reviewed lesson content — it *cannot* hallucinate a
  fact or wander off-curriculum. Grounding is structural, and every response self-certifies it
  (grounded / non-generative / never-reveals-the-answer / age-appropriate / confidence).
- **Personalized, still explainable.** Four explanation styles (direct, worked-example-led,
  concrete-to-abstract, question-led), difficulty that adapts to the learner, weak-topic detection, and
  a revision plan — all chosen by transparent rules with a rationale a mentor can read.
- **Honest about what it knows.** A calibrated confidence indicator (low by default) and escalation to
  a human when a learner is repeatedly stuck.
- **Works offline.** Teaching, hints, and corrections run fully offline from the signed package; only
  grading (queued), the plan (cached), and remote escalation (queued) wait for connectivity —
  gracefully, with honest messaging. Generative rephrasing is disabled offline, always.

### Quality

- Backend: 169 passed, 7 skipped; ruff/black/mypy(strict) green; OpenAPI valid. Frontend unchanged:
  tsc clean, 78 vitest tests, build green; markdownlint clean. See `PHASE_8_REPORT.md`.

---

## 0.7.0 — Phase 7: Curriculum Production System + Grade 4 (2026-07-22)

Tag: `phase-7`

Taleem becomes a complete **educational** platform, not just a software one: a system to produce
curriculum at scale, plus the first complete grade.

### Highlights

- **A production system, built on what already exists.** The authoring pipeline
  (Draft → Educational → Quality → Child-Safety → Publication → Offline-Packaging) is the platform's
  existing Curriculum Studio workflow + offline packaging — documented, not rebuilt. A KG–10 framework,
  eight content standards, and six QA validation checklists complete the system.
- **Grade 4, complete.** All six core subjects — Mathematics, Urdu, English, General Science, Social
  Studies, and Islamiat/Ethics (dual track) — authored to the framework: ~123 objectives with units,
  assessments, revision, homework, term projects, misconception libraries, and parent/teacher guides.
- **Safe + original by construction.** Every outcome is our own re-expression (never verbatim
  government text); every lesson is authored-original, child-safe, and Urdu-first. Sensitive subjects
  are kept structural + value-level and routed through subject-expert + child-safety review — nothing
  is fabricated.

### Quality

- No source code changed. All gates green: ruff/black/mypy(strict); pytest 159 passed / 6 skipped;
  OpenAPI valid; frontend tsc clean, 78 vitest tests, build green; markdownlint clean. See
  `PHASE_7_REPORT.md`.

---

## 0.6.4 — Phase 6.2C-1: Offline Engineering Hardening (2026-07-22)

Tag: `phase-6.2C-1`

The gate-free hardening of the offline subsystem — signing, resilience, erasure, and diagnostics —
with **no governance-gated work**.

### Highlights

- **Signed content, verified on the device.** Offline packages are now Ed25519-signed by the server
  and verified by the client before any bytes are trusted — so only approved, unmodified content ever
  renders to a child. A pure-stdlib signer (no new dependency) interoperates with browser WebCrypto,
  proven by a locked cross-language test vector.
- **Erasure reaches the device.** A de-enrolment / consent-withdrawal purge clears a learner's
  on-device data (the mechanism; the trigger stays governance-gated).
- **Resilience you can test.** A reusable chaos / fault-injection framework proves the sync engine
  survives storage faults and flapping networks with no data loss.
- **Smarter storage + visibility.** LRU eviction frees space by dropping only re-downloadable
  content — never the un-synced queue — and diagnostics now count signature/integrity/eviction/purge
  events (still local; nothing is uploaded).
- **Backward compatible.** Unsigned packages still install; older diagnostics hydrate.

### Quality

- Backend: 159 passed, 6 skipped; ruff/black/mypy(strict) green; OpenAPI valid.
- Frontend: `tsc` clean; **78 vitest tests** (incl. Python↔WebCrypto signing interop + chaos);
  `next build` green. See `PHASE_6_2C_1_REPORT.md`.

---

## 0.6.3 — Phase 6.2B: Offline Synchronization Engine (2026-07-22)

Tag: `phase-6.2B`

The other half of offline: what a child does with no network now **syncs safely** when they reconnect.

### Highlights

- **Offline attempts become real evidence.** A queued offline answer is graded server-side and
  recorded as durable `AssessmentEvidence` through the same path a live session uses — reusing the
  existing sync contract, `SyncDelta`, `client_event_id`, and `LearningUnitOfWork`. No new child-data
  table; no domain redesign.
- **Exactly-once, always.** Every attempt carries a client `evidence_id`; the server dedupes on it, so
  reconnect-retries, batch replays, reconcile re-queues, and even a **server restart** all collapse to
  a harmless duplicate. No data loss, no double-count.
- **It resumes itself.** A durable IndexedDB queue survives crashes; on reconnect the app drains
  automatically (Background Sync + online/visibility), retries with jittered backoff, dead-letters the
  truly stuck, reconciles a long offline session, and shows a calm live status.
- **Safety held.** A summative item is never auto-graded by sync (mentor-mediated). No offline auth,
  no consent-gated telemetry — those are later.

### Quality

- Backend: 147 passed, 6 skipped; ruff/black/mypy(strict) green; OpenAPI valid.
- Frontend: `tsc` clean; **52 vitest tests** including crash-recovery and a 120-attempt long offline
  session over fake-indexeddb; `next build` green. See `PHASE_6_2B_REPORT.md`.

---

## 0.6.2 — Phase 6.2A: Offline-Lite (2026-07-22)

Tag: `phase-6.2A`

The first slice of the offline subsystem: a child can open the app, view their dashboard, and load a
downloaded lesson **with no network** — and their progress is saved on-device and resumable.

### Highlights

- **Offline packages.** A published lesson builds into a content-hashed package the app downloads,
  verifies (SHA-256 against the manifest), and caches in IndexedDB. Packages ship the teaching + attempt
  surface but **never answer keys** — a device cannot reveal an answer offline.
- **Offline dashboard + lessons.** A versioned service worker serves the app shell and the student read
  APIs from cache when offline; the download manager renders cached lessons directly.
- **Local progress + resume.** Progress events and session checkpoints persist on-device (IndexedDB), so
  an interrupted lesson resumes where it left off.
- **Automatic cache versioning.** Content changes change the hash, so stale caches are detected and
  refreshed; old shell caches are purged on activate.
- **Honest, safe by design.** No background sync, no offline auth, no on-device grading, no generative
  AI offline, no child PII — only the pseudonymous `student_ref`. Those belong to 6.2B/6.2C.

### Quality

- Backend: 146 passed, 5 skipped; ruff/black/mypy(strict) green; 5 OpenAPI contracts valid.
- Frontend: `tsc` clean; **31 vitest tests** including a fake-indexeddb offline-browser simulation;
  `next build` green. See `PHASE_6_2A_REPORT.md`.

---

## 0.5.5 — Phase 5.5: Student Platform Backend APIs (2026-07-21)

Tag: `phase-5.5`

The backend the approved Student Experience needs — implemented as **derived read models** over data
the learning platform already stores, so **no new child-data tables** were added.

### Highlights

- Eleven student-facing surfaces went live behind the existing auth: the dashboard aggregate
  (`today`), homework, assessments, revision queue, timetable, notifications, achievements, session +
  lesson history, learning recommendations, and graduated `:hint` requests.
- All authenticated, authorized, and **IDOR-guarded** — a learner reaches only their own data; the
  student surface never exposes autonomous promotion/summative grading.
- A full integration test seeds a published lesson, drives a real session to mastery, and exercises
  every endpoint on both SQLite and PostgreSQL.

### Quality

- 142 tests on PostgreSQL, 97% coverage; ruff/black/mypy(strict) green; 4 OpenAPI contracts valid.
  See `PHASE_5_5_REPORT.md`.

### Scope

Governance-safe. No offline subsystem, no production child auth, no new frontend features.

---

## 0.5.0 — Phase 5: Student Experience (2026-07-21)

Complete student-experience design (`docs/12-student-experience/`) plus the governance-safe portal
core scaffold (`apps/web/app/student/*`) — Today, Session, Profile, Progress over the real
`/v1/learning` API with a synthetic learner and dev-stub token. No child identity, PII, or deployment.

---

## 0.4.2 — Phase 4.2: Wire & Harden (2026-07-21)

Tag: `phase-4.2`

Remediation of the CTO readiness review — the foundation is now production-shaped, not just
green-in-isolation.

### Highlights

- **Security closed.** Every Curriculum Studio and Learning route now requires a verified bearer
  token; the actor's role comes from the token, not the request body. Learner data is IDOR-guarded,
  and production refuses to boot with the default JWT secret or no database.
- **Actually wired.** The Learning API is mounted in the running app, and the app persists to
  SQLAlchemy (with a per-request Unit of Work) instead of the old in-memory store.
- **Migrations & CI.** A learning-schema migration was added, both schemas are verified reversible on
  PostgreSQL, and CI now runs migrations + PostgreSQL-gated tests, lints every OpenAPI contract, and
  guards ORM↔migration schema parity.
- **Defects fixed.** The `RECURRED` misconception dead-state, the audit-immutability trigger on the
  wrong partition, and the dormant learning optimistic lock are all fixed. Baseline runtime
  observability (domain metrics + correlation) was added to the contexts.

### Quality

- 140 tests (SQLite + PostgreSQL-gated); 97% coverage; ruff/black/mypy(strict), redocly, migrations
  all green. See `PHASE_4_2_REPORT.md` and `CTO_REVIEW.md`.

### Scope

No new product features, no portal work, no architecture redesign. MEDIUM/LOW review items not
required by a BLOCKER/HIGH fix remain tracked for a later pass.

---

## 0.4.1 — Phase 4.1: First end-to-end Learning vertical slice (2026-07-21)

Tag: `phase-4.1`

This milestone proves the entire platform architecture works together, end to end, on one lesson.

### Highlights

- **A real educational workflow runs start to finish.** An original Grade-4 Mathematics lesson
  ("Introduction to Fractions") is authored, reviewed through five gates, and published by Curriculum
  Studio; the Learning Intelligence Platform then loads a student, decides to teach, delivers the
  lesson via the templated AI Teaching Runtime, scores answers, detects and remediates a
  misconception, advances the learner to mastery, schedules revision, records analytics, and closes
  the session — with a captured execution trace of every step.
- **The learning "brain" is evidence-based and swappable.** Mastery (Bayesian Knowledge Tracing with
  uncertainty), forgetting/spacing (half-life), and the decision policy are pure, deterministic, and
  sit behind ports so the pedagogy can evolve without touching the rest of the system.
- **No mocks.** Curriculum Studio and the Student Knowledge Model persist to real SQLAlchemy stores;
  the AI runtime is the real templated (no-LLM) tier, in-scope by construction.

### Quality

- 124 tests pass / 2 skipped (Postgres-gated); 97% coverage (learning domain ≈98%).
- ruff, black, mypy `--strict`, OpenAPI (redocly, 3 contracts), markdownlint — all green.

### For maintainers

- Run the slice: `cd services/core-api && PYTHONPATH=src python -m taleem_core.vertical_slice.runner`
- Full report with trace, metrics, gaps, and production blockers: `VERTICAL_SLICE_REPORT.md`.

### Not included / blockers before scaling

Governance-safe only (synthetic pseudonymous learner; no real child data). Before any child-facing
use: Phase-1.5 governance and safeguarding, generative-AI-tier safety, the learning-store Alembic
migration and sharding, durable sessions, and the event relay + analytics warehouse. See the report.

---

## 0.3.0 — Phase 3: Curriculum Studio (2026-07-20)

The AI-native curriculum authoring platform: hierarchy, Lesson aggregate, AI teaching objects,
assessments, provenance/original-content enforcement, 5-gate review workflow, 9 quality gates,
immutable versioning, and the authoring API/UI.

## 0.2.0 — Phase 1.5 / 2: Governance tracks + M1 walking skeleton (2026-07-20)

Governance decision tracks and external validation; the M1 hexagonal platform skeleton; full
engineering verification; independent executive review + roadmap; and curriculum resource discovery.

## 0.1.0 — Phase 1: Foundation blueprint (2026-07-19)

The complete 50-document blueprint (product, architecture, security/privacy, design, education,
portals, engineering, delivery) plus ADRs and the external architecture review.
