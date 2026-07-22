# Pilot Readiness Review — Pilot 0

Status: **Phase 10 — Pilot Validation.** A rigorous readiness review of the **completed platform**
against the requirements for **Pilot 0** (internal end-to-end dry run — **no children**, per
[PILOT_PLAN.md](PILOT_PLAN.md)). **No new features, no redesign, no new domain models** — this is a
validation of what exists. Companions: [PILOT_RISK_REGISTER.md](PILOT_RISK_REGISTER.md),
[GO_NO_GO_DECISION.md](GO_NO_GO_DECISION.md), [POST_PILOT_BACKLOG.md](POST_PILOT_BACKLOG.md).

> **Scope reminder.** Pilot 0 is **internal, no real children** — it uses synthetic / consenting-adult
> testers and the dev auth stub, and it **drills** the safeguarding runbook. The governance gates that
> block **Pilot 1** (M-Gov consent, child-safe auth; M-Safe live safeguarding) are **not** blockers for
> Pilot 0. Pilot 0 readiness is an **engineering + content + operational-drill** question.

---

## 0. Evidence base (current, measured)

| Signal | Value |
| --- | --- |
| Phases completed (tags) | 10 — `phase-4.1` … `phase-9` |
| Commits | 30 (local; canonical history on this machine) |
| Backend gates | ruff ✅ · black ✅ · mypy `--strict` ✅ |
| Backend tests | **169 passed, 7 skipped** (7 = PostgreSQL-gated); 21 test files |
| Backend coverage | **97%** (4048 statements, 131 missing) |
| Frontend gates | `tsc` ✅ · vitest **78 passed** (19 files) · `next build` ✅ |
| API contracts | 6 OpenAPI specs, all redocly-valid |
| markdownlint | ✅ 0 errors |

All numbers are reproducible via the repo's quality gates. Every claim below cites a test or file.

---

## 1. Per-dimension readiness (WS1)

Legend — **Validated** (engineering complete + tested) · **Pilot-0 activity** (build/deploy/assure step
Pilot 0 will complete) · **Pilot-1 gate** (governance-gated, not needed for Pilot 0).

### 1.1 Architecture — **Validated**

- Clean/DDD bounded contexts (curriculum_studio, learning, sync); pure domain, hexagonal ports;
  reversible Alembic migrations; transactional outbox; append-only evidence; optimistic locking.
- **Evidence:** `test_learning_domain/persistence/api`, `test_studio_*`, `test_schema_parity`,
  `test_hardening_4_2`, `test_ports`; 97% coverage; mypy `--strict` clean.
- **Gap:** durable server-side sessions are in-memory (client-side saga is the durability layer) — a
  known, non-blocking gap (G-D below).

### 1.2 Curriculum — **Validated (system)** / **Pilot-0 activity (content depth + audio)**

- The curriculum **production system** (framework, pipeline over the Curriculum Studio `Workflow`,
  standards, QA) is complete (Phase 7); Grade 4 is spine-complete across all core subjects; the
  fractions lesson (`MATH-G4-FR-01`) is fully authored + publishable in code.
- **Evidence:** `vertical_slice/fractions_lesson.py`, `test_studio_service` (workflow gates),
  `test_offline_packages` (packaging); Phase 7 docs.
- **Gap (Pilot-0 activity):** a **coherent published + packaged content arc** beyond the single lesson,
  and **recorded Urdu audio** (scripts/spec exist; audio not recorded — PRR B4). Audio-first requires
  recorded audio for a real session.

### 1.3 AI Teacher — **Validated**

- Templated, curriculum-grounded, explainable (no LLM, AR-C-06): four explanation styles, adaptive
  plan, guardrails (grounded / non-generative / no-answer / age / confidence / escalation).
- **Evidence:** `test_ai_teacher` (grounding + no-answer + non-generative **invariants**, style policy,
  confidence, adaptive plan, endpoints + IDOR); `ai-teacher.openapi.yaml`.

### 1.4 Offline platform — **Validated**

- Service worker, IndexedDB, download manager, offline lessons/dashboard, local progress + resume,
  cache versioning; **Ed25519-signed** packages with client verification (Python↔WebCrypto interop
  locked); LRU eviction; purge; chaos framework.
- **Evidence:** backend `test_offline_packages`, `test_ed25519`; frontend `signature`,
  `packagesHardening`, `idb`, `cacheVersion`, `chaos` (fake-indexeddb).

### 1.5 Synchronization — **Validated**

- Durable sync consumer: offline `attempt.submitted` → append-only `AssessmentEvidence`, **idempotent**
  (dedupe on `evidence_id` + `client_event_id`); background drain, retry, reconcile, resume, diagnostics.
- **Evidence:** `test_sync_evidence` (duplicate upload, **crash-recovery**, append-only union, summative
  never auto-graded); frontend `syncClient`, `syncCrashRecovery` (120-attempt long session), `reconcile`.
  **Guarantee proven:** no data loss, no double-count — even after a server restart.

### 1.6 Guardian workflows — **Validated (data surfaces)** / **Pilot-1 gate (guardian auth)**

- Every guardian panel maps to an existing derived read model (`today`, `history`, `progress`,
  `recommendations`, `notifications`, sync diagnostics) — designed in Phase 9.
- **Evidence:** `test_student_api` (read models); [GUARDIAN_EXPERIENCE.md](GUARDIAN_EXPERIENCE.md).
- **Gate:** the guardian **role/identity/child-linkage** is M-Gov (a thin layer over the same reads) —
  **not needed for Pilot 0** (no guardians of children in an internal dry run).

### 1.7 Mentor workflows — **Validated (per-learner)** / **Pilot-1 gate (cohort roster)**

