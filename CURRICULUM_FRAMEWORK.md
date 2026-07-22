# Curriculum Framework — Production Framework (KG–10)

Status: **Phase 7 — Curriculum Production System. Documentation of the production framework.** Defines
how a complete KG–10 curriculum is structured and produced on the **existing** platform — no
architecture is redesigned. Reuses the Curriculum Studio authoring model, the Learning Intelligence
engine, the offline packaging pipeline, and the student/guardian/assessment surfaces already built.

Companions: [CONTENT_PRODUCTION_PIPELINE.md](CONTENT_PRODUCTION_PIPELINE.md) (WS2 authoring workflow),
[CONTENT_STANDARDS.md](CONTENT_STANDARDS.md) (WS3 standards),
[QUALITY_ASSURANCE_CHECKLISTS.md](QUALITY_ASSURANCE_CHECKLISTS.md) (WS5 QA), and the Grade 4 package
under [curriculum/grade-4/GRADE4_PACKAGE.md](curriculum/grade-4/GRADE4_PACKAGE.md) (WS4).

---

## 0. Grounding — reuse, do not redesign

This framework maps 1:1 onto components that already exist:

| Framework concept | Existing platform component (reused) |
| --- | --- |
| Subject → Unit → Lesson → Objective → Item | `contexts/curriculum_studio` domain (`Lesson`, `AssessmentBlueprint`, `Provenance`) |
| Authoring + review + publish | `contexts/curriculum_studio` `Workflow` state machine + `CurriculumStudioService` |
| Objective mastery, spacing, revision | `contexts/learning` (BKT, half-life forgetting, decision engine) |
| Assessment scoring + evidence | `contexts/learning` scorer + `AssessmentEvidence` (append-only) |
| Offline delivery | `OfflinePackageService` (Phase 6.2A, Ed25519-signed 6.2C-1) |
| Student / guardian / mentor surfaces | Student Portal + derived read models (Phase 5/5.5) |
| NCP alignment + copyright discipline | `curriculum-research/02_MASTER_CURRICULUM_MATRIX.md` |

The framework is a **specification**; the platform is the **engine**. Nothing here adds a new
subsystem.

---

## 1. Copyright + authenticity discipline (applies to every grade + subject)

Per `curriculum-research/02_MASTER_CURRICULUM_MATRIX.md` §"Copyright & authenticity notice":

- **Verified structure** — the real NCP/SNC subject roster and the real hierarchy (Standard →
  Benchmark → SLO) are used as the skeleton.
- **`[RE-EXPRESSED]` outcomes** — every learning outcome is our own independent re-expression of the
  *kind* of outcome the NCP Progression Grid contains, **never verbatim government SLO text**
  (copyright-reserved). Authoritative SLO population happens later under an NCC/MoFEPT MoU via the
  ingestion pipeline.
- **`authored-original` content** — every lesson, worked example, item, and script is written fresh
  for Taleem (like `vertical_slice/fractions_lesson.py`); `Provenance` records `authored-original` +
  `aligned_slo_codes`.
- **No verbatim third-party content** — no textbook copying; licensing/originality is a QA gate
  ([QUALITY_ASSURANCE_CHECKLISTS.md](QUALITY_ASSURANCE_CHECKLISTS.md) §6).

---

## 2. KG–10 structure (the production skeleton)

### 2.1 Grade bands + subject roster (NCP-verified)

| Grade band | Core subjects |
| --- | --- |
| **KG / Pre-I (ECE)** | Integrated ECE: emergent literacy (Urdu/English readiness), emergent numeracy, world-around-us, socio-emotional, motor, moral foundation |
| **Grades 1–3 (Early Primary)** | Urdu · English · Mathematics · General Knowledge · Islamiat/Ethics (from Gr 3) |
| **Grades 4–5 (Primary)** | Urdu · English · Mathematics · General Science · Social Studies · Islamiat/Ethics |
| **Grades 6–8 (Middle)** | Urdu · English · Mathematics · General Science · Social Studies · Islamiat/Ethics · Computer Science |
| **Grades 9–10 (SSC)** | Urdu · English · Mathematics · Physics · Chemistry · Biology (or CS stream) · Pakistan Studies · Islamiat/Ethics |

Religious education is a **student-attribute track**: Islamiat (Muslim) ↔ Ethics/Akhlaqiat
(non-Muslim), selected per learner — never mixed, never assumed.

### 2.2 The content hierarchy

```text
Grade → Subject → Academic-year plan → Unit → Lesson → Learning objective (SLO) → Item(s)
                                                     ↘ Revision  ↘ Homework  ↘ Project
```

Every level maps to an engine entity (§0). The **objective (SLO)** is the atomic, gradable, mastery-
tracked unit — the north-star currency.

---

## 3. Subject structure

Each subject is organized into **domains** (NCP Standards) → **units** → **lessons/objectives**.

- **Domains** are the stable NCP strands for the subject (e.g. Mathematics: Numbers, Operations,
  Fractions, Measurement, Geometry, Data).
- **Objective code scheme:** `SUBJ-G<grade>-<DOMAIN>-NN` (e.g. `MATH-G4-FR-01`, `SCI-G4-LIV-02`).
  Consistent with the live `MATH-G4-FR-01`.
- **Language subjects (Urdu, English)** carry a **construct-validity rule**: when *reading* is the
  construct being assessed, the passage gets **no audio scaffolding** (validity, master matrix §4.2) —
  audio-first applies everywhere else. This is a per-item property, not a per-subject one.

