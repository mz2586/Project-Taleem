# Homework and Marking Contract

**Status:** binding · **Adopted:** 2026-10-24 · **Owner:** School + Learning

A child answers a written item (`short`, `long` or `word_problem`) from a lesson their teacher has
assigned. The teacher marks it, and the mark becomes mastery evidence. Before this contract the
Homework screen was an empty state and human-graded items had no path at all.

## 1. Which items

**Written items** are a published lesson's `homework`, `challenge_problems` and
`interactive_activities` items whose type is `short`, `long` or `word_problem`. They are projected
as `ItemView.kind = "written"` with:

- learner-visible: `prompt`, `hints`, `max_chars` (200 for `short`, 2000 otherwise);
- teacher-visible only: `rubric` (criteria, `max_score`, levels with descriptors), and the
  `sample_answer` or `guidance` taken from `answer_key` when present.

Written items are never auto-scored. A learner-facing response never contains a rubric, sample
answer or guidance.

## 2. Learner homework (school context)

- `GET /v1/school/learners/{student_ref}/homework` lists, for every assignment of every class the
  learner is in, the assignment (`assignment_id`, `objective_code`, lesson title, `due_at`) and its
  written items. Each item carries its latest submission state: `not_started`, `submitted`,
  `returned` (with feedback) or `marked` (with outcome and feedback). The learner gets the same
  live consent gate as every other learner surface (withdrawn ⇒ 403).
- `POST /v1/school/learners/{student_ref}/homework/{assignment_id}/items/{item_ref}:submit`
  takes `{"text": "..."}`. The text is trimmed, must not be empty, and is capped at the item's
  `max_chars`. A child may resubmit while the state is `submitted` or `returned`. A `marked`
  submission is final (409). The item must belong to the assignment's lesson (404 otherwise).
- Submit is refused with `403 SHARING_REQUIRED` while the guardian has withdrawn progress
  sharing, so a child's writing never reaches a teacher who may not see it. The app keeps the text
  on the phone and says why it was not sent. There is one submission row per (assignment, item,
  learner); a resubmission replaces its text and increments `attempt`.
- Online only in this version. The web app says so when offline and never pretends a submission
  was saved.

## 3. Teacher marking

- `GET /v1/school/classes/{class_id}/submissions?status=submitted|returned|marked` returns the
  queue for the teacher's own class (other organizations get 404, as on every teacher route). Each
  row has the learner display name, the assignment and item, the prompt, the rubric, any sample
  answer or guidance, the text, and timestamps. Oldest first.
- `POST /v1/school/submissions/{submission_id}:mark` takes
  `{"outcome": "met" | "not_yet", "score": int | null, "feedback": str ≤ 1000}`. `score` is
  required when the item has a rubric and must be in `0..max_score`. A submission can be marked
  once (from `submitted` or `returned`); a later correction goes through a new submission.
- `POST /v1/school/submissions/{submission_id}:return` takes `{"feedback": str}` (required) and
  asks the child to try again.
- Marking records **one** `AssessmentEvidence` per submission in the learning context: outcome
  correct for `met`, incorrect for `not_yet`, context practice. It is idempotent by
  `submission_id`, so a retry never double-counts, and it goes through the existing aggregate and
  outbox.
- Every submit, mark and return is written to the durable school audit log (refs only, no text).

## 4. Child safety

Children's free text can contain a disclosure. Every queue row and submission view offers the
teacher **"Raise a safeguarding concern"** (`POST /v1/school/submissions/{id}:concern` with
`{"category", "text"?}`), which creates a concern in the existing safeguarding
queue (`source = teacher`, about that learner, referencing the `submission_id`). Teachers may raise
concerns only about learners in their own classes. Raising a concern never changes the
submission, and the child is never told.

## 5. Privacy

Submissions are child data, stored in the `school` schema (migration `0013`). Guardian export
includes them. Erasure deletes them, and the erasure completeness gate covers the new table.
Retention purge treats them like other learner work, and stays disabled until M-Gov sets the
periods. No submission text is ever logged.

## Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-10-24 | Implementation notes: `SHARING_REQUIRED`, one row per item with `attempt`, the concern route. | Engineering |
| 2026-10-24 | Contract adopted: written items, learner homework + submission, teacher marking, evidence, safeguarding hook, privacy. | Engineering |
