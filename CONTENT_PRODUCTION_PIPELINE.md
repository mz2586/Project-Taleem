# Content Production Pipeline — Authoring Workflow

Status: **Phase 7 — Curriculum Production System. Documentation of the authoring workflow.** The
pipeline **already exists in code** — this document describes how the existing Curriculum Studio
`Workflow` state machine + the offline packaging pipeline realize the required flow. No architecture
is redesigned; the pipeline is reused as-is.

Required flow: **Draft → Educational Review → Quality Review → Child Safety Review → Publication →
Offline Packaging.**

Companions: [CURRICULUM_FRAMEWORK.md](CURRICULUM_FRAMEWORK.md),
[CONTENT_STANDARDS.md](CONTENT_STANDARDS.md), [QUALITY_ASSURANCE_CHECKLISTS.md](QUALITY_ASSURANCE_CHECKLISTS.md).

---

## 0. The pipeline is the existing `Workflow` state machine

`services/core-api/src/taleem_core/contexts/curriculum_studio/domain/workflow.py` defines an
append-only, illegal-transitions-rejected state machine. Its states map **exactly** onto the required
pipeline:

| Required stage | Workflow state(s) | Responsible role (`STATE_ROLE`) |
| --- | --- | --- |
| **Draft** | `DRAFT` | author (`subject_author`) |
| **Educational Review** | `SUBJECT_EXPERT` → `EDUCATIONAL_QA` | `subject_expert`, then `instructional_designer` |
| **Quality Review** | `ACCESSIBILITY` → `LANGUAGE` | `a11y_specialist`, then `language_editor` |
| **Child Safety Review** | `AI_SAFETY` | `safety_officer` |
| **Publication** | `APPROVED` → `PUBLISHED` | `curriculum_architect` (publish) |
| **Offline Packaging** | (post-publish) | `OfflinePackageService` (Phase 6.2A; Ed25519-signed 6.2C-1) |

`ReviewAction` = `SUBMIT · APPROVE · REQUEST_CHANGES · PUBLISH · ROLLBACK · ARCHIVE`. The service
enforces **no self-approval** (the author cannot approve their own reviews) and the **ordered review
chain** (`REVIEW_CHAIN`). Every transition is recorded as an immutable `TransitionRecord`
(from/to state, action, actor role, note) — a complete, auditable provenance trail.

---

## 1. Stage 1 — Draft

- **Who:** a subject author (`subject_author`).
- **What:** author a `Lesson` (the ten required fields, §Framework §6) as `authored-original` with
  `[RE-EXPRESSED]` outcomes and `aligned_slo_codes` (Provenance). No answer keys will ship to the
  device; grading stays server-side.
- **Entry/exit:** `create()` → `DRAFT`; `submit(subject_author)` → advances to the first review state.
- **Gate:** the author self-checks against [CONTENT_STANDARDS.md](CONTENT_STANDARDS.md) before submit.

## 2. Stage 2 — Educational Review

Two gates, in order:

- **Subject-expert review (`SUBJECT_EXPERT`, role `subject_expert`):** is the content *correct* and
  NCP-aligned? Are worked examples and answer keys right? Is the objective genuinely `[RE-EXPRESSED]`
  (not verbatim SLO text)?
- **Instructional-design review (`EDUCATIONAL_QA`, role `instructional_designer`):** does it *teach*
  before it tests? Is the difficulty progression sound? Are the misconceptions + graduated hints
  pedagogically valid? Is the item pool ≥ 5 distinct per objective?
- **Advance:** `APPROVE` moves to the next state; `REQUEST_CHANGES` returns it to `DRAFT` with a note.

## 3. Stage 3 — Quality Review

Two gates, in order:

- **Accessibility review (`ACCESSIBILITY`, role `a11y_specialist`):** WCAG 2.2 AA — every visual has
  alt-text; audio-first path complete for non-readers; nothing relies on color/sound alone; usable by a
  screen-reader user; mobile-first. **Exception:** where *reading* is the construct (Urdu/English
  comprehension items), the passage carries **no audio scaffolding** (validity).
- **Language review (`LANGUAGE`, role `language_editor`):** Urdu-first correctness in a simple child
  register; accurate English support; math/subject terms consistent; correct RTL + numeral rendering
  (Eastern-Arabic in Urdu-medium, FD-15).
- **Advance:** `APPROVE` / `REQUEST_CHANGES` as above.

## 4. Stage 4 — Child Safety Review

- **Safety review (`AI_SAFETY`, role `safety_officer`) — zero-tolerance gate:** no request for personal
  information; no brands/faces/real people; no frightening/shaming/pressuring language; culturally +
  religiously safe for Pakistani children; the AI teaching object uses **approved content only**
  (templated, no generative LLM to children); escalation-to-human path intact; no dead ends. For
  sensitive subjects (Social Studies, Islamiat/Ethics) this gate is decisive.
- **Advance:** `APPROVE` → `APPROVED`. A single safety failure blocks publication (no waiver).

## 5. Stage 5 — Publication

- **Who:** `curriculum_architect`.
- **What:** `PUBLISH` moves `APPROVED` → `PUBLISHED`, versioned. Only published lessons are visible to
  the learning engine (`CurriculumStudioReadModel` projects **published** lessons into `LessonView`).
- **Rollback:** `ROLLBACK` / `ARCHIVE` are available for post-publication correction.

## 6. Stage 6 — Offline Packaging

- **Who/what:** `OfflinePackageService` (Phase 6.2A) builds a content-hashed, **Ed25519-signed**
  (Phase 6.2C-1) offline package from the published lesson — the child-safe content projection (prompts,
  options, hints; **no answer keys**), plus audio + captions (per the audio guide) and visuals.
- **Delivery:** the client downloads, **verifies the signature + content hash**, and installs
  atomically; the lesson then runs fully offline; attempts sync back as durable evidence (Phase 6.2B).
- **Gate:** a lesson is not "pilot-ready" until its offline package installs + renders offline on a
  low-end device.

---

## 7. End-to-end provenance + auditability

- The `Workflow.history` is an **append-only transition log** — who did what, when, in which role — a
  complete audit trail from Draft to Published for every lesson.
- `Provenance` records `authored-original` + `aligned_slo_codes`.
- Post-publish, `AssessmentEvidence` (append-only) records every learner attempt against the published
  content — the same immutable-evidence discipline end to end.

## 8. What is reused vs what a producer supplies

- **Reused (no change):** the `Workflow` state machine + roles, `CurriculumStudioService` (no
  self-approval, ordered chain), the read-model projection, `OfflinePackageService`, signing, and the
  learning/assessment engine.
- **Supplied per lesson (content):** the authored `Lesson` and the human reviewers who approve each
  gate. The pipeline is the machine; the curriculum is the material fed through it.

## 9. Operating the pipeline for a full grade

To produce a complete grade (e.g. Grade 4, [curriculum/grade-4/GRADE4_PACKAGE.md](curriculum/grade-4/GRADE4_PACKAGE.md)):

1. Author each subject's units/lessons to the framework contract (Draft).
2. Run each lesson through the five review gates in parallel across authors, serial per lesson.
3. Publish approved lessons; build + sign offline packages.
4. Validate the whole grade against [QUALITY_ASSURANCE_CHECKLISTS.md](QUALITY_ASSURANCE_CHECKLISTS.md)
   before the grade is declared production-ready.
