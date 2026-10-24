# Item Interaction Contract

**Status:** binding · **Adopted:** 2026-10-24 · **Owner:** Curriculum Studio + Learning

This contract defines how every auto-graded item type is authored, projected, shown to the learner,
answered and scored. Before it existed the learner runtime could only score a chosen option
(`mcq`/`true_false`). Every other auto-graded type had no shape the runtime could use.

## 1. Canonical answer keys (authoring: `AssessmentItem`)

`options` are bilingual `LocalizedText` values shown to the learner. `answer_key` is **never**
sent to a device. Indices are 0-based positions in `options`.

| Kind | `type` (or `interactive` + `answer_key.mode`) | `options` | `answer_key` |
| --- | --- | --- | --- |
| choose | `mcq`, `true_false` · mode `choose` | ≥ 2 | `{"correct_option": i}` (+ `option_misconceptions`) |
| fill | `fill_blank` · mode `fill` | none | `{"answer": "<canonical text>"}`; extra accepted answers in `accepted_variants` |
| order | `ordering` · mode `order` | the items, in **display** order | `{"order": [i, …]}`: a permutation of all option indices, in the correct order |
| match | `matching` · mode `match` | left items, then right items | `{"left_count": k, "pairs": [[l, r], …]}`: every left `l < k` appears exactly once and every `r ≥ k`; each right is used at most once |
| sort | `interactive` + mode `sort` | cards, then group labels | `{"left_count": k, "pairs": [[card, group], …]}`: every card `< k` appears exactly once and `group ≥ k`; a group may hold many cards |

Optional on every kind: `"misconception": "<library id>"`, a misconception that any wrong answer
implies. On choose items it falls back after `option_misconceptions`.

An `interactive` item whose `answer_key.mode` is missing or unknown is a **widget**: a
bespoke interaction (clock hands, place-value mat, arrays) that has no runtime yet. Widgets are
valid Studio content but are not projected to the learner and are not scored. They are reported
so a future widget runtime can pick them up.

Human-graded types (`short`, `long`, `word_problem`) are outside this contract; see
`ASSESSMENT_STANDARD.md`.

## 2. Projection (`ItemView`, learning context)

`ItemView` gains `kind` (`choose` | `fill` | `order` | `match` | `sort`) and the display fields
`options` and `left_count`. The secret fields used only by the server-side scorer are
`correct_option`, `accepted_answers`, `correct_order`, `correct_pairs`, `option_misconceptions`
and `misconception`. Offline packages and every learner-facing API carry `kind`, `options`,
`left_count` and `hints`, and **no secret field**.

The playable auto-graded items in a lesson's `interactive_activities` are projected **before** its
practice questions, in the same `practice_items` sequence, so a lesson session plays activities
first and then practice. Widgets and human-graded items are skipped.

## 3. Answers (API `:answer`, placement, offline `attempt.submitted`)

Exactly one of these fields is present:

| Kind | Field | Example |
| --- | --- | --- |
| choose | `option` (int) | `{"option": 2}` |
| fill | `text` (string, ≤ 200 chars) | `{"text": "۴۰"}` |
| order | `order` (list of option indices) | `{"order": [1, 2, 0]}` |
| match / sort | `pairs` (list of `[left, right]`) | `{"pairs": [[0, 4], [1, 3]]}` |

`option` alone stays valid for choose items, so existing clients keep working. If an answer's
shape does not match the item's kind, the API returns 422 and sync returns `conflict`.

## 4. Scoring (`learning.domain.scorer`)

- **choose:** correct if `option == correct_option`.
- **fill:** correct if `normalize(text)` equals `normalize` of `answer` or of any accepted variant.
  `normalize` applies NFKC, trims, folds case and collapses whitespace. It maps Urdu/Arabic-Indic
  digits to ASCII, removes `,` and `٬` between digits, and strips trailing `. ۔ ! ?`.
- **order:** correct if the submitted sequence equals `correct_order` exactly.
- **match / sort:** correct if the submitted pairs, as a set, equal `correct_pairs`. Partial credit
  is not given (mastery evidence is binary today).

A wrong answer implies `option_misconceptions[option]` (choose only), otherwise `misconception`,
otherwise none.

## Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-10-24 | Contract adopted: canonical keys for fill/order/match/sort, projection, answers, scoring. | Engineering |
