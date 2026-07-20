# Lesson Standard

| | |
|---|---|
| **Status** | Phase 3 · The definition of a complete, publishable lesson · Related: [CURRICULUM_DATA_MODEL](./CURRICULUM_DATA_MODEL.md) · [QUALITY_ASSURANCE_STANDARD](./QUALITY_ASSURANCE_STANDARD.md) |
| **Date** | 2026-07-20 |

## 1. Definition of a complete lesson

A lesson is **not publishable** until every required field is present, valid, aligned to ≥1 public NCP
SLO, provenance-clean (original content), and passing all quality gates. This standard is machine-checked
by the Studio validator.

## 2. Required fields (all must be present)

| Field | Required | Rule |
|---|:--:|---|
| `title`, `description` | ✅ | localized ur+en; title ≤ 80 chars |
| `learning_outcomes` | ✅ | ≥1 SLO ref; each maps to a `standard_code` |
| `prerequisites` | ✅ (may be empty) | must be acyclic vs the objective it targets |
| `estimated_duration_min` | ✅ | 5–40 min (bottom-of-curve attention) |
| `difficulty` | ✅ | one of intro/developing/secure/challenge |
| `keywords`, `vocabulary` | ✅ | vocabulary terms carry pronunciation audio ref |
| `teacher_script` | ✅ | drives AI + human delivery |
| `student_explanation` | ✅ | child-facing, Urdu-first, readability-checked |
| `worked_examples` | ✅ (≥1 for developing+) | step-by-step |
| `visual_concepts` | ✅ (≥1) | SVG/diagram; a11y alt text |
| `interactive_activities` | ✅ (≥1) | see [ASSESSMENT_STANDARD](./ASSESSMENT_STANDARD.md) |
| `practice_questions` | ✅ (≥3) | drawn from the item bank |
| `hints` | ✅ | graduated (nudge → strategy → near-answer), never the answer first |
| `common_misconceptions` | ✅ (≥1) | each with a correction |
| `adaptive_remediation` | ✅ | ≥1 route down the prerequisite DAG |
| `challenge_problems` | secure+ | for extension |
| `homework` | ✅ | offline-completable |
| `assessment` | ✅ | formative + (where summative) mentor-mediated hooks ([58 §5](../05-education/58-mastery-and-assessment-validity.md)) |
| `revision_notes`, `summary` | ✅ | summary ≤ 5 points |
| `parent_notes` | ✅ | plain, in-language, low-literacy-friendly |
| `mentor_notes` | ✅ | what to watch for |
| `accessibility_notes` | ✅ | per [ACCESSIBILITY_STANDARD](./ACCESSIBILITY_STANDARD.md) |
| `offline_package` | ✅ | fits data budget ([04 NFR DATA-02](../01-product/04-non-functional-requirements.md)) |
| `ai_teaching_object` | ✅ | complete per [AI_TEACHING_STANDARD](./AI_TEACHING_STANDARD.md) |
| `provenance` | ✅ | original-content; validated |
| `metadata` | ✅ | grade, subject, language(s), authors |

## 3. Pedagogy requirements

- **One lesson ≈ one small set of SLOs** — do not overload; a lesson is completable in one sitting on a
  low-end device.
- **Mastery-based** — the lesson's practice + assessment produce the mastery signal ([58](../05-education/58-mastery-and-assessment-validity.md)).
- **Scaffolded** — explanation → worked example → guided practice → independent practice → challenge.
- **Misconception-aware** — every lesson names the likely misconceptions and how the AI corrects them.
- **Formative-first** — low-stakes practice with immediate, kind feedback.

## 4. Reach requirements (acceptance criteria)

- **Urdu-first, RTL-complete**, English secondary ([TRANSLATION_STANDARD](./TRANSLATION_STANDARD.md)).
- **Mandatory recorded Urdu audio** for all core-path text ([16](../04-design/16-accessibility-standards.md), audit AR-C-19).
- **Within data budget** in lite mode; offline-completable.
- **WCAG 2.2 AA** ([ACCESSIBILITY_STANDARD](./ACCESSIBILITY_STANDARD.md)).
- **Readability** appropriate to the grade ([CONTENT_STYLE_GUIDE](./CONTENT_STYLE_GUIDE.md)).

## 5. Original-content rule (enforced)

The lesson is **authored original** content aligned to public SLOs. It must **never** reproduce
copyrighted textbook text/images. Provenance validation rejects prohibited sources
([CURRICULUM_ARCHITECTURE §6](./CURRICULUM_ARCHITECTURE.md)).

## 6. Definition of Done (a lesson publishes only when)

- [ ] All required fields present + valid (validator green).
- [ ] ≥1 SLO alignment; prerequisite DAG acyclic.
- [ ] Provenance clean (original / permitted).
- [ ] All 9 quality gates green ([QUALITY_ASSURANCE_STANDARD](./QUALITY_ASSURANCE_STANDARD.md)).
- [ ] Full review chain approved ([AUTHORING_WORKFLOW](./AUTHORING_WORKFLOW.md)).
- [ ] Urdu audio present; a11y + readability pass; offline package within budget.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-20 | Lesson standard: required fields, pedagogy, reach, original-content rule, definition of done. | Curriculum Studio |
