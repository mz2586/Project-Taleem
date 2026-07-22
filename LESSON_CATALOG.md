# Lesson Catalog — Grade 4 Mathematics Pilot

Status: **Content manifest. Plan only — no code.** Machine-facing index of every lesson in
[GRADE4_MATH_CURRICULUM.md](GRADE4_MATH_CURRICULUM.md), for content-authoring tracking and for wiring
into the existing platform's `Lesson` / `LessonView` model **without changing that model**.

Field meanings map to the live content model
(`services/core-api/src/taleem_core/contexts/curriculum_studio/domain/lesson.py` and
`.../contexts/learning/domain/curriculum_view.py`): `lesson_id` → `Lesson.lesson_id`; `objective` →
`aligned_slo_codes` / `objective_code`; `difficulty` → `Difficulty`; `duration` →
`estimated_duration_min`; `offline_pkg` → `Lesson.offline_package`.

Legend — Difficulty: `INTRO` / `CORE` / `STRETCH`. Comp (competency): `K` knowledge, `C`
comprehension, `A` application. Items = distinct practice/assessment item-pool size (≥ 5 for mastery).
Audio: `UR+EN` = Urdu-first narration with English support. All content is `authored-original`.

---

## 1. Teaching lessons

| lesson_id | Unit | Objective | Title (UR / EN) | Diff | Comp | Dur (min) | Prereqs | Items | HW | Audio | offline_pkg |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `L-math-g4-nb-read-write` | U1 | MATH-G4-NB-01 | اعداد پڑھنا لکھنا / Read & write numbers | INTRO | A | 18 | — | 5 | 1 | UR+EN | `pkg/math-g4-nb-read-write` |
| `L-math-g4-nb-place-value` | U1 | MATH-G4-NB-02 | جگہ کی قیمت / Place value | CORE | C | 20 | NB-01 | 6 | 1 | UR+EN | `pkg/math-g4-nb-place-value` |
| `L-math-g4-nb-compare` | U1 | MATH-G4-NB-03 | موازنہ و ترتیب / Compare & order | CORE | A | 18 | NB-02 | 6 | 1 | UR+EN | `pkg/math-g4-nb-compare` |
| `L-math-g4-nb-round` | U1 | MATH-G4-NB-04 | گول کرنا / Rounding | CORE | A | 18 | NB-03 | 6 | 1 | UR+EN | `pkg/math-g4-nb-round` |
| `L-math-g4-as-add` | U2 | MATH-G4-AS-01 | جوڑ / Addition with carrying | CORE | A | 20 | NB-02 | 6 | 1 | UR+EN | `pkg/math-g4-as-add` |
| `L-math-g4-as-subtract` | U2 | MATH-G4-AS-02 | تفریق / Subtraction with borrowing | CORE | A | 22 | AS-01 | 6 | 1 | UR+EN | `pkg/math-g4-as-subtract` |
| `L-math-g4-as-word` | U2 | MATH-G4-AS-03 | لفظی مسائل / Add-subtract word problems | CORE | A | 22 | AS-01, AS-02 | 6 | 1 | UR+EN | `pkg/math-g4-as-word` |
| `L-math-g4-as-estimate` | U2 | MATH-G4-AS-04 | اندازہ و جانچ / Estimation & checking | STRETCH | A | 18 | NB-04, AS-03 | 6 | 1 | UR+EN | `pkg/math-g4-as-estimate` |
| `L-math-g4-ml-facts` | U3 | MATH-G4-ML-01 | ضرب کے حقائق / Facts & patterns | INTRO | C | 20 | AS-01 | 6 | 1 | UR+EN | `pkg/math-g4-ml-facts` |
| `L-math-g4-ml-2x1` | U3 | MATH-G4-ML-02 | دو ہندسی × ایک / 2-digit × 1-digit | CORE | A | 20 | ML-01 | 6 | 1 | UR+EN | `pkg/math-g4-ml-2x1` |
| `L-math-g4-ml-3x1-2x2` | U3 | MATH-G4-ML-03 | بڑی ضرب / 3×1 & 2×2 digit | STRETCH | A | 24 | ML-02 | 6 | 1 | UR+EN | `pkg/math-g4-ml-3x1-2x2` |
| `L-math-g4-ml-word` | U3 | MATH-G4-ML-04 | ضرب کے لفظی مسائل / Word problems | CORE | A | 20 | ML-02, ML-03 | 6 | 1 | UR+EN | `pkg/math-g4-ml-word` |
| `L-math-g4-dv-share` | U4 | MATH-G4-DV-01 | تقسیم کا تعارف / Sharing & grouping | INTRO | C | 20 | ML-01 | 6 | 1 | UR+EN | `pkg/math-g4-dv-share` |
| `L-math-g4-dv-remainder` | U4 | MATH-G4-DV-02 | باقی / Facts & remainders | CORE | A | 20 | DV-01 | 6 | 1 | UR+EN | `pkg/math-g4-dv-remainder` |
| `L-math-g4-dv-long` | U4 | MATH-G4-DV-03 | لمبی تقسیم / 2–3 digit ÷ 1-digit | STRETCH | A | 24 | DV-02 | 6 | 1 | UR+EN | `pkg/math-g4-dv-long` |
| `L-math-g4-dv-word` | U4 | MATH-G4-DV-04 | تقسیم کے لفظی مسائل / Word problems | CORE | A | 20 | DV-03 | 6 | 1 | UR+EN | `pkg/math-g4-dv-word` |
| `L-math-g4-intro-fractions` | U5 | MATH-G4-FR-01 | کسر کا تعارف / Introduction to fractions **(LIVE)** | INTRO | A | 20 | — | 5 | 1 | UR+EN | `pkg/math-g4-intro-fractions` |
| `L-math-g4-fr-parts` | U5 | MATH-G4-FR-02 | حصے / Numerator & denominator | CORE | C | 18 | FR-01 | 6 | 1 | UR+EN | `pkg/math-g4-fr-parts` |
| `L-math-g4-fr-equivalent` | U5 | MATH-G4-FR-03 | مساوی کسر / Equivalent fractions | STRETCH | A | 20 | FR-02 | 6 | 1 | UR+EN | `pkg/math-g4-fr-equivalent` |
| `L-math-g4-fr-compare` | U5 | MATH-G4-FR-04 | کسروں کا موازنہ / Comparing fractions | CORE | A | 18 | FR-02 | 6 | 1 | UR+EN | `pkg/math-g4-fr-compare` |
| `L-math-g4-fr-addsub` | U5 | MATH-G4-FR-05 | یکساں کسر جوڑ تفریق / Add & subtract like | STRETCH | A | 20 | FR-02, FR-04 | 6 | 1 | UR+EN | `pkg/math-g4-fr-addsub` |
| `L-math-g4-me-length` | U6 | MATH-G4-ME-01 | لمبائی / Length (m, cm) | CORE | A | 20 | ML-01 | 6 | 1 | UR+EN | `pkg/math-g4-me-length` |
| `L-math-g4-me-mass` | U6 | MATH-G4-ME-02 | وزن / Mass (kg, g) | CORE | A | 18 | ME-01 | 6 | 1 | UR+EN | `pkg/math-g4-me-mass` |
| `L-math-g4-me-capacity` | U6 | MATH-G4-ME-03 | گنجائش / Capacity (l, ml) | CORE | A | 18 | ME-02 | 6 | 1 | UR+EN | `pkg/math-g4-me-capacity` |
| `L-math-g4-me-time` | U6 | MATH-G4-ME-04 | وقت / Time & calendar | CORE | A | 22 | — | 6 | 1 | UR+EN | `pkg/math-g4-me-time` |
| `L-math-g4-ge-lines` | U7 | MATH-G4-GE-01 | خطوط / Lines, rays, segments | INTRO | K | 16 | — | 6 | 1 | UR+EN | `pkg/math-g4-ge-lines` |
| `L-math-g4-ge-angles` | U7 | MATH-G4-GE-02 | زاویے / Angles | CORE | C | 18 | GE-01 | 6 | 1 | UR+EN | `pkg/math-g4-ge-angles` |
| `L-math-g4-ge-shapes` | U7 | MATH-G4-GE-03 | دو ابعادی اشکال / 2D shapes | INTRO | K | 18 | GE-01 | 6 | 1 | UR+EN | `pkg/math-g4-ge-shapes` |
| `L-math-g4-ge-symmetry` | U7 | MATH-G4-GE-04 | تناسب / Symmetry | CORE | C | 18 | GE-03 | 6 | 1 | UR+EN | `pkg/math-g4-ge-symmetry` |
| `L-math-g4-da-pictograph` | U8 | MATH-G4-DA-01 | تصویری خاکہ / Pictographs | INTRO | C | 18 | ML-01 | 6 | 1 | UR+EN | `pkg/math-g4-da-pictograph` |
| `L-math-g4-da-bargraph` | U8 | MATH-G4-DA-02 | سلاخی خاکہ / Bar graphs | CORE | A | 20 | DA-01 | 6 | 1 | UR+EN | `pkg/math-g4-da-bargraph` |

