# Phase 8 — AI Teacher Report

Status: **Complete.** The AI Teacher delivers personalized instruction while remaining **safe,
curriculum-aligned, and explainable** — implemented as a **templated, deterministic orchestration**
over the existing platform. **Not a generative model** (audit AR-C-06: no generative AI to children;
offline identical). No architecture redesign; Curriculum Studio, Learning Intelligence, Student
Platform, Assessment Engine, Offline Package System, Learning Unit of Work, and Student Profiles are
all reused. Local commit + `phase-8` tag.

---

## 1. What was built

| Layer | File | Role |
| --- | --- | --- |
| Domain (pure) | `contexts/learning/domain/ai_teacher.py` | explanation styles, grounding self-check, confidence calibration, difficulty mapping, adaptive plan, offline capabilities, escalation |
| Application | `contexts/learning/application/ai_teacher_service.py` | wires the orchestration to SessionService + CurriculumReadModel + KnowledgeService + runtime + graph |
| Adapter (API) | `contexts/learning/adapters/ai_teacher_api.py` | `:explain`, `/ai-teacher/plan`, `/ai-teacher/capabilities` |
| Composition | `main.py` | constructs + mounts the AI Teacher (reusing the same components as SessionService) |
| Contract | `packages/contracts/ai-teacher.openapi.yaml` | OpenAPI (redocly-valid) |
| Docs | `AI_TEACHER_{ARCHITECTURE,INTERACTION_MODEL,SAFETY_MODEL,EVALUATION,OFFLINE}.md` | architecture, interaction, safety, evaluation, offline |

**No schema change, no new child-data table.** Every output is derived + explainable.

---

## 2. The five workstreams

- **WS1 Teaching Engine** — lesson explanation, guided teaching, step-by-step tutoring (reused session
  flow), **four explanation styles** (`direct` / `worked_example_led` / `concrete_to_abstract` /
  `question_led` — deterministic arrangements of authored content), age-appropriate responses by
  `grade_band`.
- **WS2 Adaptive Learning** — weak-topic detection, revision planning (spaced re-checks), personalized
  practice, difficulty adaptation (`recommended_difficulty`), learning recommendations
  (`select_next` + rationale) — via `GET …/ai-teacher/plan`.
- **WS3 Assessment Support** — explain incorrect answers (authored corrections), generate hints
  (authored ladder), recommend remediation (`REMEDIATE`), detect misconceptions (scorer +
  `StudentKnowledge`), encourage mastery (authored affirmations) — reuses the session/answer path.
- **WS4 Guardrails** — curriculum grounding (`is_grounded`), no hallucinated facts (templated →
  impossible), age-appropriate language, safety checks (never reveals the answer; no PII;
  deny-by-default), **confidence indicators** (`confidence_from`), **escalation when uncertain**.
  Every response carries a self-certified **`GuardrailReport`**.
- **WS5 Offline** — the AI Teacher runs **fully offline** (templated + packaged); only grading (queued),
  the plan (cached), and remote escalation (queued) degrade — gracefully, with honest messaging;
  generative rephrasing is `disabled_offline`. See [AI_TEACHER_OFFLINE.md](AI_TEACHER_OFFLINE.md).

---

## 3. Why this is safe + explainable (the design win)

- **Templated, not generative** — the teacher arranges + selects *authored* content; it cannot invent a
  fact or source new curriculum. Grounding is **structural**, verified by `is_grounded` and asserted by
  property tests.
- **Explainable by construction** — every response carries a **rationale** (why this style / next step)
  and a **guardrail report** (grounded / non-generative / in-curriculum / never-reveals-answer /
  age-appropriate / confidence / escalate). A mentor can reconstruct exactly why the teacher acted.
- **Honest confidence + escalation** — confidence is calibrated from the BKT uncertainty (LOW by
  default); the teacher hands off to a human on repeated confusion. It knows when to stop and call a
  person.

---

## 4. Test summary

| Suite | Count | Covers |
| --- | --- | --- |
| Backend `tests/test_ai_teacher.py` | 10 unit + 1 integration (SQLite) (+1 PG-gated) | style arrangements + grounding (no hallucination), no-answer invariant, style policy, confidence calibration, difficulty mapping, adaptive plan (weak topics), offline capability matrix; endpoints (`:explain` styled/grounded/non-generative, `plan`, `capabilities`) + auth + IDOR + 404 |
| Full backend suite | **169 passed, 7 skipped** (7 = PostgreSQL-gated) | no regressions |

Because the teacher is deterministic, the safety-critical behaviours (grounding, no-answer,
non-generative) are asserted as **invariants** (proofs), not sampled.

---

## 5. Quality gate summary

| Gate | Result |
| --- | --- |
| Ruff | ✅ All checks passed |
| Black (`--check`) | ✅ unchanged |
| mypy `--strict` | ✅ no issues (96 source files) |
| pytest | ✅ 169 passed, 7 skipped |
| OpenAPI (redocly 1.25.11) | ✅ all contracts valid (new `ai-teacher.openapi.yaml`) |
| Frontend typecheck (`tsc --noEmit`) | ✅ clean (frontend unchanged) |
| Frontend tests (`vitest run`) | ✅ 78 passed |
| Frontend build (`next build`) | ✅ compiled |
| markdownlint (Phase 8 docs) | ✅ 0 errors |

---

## 6. Files

- **Created (11):** `contexts/learning/domain/ai_teacher.py`, `application/ai_teacher_service.py`,
  `adapters/ai_teacher_api.py`, `tests/test_ai_teacher.py`, `packages/contracts/ai-teacher.openapi.yaml`,
  and the five `AI_TEACHER_*.md` docs + `PHASE_8_REPORT.md`.
- **Modified (4):** `main.py` (wiring + tag), `VERSION.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`.

---

## 7. What comes next (not Phase 8)

- A generative *rephrasing* tier behind the existing `LLMGateway` port — **gated, off for children,
  off offline**; would rephrase already-grounded content and be re-checked by the guardrail. Requires
  independent safety review before any non-child use.
- Front-end surfacing of the `:explain` styles + confidence in the Student Portal (a UI follow-up).
- Field calibration of confidence + style policy against pilot outcome data.

The AI Teacher is a **small, deterministic, grounded, honest** teacher — the safe, sufficient,
explainable instructor for the pilot, built entirely within the existing architecture.
