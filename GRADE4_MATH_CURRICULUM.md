# Grade 4 Mathematics — Pilot Curriculum (Urdu-first)

Status: **Content authoring (WS4/WS5). Plan + production-ready scripts only — no code, no backend, no
frontend, no infra.** This is the complete educational content foundation for **Pilot 1** (Grade 4,
Mathematics, one subject, supervised) per [PILOT_PLAN.md](PILOT_PLAN.md) and workstream WS4 of
[MASTER_EXECUTION_PLAN.md](MASTER_EXECUTION_PLAN.md).

Companion documents: [LESSON_CATALOG.md](LESSON_CATALOG.md) (machine-facing manifest),
[AUDIO_SCRIPT_GUIDE.md](AUDIO_SCRIPT_GUIDE.md) (Urdu audio layer), [PARENT_GUIDE.md](PARENT_GUIDE.md),
[TEACHER_GUIDE.md](TEACHER_GUIDE.md), [CONTENT_QA_CHECKLIST.md](CONTENT_QA_CHECKLIST.md).

---

## 0. Authoring discipline (read first)

This curriculum follows the copyright + authenticity discipline established in
`curriculum-research/02_MASTER_CURRICULUM_MATRIX.md`:

- **All learning outcomes here are our own independent re-expression** of the *kind* of outcome the
  National Curriculum of Pakistan (NCP / SNC) Grade 4 Mathematics Progression Grid contains. They are
  **`[RE-EXPRESSED]`**, aligned to NCP domains — **never verbatim government SLO text** (which is
  copyright-reserved). Authoritative SLO population happens later under an NCC/MoFEPT MoU via the
  ingestion pipeline; this pilot content is counsel-reviewable re-expression.
- **All lesson content is `authored-original`** (like the existing
  `services/core-api/src/taleem_core/vertical_slice/fractions_lesson.py`) — not copied from any
  textbook. Every worked example, question, and script below is written fresh for Taleem.
- **This content maps 1:1 onto the existing platform model** — it does **not** change it. Each lesson
  fills the fields of `Lesson` / `AITeachingObject` / `AssessmentBlueprint` (Curriculum Studio) and
  projects into `LessonView` / `ItemView` (learning context). No new schema is introduced.
- **Numerals:** Eastern-Arabic (۰ ۱ ۲ ۳ ۴ ۵ ۶ ۷ ۸ ۹) in Urdu-medium student-facing math text per
  FOUNDER_DECISIONS FD-15; Western numerals in English support and in structural/spec fields.

**Child-safety + inclusion are non-negotiable** (Engineering Constitution, MVP §2): every item is
age-appropriate, culturally safe for Pakistani children, audio-first for non-readers, and free of
brands, people, faces, or anything requiring a child to disclose personal information.

---

## 1. Pilot scope + shape

| Attribute | Value |
| --- | --- |
| Grade | 4 |
| Subject | Mathematics |
| Language | **Urdu-first**; English support shown alongside (bilingual), except where reading is the construct (not the case in math — audio scaffolding is allowed throughout) |
| NCP domains covered | Numbers & Operations; Fractions; Measurement; Geometry; Data Handling |
| Units | 8 teaching units + 8 revision checkpoints + 1 mentor-mediated summative |
| Objectives | 31 (`[RE-EXPRESSED]`, one lesson each) |
| Lessons | 31 teaching lessons + 8 revision lessons + 1 summative (see [LESSON_CATALOG.md](LESSON_CATALOG.md)) |
| Session length | 15–25 min per lesson (child attention band; short by design) |
| Delivery | Mobile-first PWA, audio-first, **offline-compatible** (each lesson packages to `pkg/…`) |
| AI teaching tier | **Templated / approved-content only** (no generative LLM to children in pilot) |

**Learning arc (spine).** The units form one coherent progression — number sense underpins the four
operations, which underpin fractions, which reuse "equal parts"; measurement, geometry, and data
apply that number sense. Prerequisites are explicit per lesson so the decision engine sequences
correctly.

```text
U1 Numbers → U2 Add/Subtract → U3 Multiply → U4 Divide → U5 Fractions
                                                    ↘ U6 Measurement ↘ U7 Geometry ↘ U8 Data
```

---

## 2. Objective (SLO) code scheme

Codes follow the existing pattern (`MATH-G4-FR-01`, used by the live fractions lesson). Domain tags:

| Domain | Tag | Objective range |
| --- | --- | --- |
| Numbers & place value | `NB` | MATH-G4-NB-01 … 04 |
| Addition & subtraction | `AS` | MATH-G4-AS-01 … 04 |
| Multiplication | `ML` | MATH-G4-ML-01 … 04 |
| Division | `DV` | MATH-G4-DV-01 … 04 |
| Fractions | `FR` | MATH-G4-FR-01 … 05 (FR-01 already live) |
| Measurement | `ME` | MATH-G4-ME-01 … 04 |
| Geometry | `GE` | MATH-G4-GE-01 … 04 |
| Data handling | `DA` | MATH-G4-DA-01 … 02 |

Each objective carries: a `[RE-EXPRESSED]` outcome, a competency class, mastery criteria, ≥1 authored
assessment item, and revision triggers (§5–§7).

---

## 3. Competency + mastery model

Aligned to `docs/05-education/58-mastery-and-assessment-validity.md` and the master matrix §5.

| Competency class | Item types | Grading | Summative identity |
| --- | --- | --- | --- |
| Knowledge / Comprehension | MCQ, true/false, match, label | auto | formative, device-ok |
| Application | numeric, structured, interactive drag/select | auto where deterministic | formative, device-ok |
| Analysis / constructed | short explanation, "show your working" | AI-assisted → **human** | **mentor-mediated** at summative |

**Mastery criteria (default per objective).** These feed the BKT mastery + spacing engine already
built; the curriculum only supplies the thresholds and item pools:

- **Confirmed mastery** = the learner answers **≥ 4 of the last 5** distinct items on the objective
  correctly, drawn from an item pool of **≥ 5 distinct items** (no item repeats within a check).