- Learner overview, intervention triage (AI plan weak topics), escalation review (`guardrail.escalate`),
  analytics, assessment review (mentor-mediated) — over mentor-privileged reads.
- **Evidence:** `test_ai_teacher` (plan/escalate/IDOR), `test_student_api`, `test_learning_api`;
  [MENTOR_WORKFLOWS.md](MENTOR_WORKFLOWS.md).
- **Gate:** the **cohort roster + assignment + persisted notes** are M-Gov/admin — per-learner data
  exists today.

### 1.8 Pilot operations — **Validated (docs)** / **Pilot-0 activity (execution)**

- Onboarding, device prep, offline deployment, daily runbook, support, incident response, data-
  collection — documented in Phase 9.
- **Evidence:** [PILOT_RUNBOOK.md](PILOT_RUNBOOK.md), [DEVICE_PREPARATION.md](DEVICE_PREPARATION.md),
  [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md).
- **Gap (Pilot-0 activity):** the runbooks must be **executed** — deploy infra + monitoring + backups +
  kill-switch; run the safeguarding drill; provision + verify the pilot device.

---

## 2. End-to-end journey validation (WS2)

The critical learner journey (Guardian → Student → Lesson → Offline study → Assessment → Sync →
Guardian reporting → Mentor intervention). **Expected · Observed · Evidence · Remaining risk.**

| Step | Expected | Observed (implementation) | Evidence | Remaining risk |
| --- | --- | --- | --- | --- |
| Student session start | a learner starts a session | `POST /v1/learning/sessions` works | `test_student_api`, `test_ai_teacher` | child-safe auth is Pilot-1 (dev stub for Pilot 0) |
| Lesson taught | grounded, non-generative explanation + tutoring | AI Teacher `:explain` + session `:teach/:answer/:hint` | `test_ai_teacher` (invariants), `test_learning_*` | needs recorded audio for audio-first (Pilot-0 activity) |
| Offline study | download → verify → render → work offline | signed packages + SW + IndexedDB; offline render | `test_offline_packages`, `test_ed25519`, FE `idb`/`signature` | needs a published+packaged content arc |
| Assessment | formative auto, summative mentor-mediated; no auto-promote | scorer + append-only evidence + `mentor_mediated` | `test_learning_*`, `test_student_api` | none (guarantee holds) |
| Synchronization | attempts sync as durable evidence, idempotent | durable consumer via `/v1/sync/batch` | `test_sync_evidence`, FE `syncCrashRecovery` | none (no loss / no double-count proven) |
| Guardian reporting | timeline + weekly summary + recommendations | derived reads + AI plan | `test_student_api`, `test_ai_teacher` | guardian auth is Pilot-1 |
| Mentor intervention | triage + escalation review + follow-up | AI plan + mentor-privileged reads | `test_ai_teacher`, `test_student_api` | cohort roster is Pilot-1 |
| End-to-end on a device | the whole journey on the pilot device | **not yet run** | — | **this is the Pilot 0 dry run itself** |

**Verdict:** every step is **implemented and unit/integration-tested** at the platform layer; the
**full on-device dry run is Pilot 0's own purpose** and is the one thing not yet executed.

---

## 3. Remaining engineering / content / ops gaps (WS1)

| ID | Gap | Type | Blocks Pilot 0? | Owner |
| --- | --- | --- | --- | --- |
| **G-A** | Urdu audio not recorded (scripts/spec exist) | Content/Media | **Yes** (audio-first) | WS5/content |
| **G-B** | Coherent published + packaged content arc (beyond 1 lesson) | Content pipeline | **Yes** | WS4/content |
| **G-C** | Student-session UI completeness for a full journey (portal is a scaffold; offline lib built + tested) | Frontend | **Yes** (runnable dry run) | Frontend |
| **G-D** | Durable server-side sessions (in-memory; client saga is durability) | Backend | No (offline-lite works) | Backend (WS15/H1) |
| **G-E** | Deployed infra + monitoring + backups/DR + kill-switch | Infra/Ops | **Yes** (Pilot 0 exit) | SRE/Ops |
| **G-F** | Assurance run: a11y audit, security review/pentest, load test, safeguarding drill | Assurance | **Yes** (Pilot 0 exit) | QA/Security/Safeguarding |
| **G-G** | Child-safe auth, guardian/cohort, crisis routing, at-rest prod keys, telemetry | Governance | **No** (Pilot-1 gates) | Governance (M-Gov/M-Safe) |

**Interpretation:** the **hard architectural + algorithmic core is complete, tested (97%), and
validated** (G-D, G-G aside). The Pilot-0 blockers (**G-A, G-B, G-C, G-E, G-F**) are **bounded build +
deploy + assurance activities** — exactly the work Pilot 0 exists to complete and exit on — **not**
missing architecture or unproven design.

---

## 4. Summary

- **Architecture, AI Teacher, offline, and synchronization: VALIDATED** — complete, tested, and proven
  (including the no-data-loss/no-double-count and no-hallucination guarantees).
- **Curriculum system + guardian/mentor/ops experience: VALIDATED as design + engine**; the runnable
  pilot needs **audio, a published content arc, student-session UI, deployed infra, and the assurance
  run** (Pilot-0 activities, G-A/B/C/E/F).
- **Pilot 1 (children): governance-gated** (M-Gov + M-Safe) — out of scope for Pilot 0.

The Go/No-Go recommendation, with conditions, is in [GO_NO_GO_DECISION.md](GO_NO_GO_DECISION.md); risks
in [PILOT_RISK_REGISTER.md](PILOT_RISK_REGISTER.md); the post-pilot backlog in
[POST_PILOT_BACKLOG.md](POST_PILOT_BACKLOG.md).
