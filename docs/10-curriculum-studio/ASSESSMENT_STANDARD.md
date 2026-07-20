# Assessment Standard

| | |
|---|---|
| **Status** | Phase 3 · The assessment engine Curriculum Studio authors against · Related: [23 Assessment](../05-education/23-assessment-engine.md) · [58 Mastery & Validity](../05-education/58-mastery-and-assessment-validity.md) |
| **Date** | 2026-07-20 |

## 1. Item types (supported)

| Type | Grading | Notes |
|---|---|---|
| **MCQ** | auto | single/multi; guessing-adjusted |
| **True/False** | auto | down-weighted (50% guess) |
| **Fill in the blanks** | auto | exact + accepted-variants (Urdu diacritics) |
| **Matching** | auto | pairs |
| **Ordering** | auto | sequence |
| **Short Answer** | auto (deterministic) / AI-assisted → human | Urdu short-answer flagged for review |
| **Long Answer** | human / AI-assisted-then-human | rubric-scored |
| **Word Problems** | auto (numeric) + reasoning (human) | shows working |
| **Interactive** | auto | drag/drop, tap, simulation |

## 2. Test types

| Test | Purpose |
|---|---|
| **Diagnostic** | placement / find prerequisite gaps (routes the DAG) |
| **Adaptive** | difficulty adapts to responses |
| **Revision** | spaced retrieval re-check (confirms mastery, [58 §1](../05-education/58-mastery-and-assessment-validity.md)) |
| **Summative** | promotion-bearing → **mentor-mediated identity assurance** ([58 §5](../05-education/58-mastery-and-assessment-validity.md)) |

## 3. Item object schema

```json
{ "item_id": "uuidv7", "type": "mcq|true_false|fill_blank|matching|ordering|short|long|word_problem|interactive",
  "objective_ref": "MATH-G1-N-01", "competency": "knowledge|comprehension|application|analysis",
  "stem": localized, "media": [ref], "options": [...], "answer_key": {...},
  "accepted_variants": [...], "rubric": {...}, "auto_marking_guidance": "...",
  "mentor_review_guidance": "...", "difficulty": "intro|developing|secure|challenge",
  "hints": [...], "explanation": localized, "provenance": {...} }
```

## 4. Rubrics (for constructed response)

Each long-answer/word-problem item carries a **rubric**: criteria × levels with descriptors, a max score,
and worked exemplars. Rubrics drive both AI-assisted pre-scoring and mentor review. Cut scores for any
promotion decision use a documented standard-setting method ([58 §3](../05-education/58-mastery-and-assessment-validity.md)).

## 5. Auto-marking + mentor-review guidance

- **`auto_marking_guidance`** — for deterministic items, the exact matching rules (incl. Urdu diacritic
  variants); for AI-assisted, the confidence boundary above which auto-score stands vs. escalates.
- **`mentor_review_guidance`** — what a Mentor checks, common partial-credit cases, red flags.

## 6. Item-bank & mastery rules (from [58](../05-education/58-mastery-and-assessment-validity.md))

- **≥5× distinct-item pool per SLO** (no repeats within a mastery window) → anti-gaming.
- Recognition-only types down-weighted; guessing correction applied.
- **Confirmed mastery** requires spaced-retention survival, not first-pass.
- Attempts are **immutable, sealed at submission**; **server-side scoring** (no on-device keys).

## 7. Validity requirements (release-gating)

- Every item maps to an SLO + competency; orphan items are errors.
- Items reviewed for difficulty/discrimination; poor-discrimination items retired.
- **Reading items:** if reading is the construct, **no audio scaffolding** on the passage (validity).
- Bias/gender/religious-neutrality rubric applied ([QUALITY_ASSURANCE_STANDARD](./QUALITY_ASSURANCE_STANDARD.md)).

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-20 | Assessment standard: 9 item types, 4 test types, item/rubric schema, auto+mentor marking, item-bank/mastery + validity rules. | Curriculum Studio |