## 2. Revision lessons

| lesson_id | Unit | Pulls from | Items | Dur (min) | offline_pkg |
| --- | --- | --- | --- | --- | --- |
| `R-math-g4-u1` | U1 | NB-01…04 | 8 | 15 | `pkg/math-g4-r-u1` |
| `R-math-g4-u2` | U2 | AS-01…04 | 8 | 15 | `pkg/math-g4-r-u2` |
| `R-math-g4-u3` | U3 | ML-01…04 | 8 | 15 | `pkg/math-g4-r-u3` |
| `R-math-g4-u4` | U4 | DV-01…04 | 8 | 15 | `pkg/math-g4-r-u4` |
| `R-math-g4-u5` | U5 | FR-01…05 | 8 | 15 | `pkg/math-g4-r-u5` |
| `R-math-g4-u6` | U6 | ME-01…04 | 8 | 15 | `pkg/math-g4-r-u6` |
| `R-math-g4-u7` | U7 | GE-01…04 | 8 | 15 | `pkg/math-g4-r-u7` |
| `R-math-g4-u8` | U8 | DA-01…02 | 8 | 15 | `pkg/math-g4-r-u8` |

## 3. Summative

| lesson_id | Scope | Grading | offline_pkg |
| --- | --- | --- | --- |
| `S-math-g4-pilot` | all objectives (mixed) | **mentor-mediated** (`summative_mentor_mediated = true`) | `pkg/math-g4-summative` |