- **Spaced re-check** = after confirmed mastery, the objective re-surfaces on the forgetting schedule
  (the engine's half-life spacing); a failed re-check re-opens the objective.
- **Promotion is never automatic / high-stakes** — the summative is mentor-mediated (MVP §2).
- Deterministic-answer application items are auto-graded; "explain in your own words" items are
  formative-only signals and, at summative, mentor-mediated.

---

## 4. Misconception library (Grade 4 Math)

Every misconception has a stable ref, a detector signal (what the learner does), and an authored
correction. Items encode `option_misconceptions` so a wrong choice raises the matching signal; the
teaching runtime replies with the correction (never the bare answer). This is the same mechanism the
live fractions lesson uses (`m-bigger-denominator-is-bigger`).

| Ref | Misconception | Detector signal | Correction (child-facing, Urdu-first) |
| --- | --- | --- | --- |
| `m-place-value-digit-equals-value` | A digit's value equals the digit, ignoring its column | reads 3 in "356" as three, not three hundred | ہر ہندسے کی جگہ اس کی قیمت بتاتی ہے — "The place of a digit tells its value; the 3 here means three hundred." |
| `m-bigger-number-more-digits-always` | More digits always means bigger (ignoring leading zeros/place) | ranks 099 above 100-family incorrectly | پہلے ہندسوں کی تعداد گنیں، پھر بائیں سے موازنہ کریں — "Compare digit-count first, then left to right." |
| `m-carry-forgotten` | Forgets to carry in column addition | 47+38 → 75 | جب جوڑ ۹ سے بڑا ہو تو اگلی جگہ ایک لے جائیں — "When a column adds past 9, carry one to the next place." |
| `m-borrow-forgotten` | Subtracts smaller-from-larger per column regardless of order | 52−28 → 36 | چھوٹے سے بڑا نہیں گھٹتا؛ اوپر والے سے ادھار لیں — "Borrow from the next column instead of flipping the digits." |
| `m-mult-add-instead` | Adds the two factors instead of multiplying | 6×4 → 10 | ضرب یعنی بار بار جوڑ: ۶ کو ۴ بار — "Multiply = repeated add: six, four times = 24." |
| `m-div-bigger-answer` | Thinks dividing makes the answer bigger | 12÷4 → 48 | تقسیم یعنی برابر بانٹنا؛ نتیجہ چھوٹا ہوتا ہے — "Dividing shares equally; the result is smaller." |
| `m-remainder-dropped` | Ignores the remainder in division | 13÷4 → 3 (drops 1) | جو بچ جائے وہ باقی ہے، اسے لکھیں — "What is left over is the remainder; write it." |
| `m-bigger-denominator-is-bigger` | Bigger bottom number means bigger fraction | picks 1/4 > 1/2 | زیادہ حصے مطلب چھوٹے حصے — "More parts means smaller parts, so 1/4 is smaller than 1/2." *(shared with live FR-01)* |
| `m-fraction-add-denominators` | Adds denominators when adding like fractions | 1/4 + 2/4 → 3/8 | یکساں کسر جوڑیں تو نیچے کا نمبر وہی رہتا ہے — "Add the tops; the bottom stays the same: 3/4." |
| `m-equivalent-only-numerator` | Changes only the top to make equivalents | 1/2 = 2/2 | اوپر اور نیچے دونوں کو ایک ہی عدد سے ضرب دیں — "Multiply top and bottom by the same number." |
| `m-unit-mix` | Mixes units (adds cm to m without converting) | 1 m + 50 cm → 51 | پہلے ایک ہی اکائی بنائیں — "Convert to the same unit first: 1 m = 100 cm." |
| `m-clock-hour-hand` | Reads the hour from the minute hand or vice-versa | 3:15 read as 15 past hour-hand position | چھوٹی سوئی گھنٹے، بڑی سوئی منٹ — "Short hand = hours, long hand = minutes." |
| `m-right-angle-size` | Thinks a bigger drawing means a bigger angle | calls a long-armed acute angle "bigger" | زاویہ کھلاؤ سے ناپتے ہیں، لمبائی سے نہیں — "An angle is the opening, not the arm length." |
| `m-symmetry-any-line` | Any line through a shape is a line of symmetry | draws a diagonal on a rectangle as symmetric | دونوں حصے بالکل برابر جُڑنے چاہییں — "Both halves must match exactly when folded." |
| `m-graph-scale-ignored` | Reads bar height as the count, ignoring the scale | reads a bar at "3 marks" as 3 when scale = 2 each | پہلے پیمانہ دیکھیں: ہر خانہ کتنے کا ہے — "Check the scale: how many each square counts for." |

---

## 5. Hint hierarchy (graduated, never gives the answer)

Every practice/homework item carries a **graduated hint ladder** (the `hints` tuple on `ItemView`).
The teaching runtime follows the live policy: *graduated; two hints surfaced before a worked
re-teach; never reveal the answer first* (matches `AITeachingObject.hint_policy`).

| Level | Purpose | Style | Example (fraction compare) |
| --- | --- | --- | --- |
| **H1 — Orient** | Point to the idea, not the step | a question that reframes | "پیزا کے ٹکڑوں کا سوچیں — Think about pizza slices." |
| **H2 — Strategy** | Name the method to try | one concrete action | "زیادہ ٹکڑے مطلب چھوٹے ٹکڑے — More slices means smaller slices." |
| **H3 — Worked re-teach** | Re-show a parallel worked example, then re-ask | model a *similar* problem, not this one | Work 1/2 vs 1/3 aloud, then return to 1/2 vs 1/4. |
| **Escalate** | Repeated confusion after H3 → **mentor** | hands to a human | Raises `misconception:*` / `repeated-confusion` → mentor queue (WS7). |

**Rules:** never state the correct option before H3; two hints maximum before a worked re-teach; after
a worked re-teach and one more miss, escalate to a mentor (no infinite loops); hints are authored per
item, localized Urdu-first with English support.

---

## 6. Revision + spacing model

- **Within a unit:** each unit ends with a **revision lesson** (`R#`) summarizing key ideas + a mixed
  formative checkpoint drawn from that unit's item pools.
- **Across units:** confirmed-mastered objectives re-surface on the engine's forgetting schedule
  (spaced re-check); the curriculum supplies distinct re-check items so no item repeats.
- **Revision triggers (per objective)** — the curriculum declares when an objective should be pushed
  back into revision. Standard triggers:
  - a failed spaced re-check;
  - a wrong answer on a later lesson whose prerequisite is this objective;
  - a detected misconception ref tied to this objective;
  - mentor flag.

Each lesson below lists its specific **Revision triggers** field.

---

## 7. The units + lessons

Every lesson specifies the **ten required fields** — Learning outcome · Difficulty · Estimated
duration · Prerequisites · Vocabulary · Examples · Worked examples · Practice · Assessment · Revision
triggers — plus teaching script, activities, misconceptions, hint ladder, homework, and parent/teacher
notes. Difficulty uses the existing `Difficulty` enum (`INTRO`, `CORE`, `STRETCH`).

Deeply-authored exemplar lessons (full bilingual scripts + items) are marked **★**; every other
lesson carries the complete field set and its item specification, ready for an author to expand item
wording using the same pattern. Urdu student-facing math uses Eastern-Arabic numerals.

---

### Unit 1 — Numbers up to 100,000 (place value, comparing, rounding)

Objective set: MATH-G4-NB-01 … NB-04. Unit outcome `[RE-EXPRESSED]`: *the learner can read, write,
compare, order, and round whole numbers up to 100,000 using place value.*

#### ★ L1.1 — Reading and writing numbers to 10,000 (MATH-G4-NB-01)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can read aloud and write in figures whole numbers
  up to 10,000, matching words to numerals.
- **Difficulty:** INTRO
- **Estimated duration:** 18 min
- **Prerequisites:** Grade 3 numbers to 1,000 (assumed prior; not a pilot objective)
- **Vocabulary:** ہندسہ (digit), عدد (number), ہزار (thousand), سو (hundred), دہائی (ten), اکائی (one)
- **Examples:** ۳۴۵۶ read as "تین ہزار چار سو چھپن / three thousand four hundred fifty-six".
- **Worked example (script):**
  - "ہم عدد کو دائیں سے پڑھتے ہیں: اکائی، دہائی، سو، ہزار۔"
  - "۲۰۰۵ میں: ۵ اکائیاں، ۰ دہائی، ۰ سو، ۲ ہزار — دو ہزار پانچ۔"
  - "We read from the right: ones, tens, hundreds, thousands. 2005 is two thousand and five."
- **Practice (5 items, MCQ + type-the-number):** match words↔figures for ۳۴۵۶, ۲۰۰۵, ۹۹۹۹, ۱۰۰۰,
  and a "which is 'four thousand and twenty'" selector. Auto-graded (Application).
- **Assessment (formative):** 5-item pool; confirmed mastery ≥ 4/5 distinct.
- **Revision triggers:** wrong on any later NB lesson's number-reading step; `m-place-value-digit-equals-value`.
- **Misconceptions:** `m-place-value-digit-equals-value`.
- **Hint ladder:** H1 "دائیں سے شروع کریں — start from the right"; H2 "ہر خانے کا نام لیں — name each
  place"; H3 re-teach with ۲۰۰۵.
- **Homework:** write three household numbers (page number, house number, a price) in words.
- **Parent note:** "بچے سے گھر کے نمبر پڑھوائیں — ask your child to read the house/page numbers aloud."
- **Teacher note:** watch for reading the wrong place; use the place-value mat.

#### L1.2 — Place value to 100,000 (MATH-G4-NB-02)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can state the value of each digit in a number up
  to 100,000 (ten-thousands, thousands, hundreds, tens, ones).
- **Difficulty:** CORE
- **Estimated duration:** 20 min
- **Prerequisites:** MATH-G4-NB-01
- **Vocabulary:** دس ہزار (ten-thousand), جگہ کی قیمت (place value)
- **Examples:** in ۴۵٬۶۷۸ the ۴ means چالیس ہزار (forty thousand).
- **Worked example:** decompose ۲۳٬۴۰۵ → ۲ دس-ہزار + ۳ ہزار + ۴ سو + ۰ دہائی + ۵ اکائی.
- **Practice (6 items):** "what is the value of the underlined digit?" drag-to-place-value-mat +
  MCQ. Auto-graded.
- **Assessment (formative):** 6-item pool; ≥ 4/5 distinct.
- **Revision triggers:** `m-place-value-digit-equals-value`; wrong on comparing (NB-03).
- **Misconceptions:** `m-place-value-digit-equals-value`.
- **Hint ladder:** H1 "خانہ گنیں — count the columns"; H2 "دائیں سے جگہ کا نام"; H3 re-teach ۲۳٬۴۰۵.
- **Homework:** decompose two numbers into place-value parts.
- **Parent note:** build numbers with beads/matchsticks in groups of ten.
- **Teacher note:** the zero-as-placeholder case (۲۳٬۴۰۵) trips learners — dwell on it.

#### L1.3 — Comparing and ordering numbers (MATH-G4-NB-03)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can compare and order whole numbers to 100,000
  using >, <, =.
- **Difficulty:** CORE
- **Estimated duration:** 18 min
- **Prerequisites:** MATH-G4-NB-02
- **Vocabulary:** بڑا (greater), چھوٹا (less), برابر (equal), ترتیب (order)
- **Examples:** ۴۵٬۶۷۸ > ۴۵٬۶۰۹ (compare left to right).
- **Worked example:** compare ۹٬۸۷۶ and ۱۰٬۰۰۱ — count digits first (5 > 4), so the second is larger.
- **Practice (6 items):** insert >, <, =; order three numbers. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-bigger-number-more-digits-always`; wrong on rounding (NB-04).
- **Misconceptions:** `m-bigger-number-more-digits-always`.
- **Hint ladder:** H1 "پہلے ہندسے گنیں — count digits first"; H2 "پھر بائیں سے موازنہ"; H3 re-teach.
- **Homework:** order four family members' ages / four prices.
- **Parent note:** compare quantities while shopping ("which is more?").
- **Teacher note:** stress digit-count before left-to-right comparison.

#### L1.4 — Rounding to the nearest 10 and 100 (MATH-G4-NB-04)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can round whole numbers to the nearest 10 and
  100.
- **Difficulty:** CORE
- **Estimated duration:** 18 min
- **Prerequisites:** MATH-G4-NB-03
- **Vocabulary:** قریب ترین (nearest), گول کرنا (rounding)
- **Examples:** ۴۷ ≈ ۵۰ (to nearest 10); ۳۴۰ ≈ ۳۰۰ (to nearest 100).
- **Worked example:** round ۲۶۸ to nearest 100 — look at the tens digit (۶ ≥ ۵) → round up → ۳۰۰.
- **Practice (6 items):** round-to-10 and round-to-100 MCQ + number-line select. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** wrong on estimation in AS-04.
- **Misconceptions:** rounding the wrong digit (add `m-round-wrong-place` locally if observed).
- **Hint ladder:** H1 "کونسا ہندسہ دیکھنا ہے؟"; H2 "۵ یا زیادہ تو اوپر"; H3 re-teach ۲۶۸.
- **Homework:** round three prices to the nearest 10.
- **Parent note:** estimate the shopping total by rounding.
- **Teacher note:** the "exactly 5" convention (round up) needs an explicit example.

#### R1 — Unit 1 revision + checkpoint

Mixed 8-item formative pull from NB-01…04 pools; summary card of place value; no new content.
Revision triggers feed the spacing engine. Duration 15 min.

---

### Unit 2 — Addition and subtraction (to 4 digits)

Objective set: MATH-G4-AS-01 … AS-04. Unit outcome `[RE-EXPRESSED]`: *the learner can add and subtract
whole numbers to 4 digits with regrouping and solve word problems.*

#### ★ L2.1 — Adding 4-digit numbers with carrying (MATH-G4-AS-01)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can add two 4-digit numbers, carrying across
  places.
- **Difficulty:** CORE
- **Estimated duration:** 20 min
- **Prerequisites:** MATH-G4-NB-02
- **Vocabulary:** جوڑ (sum), ہتھیلی/ہاتھ لے جانا (carry), جمع (addition)
- **Examples:** ۲۴۷۶ + ۱۳۸۵ = ۳۸۶۱.
- **Worked example (script):**
  - "اکائی سے شروع: ۶+۵=۱۱، ۱ لکھیں، ۱ لے جائیں۔"
  - "دہائی: ۷+۸+۱=۱۶، ۶ لکھیں، ۱ لے جائیں۔ … جواب ۳۸۶۱۔"
  - "Start at the ones: 6+5=11, write 1 carry 1. Tens: 7+8+1=16, write 6 carry 1…"
- **Practice (6 items):** column sums with and without carrying; one "find the missing carry".
  Auto-graded.
- **Assessment (formative):** 6-item pool; ≥ 4/5 distinct.
- **Revision triggers:** `m-carry-forgotten`; wrong on AS-03 word problems.
- **Misconceptions:** `m-carry-forgotten`.
- **Hint ladder:** H1 "کہاں سے شروع کریں؟"; H2 "۹ سے بڑا ہو تو ایک لے جائیں"; H3 re-teach ۲۴۷۶+۱۳۸۵.
- **Homework:** add two 3-digit prices.
- **Parent note:** add two grocery prices together with your child.
- **Teacher note:** the carry into a new highest place (sum grows a digit) needs an example.

#### L2.2 — Subtracting 4-digit numbers with borrowing (MATH-G4-AS-02)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can subtract 4-digit numbers with regrouping
  (borrowing), including across a zero.
- **Difficulty:** CORE
- **Estimated duration:** 22 min
- **Prerequisites:** MATH-G4-AS-01
- **Vocabulary:** تفریق (subtraction), ادھار لینا (borrow), باقی (difference)
- **Examples:** ۴۰۰۵ − ۱۲۳۸ = ۲۷۶۷.
- **Worked example:** borrow across the zero in ۴۰۰۵ − ۱۲۳۸, step by step.
- **Practice (6 items):** with borrowing, incl. borrow-across-zero; one "check by adding back".
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-borrow-forgotten`.
- **Misconceptions:** `m-borrow-forgotten`.
- **Hint ladder:** H1 "کیا اوپر کا ہندسہ کافی ہے؟"; H2 "اگلی جگہ سے ادھار لیں"; H3 re-teach across-zero.
- **Homework:** find change from a note for a purchase.
- **Parent note:** work out change together at a shop.
- **Teacher note:** borrow-across-zero is the hardest case; model it twice.

#### L2.3 — Word problems: addition and subtraction (MATH-G4-AS-03)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can choose add or subtract for one- and two-step
  everyday word problems and solve them.
- **Difficulty:** CORE
- **Estimated duration:** 22 min
- **Prerequisites:** MATH-G4-AS-01, AS-02
- **Vocabulary:** کل (total), بچا (left), زیادہ/کم (more/less)
- **Examples:** "A shop had ۱۲۵۰ notebooks, sold ۴۸۰; how many left?"
- **Worked example:** identify keyword → operation → compute → check reasonableness.
- **Practice (6 items):** mix of add/subtract, one two-step; short "which operation?" selectors.
  Deterministic answers auto-graded; a "show your steps" item is formative-only.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** wrong operation choice; feeds AS-04.
- **Misconceptions:** keyword-only reasoning (add `m-keyword-only` locally if observed).
- **Hint ladder:** H1 "کیا پوچھا گیا ہے؟"; H2 "جوڑنا ہے یا گھٹانا؟"; H3 re-teach a parallel problem.
- **Homework:** one everyday two-step problem set at home.
- **Parent note:** pose a simple "how many left?" question during chores.
- **Teacher note:** discourage keyword-matching; ask learners to picture the situation.

#### L2.4 — Estimation and checking (MATH-G4-AS-04)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can estimate sums/differences by rounding and
  check whether an answer is reasonable.
- **Difficulty:** STRETCH
- **Estimated duration:** 18 min
- **Prerequisites:** MATH-G4-NB-04, AS-03
- **Vocabulary:** اندازہ (estimate), معقول (reasonable)
- **Examples:** ۲۹۷ + ۴۰۵ ≈ ۳۰۰ + ۴۰۰ = ۷۰۰.
- **Worked example:** estimate then compare to the exact answer to catch an error.
- **Practice (6 items):** "estimate first, then check"; spot the unreasonable answer. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** feeds all later word-problem checking.
- **Misconceptions:** rounding the wrong way.
- **Hint ladder:** H1 "ہر عدد کو گول کریں"; H2 "اب جوڑیں"; H3 re-teach.
- **Homework:** estimate a shopping total, then check.
- **Parent note:** guess the total before the shopkeeper adds it up.
- **Teacher note:** frame estimation as a self-check habit, not a separate topic.

#### R2 — Unit 2 revision + checkpoint

Mixed 8-item pull from AS pools; add/subtract summary; 15 min.

---

### Unit 3 — Multiplication

Objective set: MATH-G4-ML-01 … ML-04. Unit outcome `[RE-EXPRESSED]`: *the learner can multiply up to
3-digit by 1-digit and 2-digit by 2-digit numbers and solve word problems.*

#### ★ L3.1 — Multiplication facts and patterns (MATH-G4-ML-01)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can recall multiplication facts to 10×10 and
  explain multiplication as repeated addition / equal groups.
- **Difficulty:** INTRO
- **Estimated duration:** 20 min
- **Prerequisites:** MATH-G4-AS-01
- **Vocabulary:** ضرب (multiply), گنا (times), گروہ (group), پہاڑا (times-table)
- **Examples:** ۶×۴ = ۶+۶+۶+۶ = ۲۴.
- **Worked example (script):**
  - "ضرب یعنی برابر گروہ۔ ۴ گروہ، ہر ایک میں ۶ — ۶ کو ۴ بار جوڑیں = ۲۴۔"
  - "Multiplication is equal groups: four groups of six is six added four times = 24."
- **Practice (6 items):** fact recall + "which repeated-addition matches 6×4?" Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-mult-add-instead`; underpins ML-02…04, DV, area/measurement.
- **Misconceptions:** `m-mult-add-instead`.
- **Hint ladder:** H1 "کتنے گروہ؟"; H2 "ہر گروہ میں کتنے؟ جوڑیں"; H3 re-teach with counters.
- **Homework:** skip-count in 6s to 60.
- **Parent note:** count objects in equal groups (eggs in trays, etc.).
- **Teacher note:** anchor facts in equal-groups meaning, not rote only.

#### L3.2 — Multiply 2-digit by 1-digit (MATH-G4-ML-02)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can multiply a 2-digit number by a 1-digit number
  with regrouping.
- **Difficulty:** CORE
- **Estimated duration:** 20 min
- **Prerequisites:** MATH-G4-ML-01
- **Vocabulary:** ہتھیلی/ہاتھ لے جانا (carry in multiplication)
- **Examples:** ۳۷ × ۴ = ۱۴۸.
- **Worked example:** ones then tens with the carry, step by step.
- **Practice (6 items):** column products with carrying. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-carry-forgotten`; feeds ML-03.
- **Misconceptions:** `m-carry-forgotten`, `m-mult-add-instead`.
- **Hint ladder:** H1 "اکائی سے شروع"; H2 "لے جانا نہ بھولیں"; H3 re-teach ۳۷×۴.
- **Homework:** two 2-digit × 1-digit problems from home (e.g., cost of 4 items).
- **Parent note:** "if one costs ۳۷, four cost…?"
- **Teacher note:** align digits; the carry from ones into tens is the usual slip.

#### L3.3 — Multiply 3-digit by 1-digit and 2-digit by 2-digit (MATH-G4-ML-03)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can multiply 3-digit by 1-digit and 2-digit by
  2-digit numbers using the standard method.
- **Difficulty:** STRETCH
- **Estimated duration:** 24 min
- **Prerequisites:** MATH-G4-ML-02
- **Vocabulary:** جزوی حاصل ضرب (partial product)
- **Examples:** ۲۳ × ۱۴ = ۳۲۲.
- **Worked example:** partial products (۲۳×۴, then ۲۳×۱۰) and add.
- **Practice (6 items):** 3-digit×1-digit and 2-digit×2-digit. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** place-value slips (`m-place-value-digit-equals-value`).
- **Misconceptions:** forgetting the place-holder zero in the second partial product.
- **Hint ladder:** H1 "دو حصوں میں توڑیں"; H2 "دوسری سطر میں صفر رکھیں"; H3 re-teach ۲۳×۱۴.
- **Homework:** one 2-digit × 2-digit problem.
- **Parent note:** total cost of several same-price items.
- **Teacher note:** the missing placeholder zero is the top error; make it explicit.

#### L3.4 — Multiplication word problems (MATH-G4-ML-04)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can identify and solve multiplication word
  problems (equal groups, arrays, rate).
- **Difficulty:** CORE
- **Estimated duration:** 20 min
- **Prerequisites:** MATH-G4-ML-02, ML-03
- **Vocabulary:** فی (per), قطار (row/array)
- **Examples:** "۶ boxes, ۸ pencils each — how many pencils?"
- **Worked example:** picture the groups → multiply → check by estimation.
- **Practice (6 items):** equal-groups + array problems; a "which operation?" selector.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** wrong operation; feeds DV word problems.
- **Misconceptions:** `m-mult-add-instead`.
- **Hint ladder:** H1 "کتنے گروہ، ہر ایک میں کتنے؟"; H2 "ضرب کریں"; H3 re-teach.
- **Homework:** one equal-groups problem from home.
- **Parent note:** count rows × columns in a tray or tiles.
- **Teacher note:** connect arrays to area (previews geometry/measurement).

#### R3 — Unit 3 revision + checkpoint

Mixed 8-item pull from ML pools; 15 min.

---

### Unit 4 — Division

Objective set: MATH-G4-DV-01 … DV-04. Unit outcome `[RE-EXPRESSED]`: *the learner can divide 2–3 digit
numbers by a 1-digit number, interpret remainders, and solve word problems.*

#### ★ L4.1 — Division as sharing and grouping (MATH-G4-DV-01)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can explain division as equal sharing / equal
  grouping and relate it to multiplication.
- **Difficulty:** INTRO
- **Estimated duration:** 20 min
- **Prerequisites:** MATH-G4-ML-01
- **Vocabulary:** تقسیم (divide), برابر بانٹنا (share equally), الٹ عمل (inverse)
- **Examples:** ۱۲ ÷ ۴ = ۳ (share 12 among 4).
- **Worked example (script):**
  - "۱۲ ٹافیاں، ۴ بچے — ہر بچے کو برابر۔ ہر ایک کو ۳ ملیں۔"
  - "12 sweets shared among 4 children — 3 each. Division shares equally; the answer is smaller."
- **Practice (6 items):** share/group MCQ + "which multiplication matches 12÷4?" Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-div-bigger-answer`; underpins DV-02…04.
- **Misconceptions:** `m-div-bigger-answer`.
- **Hint ladder:** H1 "کتنے میں بانٹنا ہے؟"; H2 "برابر گروہ بنائیں"; H3 re-teach with counters.
- **Homework:** share objects at home equally and write the division.
- **Parent note:** share snacks equally and ask "how many each?"
- **Teacher note:** link ÷ to × immediately (fact families).

#### L4.2 — Division facts and remainders (MATH-G4-DV-02)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can divide within known facts and express what is
  left over as a remainder.
- **Difficulty:** CORE
- **Estimated duration:** 20 min
- **Prerequisites:** MATH-G4-DV-01
- **Vocabulary:** باقی (remainder), پورا (exact)
- **Examples:** ۱۳ ÷ ۴ = ۳ باقی ۱.
- **Worked example:** share 13 among 4 → 3 each, 1 left → "3 remainder 1".
- **Practice (6 items):** with and without remainders. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-remainder-dropped`.
- **Misconceptions:** `m-remainder-dropped`.
- **Hint ladder:** H1 "برابر بانٹنے کے بعد کیا بچا؟"; H2 "بچا ہوا باقی ہے"; H3 re-teach ۱۳÷۴.
- **Homework:** two share-with-leftover problems.
- **Parent note:** "if 13 rotis for 4 people, how many each and how many left?"
- **Teacher note:** the remainder is often dropped; make "what is left?" explicit.

#### L4.3 — Divide 2–3 digit by 1-digit (MATH-G4-DV-03)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can divide a 2–3 digit number by a 1-digit
  number using the standard method, with remainders.
- **Difficulty:** STRETCH
- **Estimated duration:** 24 min
- **Prerequisites:** MATH-G4-DV-02
- **Vocabulary:** لمبی تقسیم (long division), مقسوم/مقسوم علیہ (dividend/divisor)
- **Examples:** ۸۵ ÷ ۵ = ۱۷.
- **Worked example:** long-division steps (divide, multiply, subtract, bring down).
- **Practice (6 items):** 2- and 3-digit dividends. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-remainder-dropped`; place-value alignment.
- **Misconceptions:** `m-remainder-dropped`, alignment errors.
- **Hint ladder:** H1 "بائیں سے شروع"; H2 "تقسیم، ضرب، تفریق، نیچے لائیں"; H3 re-teach ۸۵÷۵.
- **Homework:** one long-division problem.
- **Parent note:** split a bill equally among people.
- **Teacher note:** the four-step cycle needs repetition; keep digits aligned.

#### L4.4 — Division word problems (MATH-G4-DV-04)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can solve division word problems and interpret
  the remainder in context.
- **Difficulty:** CORE
- **Estimated duration:** 20 min
- **Prerequisites:** MATH-G4-DV-03
- **Vocabulary:** فی کس (per person), گروہ بندی (grouping)
- **Examples:** "۲۵ children, ۴ per bench — how many benches?"
- **Worked example:** decide whether the remainder rounds up (need an extra bench) or is left over.
- **Practice (6 items):** share and group problems; remainder-in-context selector.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** remainder interpretation; wrong operation.
- **Misconceptions:** `m-div-bigger-answer`, `m-remainder-dropped`.
- **Hint ladder:** H1 "بانٹنا ہے یا گروہ بنانا؟"; H2 "باقی کا کیا کریں؟"; H3 re-teach.
- **Homework:** one grouping problem from home.
- **Parent note:** "how many cars for 25 people, 4 each?"
- **Teacher note:** context decides the remainder — discuss both "round up" and "left over".

#### R4 — Unit 4 revision + checkpoint

Mixed 8-item pull from DV pools; 15 min.

---

### Unit 5 — Fractions (spine; extends the live FR-01 lesson)

Objective set: MATH-G4-FR-01 … FR-05. Unit outcome `[RE-EXPRESSED]`: *the learner can name, compare,
find equivalents for, and add/subtract like fractions.* **FR-01 already exists and is live**
(`fractions_lesson.py`); this unit reuses it unchanged and adds FR-02…05.

#### ★ L5.1 — Introduction to fractions (MATH-G4-FR-01) — EXISTING, live

- **Learning outcome `[RE-EXPRESSED]`:** the learner can name a fraction as an equal part of a whole
  (halves, quarters).
- **Difficulty:** INTRO
- **Estimated duration:** 20 min
- **Prerequisites:** none (entry lesson)
- **Vocabulary:** کسر (fraction), برابر حصے (equal parts), اوپر/نیچے کا نمبر (numerator/denominator)
- **Examples / worked example / practice / assessment / hints / homework / misconceptions:** **as
  authored in `fractions_lesson.py`** — 5 practice items, the `m-bigger-denominator-is-bigger`
  detector + correction, graduated pizza-slice hints, and homework. **Do not re-author; reference it.**
- **Revision triggers:** `m-bigger-denominator-is-bigger`; feeds FR-02…05.
- **Note:** this lesson is the content-model reference for every lesson above; new lessons mirror its
  shape exactly.

#### L5.2 — Numerator and denominator; parts of a whole (MATH-G4-FR-02)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can read and write a fraction and identify what
  the top and bottom numbers mean, including thirds, fifths, and eighths.
- **Difficulty:** CORE
- **Estimated duration:** 18 min
- **Prerequisites:** MATH-G4-FR-01
- **Vocabulary:** شمار کنندہ (numerator), نسب نما (denominator)
- **Examples:** ۳/۵ — three parts of five equal parts.
- **Worked example:** shade 3 of 5 equal parts; write ۳/۵.
- **Practice (6 items):** "shade the fraction" / "name the shaded fraction". Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** miscount of equal parts; feeds FR-03.
- **Misconceptions:** unequal parts counted as valid (add `m-unequal-parts` locally if observed).
- **Hint ladder:** H1 "کل کتنے حصے؟"; H2 "کتنے رنگے؟"; H3 re-teach with ۳/۵.
- **Homework:** draw and label two fractions of a chapati/roti.
- **Parent note:** cut food into equal parts and name the fraction eaten.
- **Teacher note:** insist on *equal* parts; unequal shading is the classic error.

#### L5.3 — Equivalent fractions (MATH-G4-FR-03)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can find simple equivalent fractions (e.g.
  1/2 = 2/4 = 3/6).
- **Difficulty:** STRETCH
- **Estimated duration:** 20 min
- **Prerequisites:** MATH-G4-FR-02
- **Vocabulary:** مساوی کسر (equivalent fraction)
- **Examples:** ۱/۲ = ۲/۴.
- **Worked example:** multiply top and bottom by the same number; show with a fraction bar.
- **Practice (6 items):** "which fractions are equal?" + fill-the-missing-equivalent. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-equivalent-only-numerator`.
- **Misconceptions:** `m-equivalent-only-numerator`.
- **Hint ladder:** H1 "کیا دونوں برابر نظر آتے ہیں؟"; H2 "اوپر اور نیچے دونوں کو ضرب دیں"; H3 re-teach.
- **Homework:** find one equivalent for 1/2 and one for 1/3.
- **Parent note:** show that half a roti = two quarters.
- **Teacher note:** the "same number top and bottom" rule must be stated and shown visually.

#### L5.4 — Comparing fractions (MATH-G4-FR-04)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can compare two fractions with the same
  denominator, and simple unit fractions.
- **Difficulty:** CORE
- **Estimated duration:** 18 min
- **Prerequisites:** MATH-G4-FR-02
- **Vocabulary:** موازنہ (comparison)
- **Examples:** ۳/۵ > ۲/۵; ۱/۲ > ۱/۴.
- **Worked example:** same bottom → compare tops; unit fractions → more parts means smaller.
- **Practice (6 items):** insert >, < between fractions. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-bigger-denominator-is-bigger`.
- **Misconceptions:** `m-bigger-denominator-is-bigger`.
- **Hint ladder:** H1 "نیچے کا نمبر ایک جیسا ہے؟"; H2 "تو اوپر گنیں"; H3 re-teach with bars.
- **Homework:** compare two fractions of a shared item.
- **Parent note:** who ate more — 2/4 or 3/4 of the roti?
- **Teacher note:** separate the same-denominator case from the unit-fraction case.

#### L5.5 — Adding and subtracting like fractions (MATH-G4-FR-05)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can add and subtract fractions with the same
  denominator.
- **Difficulty:** STRETCH
- **Estimated duration:** 20 min
- **Prerequisites:** MATH-G4-FR-02, FR-04
- **Vocabulary:** یکساں کسر (like fractions)
- **Examples:** ۱/۴ + ۲/۴ = ۳/۴.
- **Worked example:** add the tops, keep the bottom; show with a bar.
- **Practice (6 items):** add and subtract like fractions. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-fraction-add-denominators`.
- **Misconceptions:** `m-fraction-add-denominators`.
- **Hint ladder:** H1 "نیچے کا نمبر بدلتا ہے؟"; H2 "صرف اوپر جوڑیں"; H3 re-teach ۱/۴+۲/۴.
- **Homework:** two add/subtract like-fraction problems.
- **Parent note:** combine parts of the same whole (1/4 + 1/4 of a roti).
- **Teacher note:** the "add the bottoms too" error is near-universal; pre-empt it.

#### R5 — Unit 5 revision + checkpoint

Mixed 8-item pull from FR pools (incl. live FR-01); 15 min.

---

### Unit 6 — Measurement

Objective set: MATH-G4-ME-01 … ME-04. Unit outcome `[RE-EXPRESSED]`: *the learner can measure and
convert length, mass, and capacity in metric units and read time.*

#### ★ L6.1 — Length: metres and centimetres (MATH-G4-ME-01)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can measure length and convert between metres and
  centimetres (1 m = 100 cm).
- **Difficulty:** CORE
- **Estimated duration:** 20 min
- **Prerequisites:** MATH-G4-ML-01
- **Vocabulary:** لمبائی (length), میٹر (metre), سینٹی میٹر (centimetre)
- **Examples:** ۲ میٹر = ۲۰۰ سینٹی میٹر.
- **Worked example (script):** "۱ میٹر میں ۱۰۰ سینٹی میٹر۔ ۲ میٹر یعنی ۲×۱۰۰ = ۲۰۰ سینٹی میٹر۔"
- **Practice (6 items):** convert m↔cm; pick the sensible unit. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-unit-mix`.
- **Misconceptions:** `m-unit-mix`.
- **Hint ladder:** H1 "ایک میٹر میں کتنے سینٹی میٹر؟"; H2 "ایک ہی اکائی بنائیں"; H3 re-teach.
- **Homework:** measure two objects at home in cm.
- **Parent note:** measure your child's height in cm and m.
- **Teacher note:** always convert to one unit before adding.

#### L6.2 — Mass: kilograms and grams (MATH-G4-ME-02)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can compare and convert mass between kilograms
  and grams (1 kg = 1000 g).
- **Difficulty:** CORE
- **Estimated duration:** 18 min
- **Prerequisites:** MATH-G4-ME-01
- **Vocabulary:** وزن (mass/weight), کلوگرام (kg), گرام (g)
- **Examples:** ۱ کلوگرام = ۱۰۰۰ گرام.
- **Worked example:** convert 2 kg to grams; compare 1500 g and 1 kg.
- **Practice (6 items):** convert and compare mass. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-unit-mix`.
- **Misconceptions:** `m-unit-mix`.
- **Hint ladder:** H1 "کلو میں کتنے گرام؟"; H2 "برابر اکائی بنائیں"; H3 re-teach.
- **Homework:** read two package weights at home.
- **Parent note:** compare weights of grocery packets.
- **Teacher note:** relate to shopping quantities children see.

#### L6.3 — Capacity: litres and millilitres (MATH-G4-ME-03)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can compare and convert capacity between litres
  and millilitres (1 l = 1000 ml).
- **Difficulty:** CORE
- **Estimated duration:** 18 min
- **Prerequisites:** MATH-G4-ME-02
- **Vocabulary:** گنجائش (capacity), لیٹر (litre), ملی لیٹر (ml)
- **Examples:** ۱ لیٹر = ۱۰۰۰ ملی لیٹر.
- **Worked example:** convert and compare capacities.
- **Practice (6 items):** convert and compare. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-unit-mix`.
- **Misconceptions:** `m-unit-mix`.
- **Hint ladder:** H1 "لیٹر میں کتنے ملی لیٹر؟"; H2 "ایک اکائی"; H3 re-teach.
- **Homework:** read two bottle capacities at home.
- **Parent note:** compare bottle sizes while filling water.
- **Teacher note:** connect to daily water/juice bottles.

#### L6.4 — Time: clocks and the calendar (MATH-G4-ME-04)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can read time on analogue and digital clocks (to
  5 minutes) and use days/weeks/months.
- **Difficulty:** CORE
- **Estimated duration:** 22 min
- **Prerequisites:** none (independent)
- **Vocabulary:** گھنٹہ (hour), منٹ (minute), ہفتہ (week), مہینہ (month)
- **Examples:** "quarter past three" = ۳:۱۵.
- **Worked example:** short hand = hours, long hand = minutes; read ۳:۱۵.
- **Practice (6 items):** read clock faces; days-of-week ordering. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-clock-hour-hand`.
- **Misconceptions:** `m-clock-hour-hand`.
- **Hint ladder:** H1 "چھوٹی سوئی کیا بتاتی ہے؟"; H2 "بڑی سوئی منٹ"; H3 re-teach ۳:۱۵.
- **Homework:** read the time at two moments of the day.
- **Parent note:** ask your child to tell the time at meals.
- **Teacher note:** hour-vs-minute-hand confusion is the main error.

#### R6 — Unit 6 revision + checkpoint

Mixed 8-item pull from ME pools; 15 min.

---

### Unit 7 — Geometry

Objective set: MATH-G4-GE-01 … GE-04. Unit outcome `[RE-EXPRESSED]`: *the learner can identify lines,
angles, 2D shapes, and lines of symmetry.*

#### ★ L7.1 — Lines, rays, and line segments (MATH-G4-GE-01)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can identify and name lines, rays, and line
  segments.
- **Difficulty:** INTRO
- **Estimated duration:** 16 min
- **Prerequisites:** none
- **Vocabulary:** خط (line), شعاع (ray), خط پارہ (line segment), نقطہ (point)
- **Examples:** a segment has two endpoints; a ray has one; a line has none.
- **Worked example (script):** compare the three with a simple diagram and endpoints.
- **Practice (6 items):** identify the figure. Auto-graded (Knowledge).
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** feeds angles (GE-02).
- **Misconceptions:** confusing ray and segment (add `m-ray-segment` locally if observed).
- **Hint ladder:** H1 "کتنے سرے ہیں؟"; H2 "دو سرے = خط پارہ"; H3 re-teach.
- **Homework:** find and name two lines/segments at home (table edge, etc.).
- **Parent note:** point out straight edges and corners around the house.
- **Teacher note:** endpoints are the distinguishing feature — count them.

#### L7.2 — Angles: right, acute, obtuse (MATH-G4-GE-02)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can recognize right, acute, and obtuse angles.
- **Difficulty:** CORE
- **Estimated duration:** 18 min
- **Prerequisites:** MATH-G4-GE-01
- **Vocabulary:** زاویہ (angle), قائمہ (right), حادہ (acute), منفرجہ (obtuse)
- **Examples:** a corner of a page is a right angle.
- **Worked example:** compare openings to a right angle.
- **Practice (6 items):** classify the angle. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-right-angle-size`.
- **Misconceptions:** `m-right-angle-size`.
- **Hint ladder:** H1 "کھلاؤ دیکھیں، لمبائی نہیں"; H2 "کیا یہ کونہ ۹۰ ہے؟"; H3 re-teach.
- **Homework:** find one right, one acute, one obtuse angle at home.
- **Parent note:** spot right angles in door and window corners.
- **Teacher note:** angle size ≠ arm length; use a paper-corner comparator.

#### L7.3 — 2D shapes and their properties (MATH-G4-GE-03)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can name common 2D shapes and state sides/corners
  (triangle, square, rectangle, circle).
- **Difficulty:** INTRO
- **Estimated duration:** 18 min
- **Prerequisites:** MATH-G4-GE-01
- **Vocabulary:** مثلث (triangle), مربع (square), مستطیل (rectangle), دائرہ (circle), ضلع (side)
- **Examples:** a square has 4 equal sides and 4 right angles.
- **Worked example:** count sides and corners of each shape.
- **Practice (6 items):** match shape↔properties. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** feeds symmetry (GE-04).
- **Misconceptions:** square-vs-rectangle confusion (add `m-square-rectangle` locally if observed).
- **Hint ladder:** H1 "کتنے ضلع؟"; H2 "کیا سب برابر ہیں؟"; H3 re-teach.
- **Homework:** find one of each shape at home.
- **Parent note:** name shapes of everyday objects (plate = circle, etc.).
- **Teacher note:** a square is a special rectangle — mention gently, don't over-formalize.

#### L7.4 — Symmetry (MATH-G4-GE-04)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can identify one or more lines of symmetry in
  simple shapes and patterns.
- **Difficulty:** CORE
- **Estimated duration:** 18 min
- **Prerequisites:** MATH-G4-GE-03
- **Vocabulary:** توازن/تناسب (symmetry), محورِ تناسب (line of symmetry)
- **Examples:** a square has 4 lines of symmetry.
- **Worked example:** fold-test — both halves match exactly.
- **Practice (6 items):** "is this line a line of symmetry?" + count lines. Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-symmetry-any-line`.
- **Misconceptions:** `m-symmetry-any-line`.
- **Hint ladder:** H1 "کیا موڑنے پر دونوں حصے ملتے ہیں؟"; H2 "بالکل برابر ہونا چاہیے"; H3 re-teach.
- **Homework:** find one symmetric object at home.
- **Parent note:** fold paper shapes to test symmetry together.
- **Teacher note:** the fold-test defeats the "any line" misconception.

#### R7 — Unit 7 revision + checkpoint

Mixed 8-item pull from GE pools; 15 min.

---

### Unit 8 — Data handling

Objective set: MATH-G4-DA-01 … DA-02. Unit outcome `[RE-EXPRESSED]`: *the learner can read and
construct simple pictographs and bar graphs.*

#### ★ L8.1 — Reading pictographs (MATH-G4-DA-01)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can read a pictograph where one symbol stands for
  a fixed number.
- **Difficulty:** INTRO
- **Estimated duration:** 18 min
- **Prerequisites:** MATH-G4-ML-01
- **Vocabulary:** تصویری خاکہ (pictograph), کلید (key), علامت (symbol)
- **Examples:** if 🍎 = 2 apples, then 3 symbols = 6 apples.
- **Worked example (script):** read the key first, then multiply symbols by the key value.
- **Practice (6 items):** "how many does the graph show?" Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-graph-scale-ignored`.
- **Misconceptions:** `m-graph-scale-ignored`.
- **Hint ladder:** H1 "کلید دیکھیں: ایک علامت کتنے کی؟"; H2 "علامتیں ضرب کریں"; H3 re-teach.
- **Homework:** read one simple pictograph (provided offline).
- **Parent note:** count categories of things at home (spoons, cups) and tally them.
- **Teacher note:** the key is everything — always read it first.

#### L8.2 — Reading and drawing bar graphs (MATH-G4-DA-02)

- **Learning outcome `[RE-EXPRESSED]`:** the learner can read a bar graph with a scale and compare
  categories.
- **Difficulty:** CORE
- **Estimated duration:** 20 min
- **Prerequisites:** MATH-G4-DA-01
- **Vocabulary:** سلاخی خاکہ (bar graph), پیمانہ (scale), محور (axis)
- **Examples:** a bar reaching "6" on a scale of 2 per square = 6.
- **Worked example:** read the scale, then the bar height; compare two bars.
- **Practice (6 items):** read values + "which category is most/least?" Auto-graded.
- **Assessment (formative):** 6-item pool.
- **Revision triggers:** `m-graph-scale-ignored`.
- **Misconceptions:** `m-graph-scale-ignored`.
- **Hint ladder:** H1 "پہلے پیمانہ دیکھیں"; H2 "ہر خانہ کتنے کا؟"; H3 re-teach.
- **Homework:** read one simple bar graph (provided offline).
- **Parent note:** tally and compare favourite fruits in the family.
- **Teacher note:** reading the scale before the bar prevents the top error.

#### R8 — Unit 8 revision + checkpoint

Mixed 8-item pull from DA pools; 15 min.

---

## 8. End-of-pilot summative (mentor-mediated)

- **Form:** a mixed set across all objectives, **mentor-mediated** (MVP §2 non-negotiable; summative
  identity is human-mediated, `summative_mentor_mediated = True` on the `LessonView`).
- **Auto-graded items** (Knowledge/Application) provide the objective evidence; **constructed
  "explain/show your working" items** are reviewed by the mentor — never auto-promoted.
- **Purpose:** measure mastery gain across the pilot (a Pilot-1 success criterion), **not** to rank or
  gate a child.

---

## 9. Content inventory (what WS4/WS5 must produce for this curriculum)

| Asset type | Count (approx.) | Notes |
| --- | --- | --- |
| Objectives (SLOs, `[RE-EXPRESSED]`) | 31 | NB×4, AS×4, ML×4, DV×4, FR×5, ME×4, GE×4, DA×2 |
| Teaching lessons | 31 | one per objective; incl. the live FR-01 |
| Revision lessons | 8 | R1–R8 |
| Summative | 1 | mentor-mediated (`S-math-g4-pilot`) |
| Practice/assessment items | ~210 | ≥ 5-item distinct pool per objective + revision + summative pulls |
| Homework items | 31 | one per teaching lesson |
| Worked examples | 31+ | ≥ 1 per lesson |
| Misconception entries | 15 | §4 library (+ locally-flagged extras) |
| Audio narration scripts | per [AUDIO_SCRIPT_GUIDE.md](AUDIO_SCRIPT_GUIDE.md) | Urdu-first, English support |
| Visual concepts (SVG/image) | ~40 | alt-text required (WCAG); no faces/brands |
| Offline packages | 40 | one `pkg/…` per teaching + revision lesson + summative |

Every item above must pass [CONTENT_QA_CHECKLIST.md](CONTENT_QA_CHECKLIST.md) before publish, and
carries `provenance = authored-original` with `aligned_slo_codes` set.

## 10. Change log

| Date | Change | Author |
| --- | --- | --- |
| 2026-07-21 | Grade 4 Mathematics pilot curriculum authored: 8 units, 33 lessons + 8 revisions, competency/mastery model, 15-entry misconception library, graduated hint hierarchy, revision/spacing model, mentor-mediated summative, content inventory. Extends live FR-01. NCP-aligned re-expression (non-verbatim), authored-original content. | Content authoring (WS4) |