---

## 4. Academic year structure

- **Year plan per subject:** an ordered sequence of units sized to a school year, with explicit
  prerequisites so the decision engine sequences correctly (prereq DAG).
- **Terms/checkpoints:** the year divides into terms; each term ends with a **revision checkpoint** and
  a **term review** (formative for the learner; mentor-mediated for any summative identity).
- **Pacing:** lessons are short (15–25 min, child attention band); a unit is a coherent multi-lesson
  arc; the year is a coherent progression across units.
- **Cross-subject coherence:** where subjects reinforce each other (e.g. Math measurement ↔ Science
  inquiry; Urdu/English literacy ↔ every subject's reading load), the year plan notes the linkage so
  content is mutually supportive, not contradictory.

---

## 5. Units

A **unit** is a themed group of lessons/objectives with:

- a **unit outcome** (`[RE-EXPRESSED]`) summarizing what the learner can do;
- an **ordered lesson list** with per-lesson prerequisites;
- a **revision lesson** (`R#`) closing the unit with a mixed formative checkpoint;
- **mastery criteria** inherited from the objectives it contains.

Units are sized so a learner completes one in roughly a week of short sessions.

---

## 6. Lessons

Every lesson specifies the **ten required fields** (the production contract, proven by the Grade 4
Mathematics curriculum):

- **Learning outcome** (`[RE-EXPRESSED]`) · **Difficulty** (`INTRO`/`CORE`/`STRETCH`) · **Estimated
  duration** · **Prerequisites** · **Vocabulary** · **Examples** · **Worked examples** · **Practice**
  · **Assessment** · **Revision triggers.**

Plus: teaching script (Urdu-first, English support), activities, **misconceptions** (ref + detector +
correction), a **graduated hint ladder** (H1 orient → H2 strategy → H3 worked re-teach → mentor),
**homework**, and parent/teacher notes. This is exactly the shape of `Lesson` / `LessonView` /
`ItemView` — no new fields.

---

## 7. Learning objectives (SLOs)

- Each objective is `[RE-EXPRESSED]`, tagged with a competency class (Knowledge / Comprehension /
  Application / Analysis), and carries **mastery criteria**: confirmed at **≥ 4 of the last 5**
  distinct items from a **≥ 5-item pool**; spaced re-check on the forgetting schedule; **promotion is
  human-mediated, never automatic** (a platform non-negotiable).
- Objectives declare prerequisites (the sequencing DAG) and revision triggers.

---

## 8. Assessments

Aligned to `docs/05-education/58-mastery-and-assessment-validity.md`:

| Competency class | Item types | Grading | Summative identity |
| --- | --- | --- | --- |
| Knowledge / Comprehension | MCQ, true/false, match, label | auto | formative, device-ok |
| Application | numeric, structured, interactive | auto where deterministic | formative, device-ok |
| Analysis / constructed | short explanation, "show your working" | AI-assisted → **human** | **mentor-mediated** |

- **Formative** assessment is continuous (every practice item is evidence).
- **Summative** identity is always **mentor-mediated** — the platform never auto-promotes a child.
- **No answer keys ship to the device** (offline packages carry prompts/options/hints only; grading is
  server-side — Phase 6.2A/6.2B).

---

## 9. Revision

- **Within a unit:** a revision lesson summarizes key ideas + a mixed formative checkpoint from the
  unit's item pools.
- **Across the year:** confirmed-mastered objectives re-surface on the engine's forgetting schedule
  (spaced re-check) with **distinct** re-check items (no item repeats within a check).
- **Revision triggers** (per objective): a failed spaced re-check; a wrong answer on a later lesson
  whose prerequisite is this objective; a detected misconception; a mentor flag.

---

## 10. Homework

- **One short, everyday task per lesson**, tied to the objective and doable without special resources
  (the Grade 4 Math pattern — e.g. "read the house numbers aloud", "share rotis equally").
- Homework is **encouraged, not graded harshly**; it generates the same append-only evidence when the
  learner completes it in-app.

---

## 11. Projects

- A **project** is a small, multi-lesson, applied task at the end of a unit or term that integrates
  several objectives (and, where natural, more than one subject).
- Projects are **age-appropriate, resource-light, and safe** — no personal-data collection, no
  outside-contact requirement, no cost barrier.
- Projects are **mentor-guided and mentor-assessed** (constructed work → human review), never
  auto-graded.
- Each project specifies: objectives integrated, steps, expected artifact, mentor rubric, estimated
  effort, and a home-safe materials list.

---

## 12. What the framework guarantees (and delegates)

- **Guarantees:** a consistent, NCP-aligned, mastery-tracked, offline-deliverable, child-safe
  structure across every grade and subject — one production contract.
- **Delegates to the pipeline** ([CONTENT_PRODUCTION_PIPELINE.md](CONTENT_PRODUCTION_PIPELINE.md)): how
  each lesson moves Draft → reviews → Publish → offline package.
- **Delegates to standards** ([CONTENT_STANDARDS.md](CONTENT_STANDARDS.md)): what "good" looks like per
  dimension.
- **Delegates to QA** ([QUALITY_ASSURANCE_CHECKLISTS.md](QUALITY_ASSURANCE_CHECKLISTS.md)): the
  pass/fail gates before publish.

The first full application of this framework is the **Grade 4 complete package**
([curriculum/grade-4/GRADE4_PACKAGE.md](curriculum/grade-4/GRADE4_PACKAGE.md)).