## 4. Objective → mastery quick reference

Mastery (default, per [GRADE4_MATH_CURRICULUM.md](GRADE4_MATH_CURRICULUM.md) §3): confirmed at
**≥ 4 of last 5 distinct** items from a **≥ 5-item pool**; spaced re-check on the forgetting schedule;
promotion mentor-mediated, never automatic.

| Objective | Depends on | Primary misconception ref | Revision trigger |
| --- | --- | --- | --- |
| MATH-G4-NB-01 | — | `m-place-value-digit-equals-value` | later NB number-reading miss |
| MATH-G4-NB-02 | NB-01 | `m-place-value-digit-equals-value` | compare/round miss |
| MATH-G4-NB-03 | NB-02 | `m-bigger-number-more-digits-always` | rounding miss |
| MATH-G4-NB-04 | NB-03 | (round-wrong-place, local) | estimation miss (AS-04) |
| MATH-G4-AS-01 | NB-02 | `m-carry-forgotten` | AS-03 miss |
| MATH-G4-AS-02 | AS-01 | `m-borrow-forgotten` | AS-03 miss |
| MATH-G4-AS-03 | AS-01, AS-02 | (keyword-only, local) | AS-04 |
| MATH-G4-AS-04 | NB-04, AS-03 | round-wrong-way | later word-problem checks |
| MATH-G4-ML-01 | AS-01 | `m-mult-add-instead` | ML-02…04, DV, ME |
| MATH-G4-ML-02 | ML-01 | `m-carry-forgotten` | ML-03 |
| MATH-G4-ML-03 | ML-02 | placeholder-zero | ML-04 |
| MATH-G4-ML-04 | ML-02, ML-03 | `m-mult-add-instead` | DV word problems |
| MATH-G4-DV-01 | ML-01 | `m-div-bigger-answer` | DV-02…04 |
| MATH-G4-DV-02 | DV-01 | `m-remainder-dropped` | DV-03 |
| MATH-G4-DV-03 | DV-02 | `m-remainder-dropped` | DV-04 |
| MATH-G4-DV-04 | DV-03 | `m-div-bigger-answer`, `m-remainder-dropped` | summative |
| MATH-G4-FR-01 (live) | — | `m-bigger-denominator-is-bigger` | FR-02…05 |
| MATH-G4-FR-02 | FR-01 | (unequal-parts, local) | FR-03 |
| MATH-G4-FR-03 | FR-02 | `m-equivalent-only-numerator` | FR-05 |
| MATH-G4-FR-04 | FR-02 | `m-bigger-denominator-is-bigger` | FR-05 |
| MATH-G4-FR-05 | FR-02, FR-04 | `m-fraction-add-denominators` | summative |
| MATH-G4-ME-01 | ML-01 | `m-unit-mix` | ME-02…03 |
| MATH-G4-ME-02 | ME-01 | `m-unit-mix` | ME-03 |
| MATH-G4-ME-03 | ME-02 | `m-unit-mix` | summative |
| MATH-G4-ME-04 | — | `m-clock-hour-hand` | summative |
| MATH-G4-GE-01 | — | (ray-segment, local) | GE-02 |
| MATH-G4-GE-02 | GE-01 | `m-right-angle-size` | summative |
| MATH-G4-GE-03 | GE-01 | (square-rectangle, local) | GE-04 |
| MATH-G4-GE-04 | GE-03 | `m-symmetry-any-line` | summative |
| MATH-G4-DA-01 | ML-01 | `m-graph-scale-ignored` | DA-02 |
| MATH-G4-DA-02 | DA-01 | `m-graph-scale-ignored` | summative |

## 5. Totals

| Metric | Count |
| --- | --- |
| Objectives | 31 |
| Teaching lessons | 31 (1 live: FR-01) |
| Revision lessons | 8 |
| Summative | 1 (mentor-mediated) |
| Offline packages | 40 (31 teaching + 8 revision + 1 summative) |
| Distinct item pools | 31 (+ 8 revision + 1 summative) |
