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

## 6. The AI-led path: no teacher required (binding since 2026-10-24)

The definitive mission ([`GLOBAL_PRODUCT_SCOPE.md`](../GLOBAL_PRODUCT_SCOPE.md)) forbids any
learner journey that depends on a teacher. §2–§3 stay as an **optional** human path. This section is
the primary path.

- **Self-paced homework.** Every lesson the learner has studied (a live session or a synced offline
  attempt on its objective) contributes its written items to the Homework screen. No assignment is
  needed. A teacher assignment, where one exists, only adds a due date. The list endpoint returns
  both, each item tagged `source: "self_paced" | "assignment"`.
- **Automatic marking only where it is reliable.** A written item whose `answer_key.answer` (plus
  `accepted_variants`) states an exact answer is marked on submit with the same `normalize` rule as
  fill items (ITEM_INTERACTION_CONTRACT §4). The mark is `met` / `not_yet`, `reviewed_by = "auto"`,
  and records one idempotent evidence. Nothing else is auto-marked.
- **Open written answers** (no exact key: stories, explanations, letters) are **never** scored by a
  rule or a model today. On submit the child gets `state: "submitted"` and
  `marking: "self_check"`. If the author provided a `sample_answer` or `guidance`, the child may then
  see it, labelled "compare your answer". No mastery evidence is recorded and the screen never says
  "marked".
- **AI marking (future, inert).** A rubric-marking port on the existing `LLMGateway` is defined and
  tested against a stub. It is disabled until FD-03 is approved **and** an in-region distress
  classifier screens the child's text first (FD-03 brief). It never runs on a teacher-free path
  before then.
- **Optional human marking.** If the learner is in a class, its teacher may still mark or return
  submissions (§3), including open ones.
- **Safety: nobody reading must not mean nobody protecting.** Every submitted text passes a
  deterministic **disclosure screen**: an Urdu + English phrase list kept as configuration, not
  code. A match raises a concern in the existing safeguarding triage queue (`source = system`,
  referencing the submission). The child's screen never changes because of it; the child always
  sees the existing "talk to a trusted adult / tell us" affordance. The screen only escalates to a
  human. It never decides, replies or blocks. The phrase list ships as an engineering starter and
  is marked **pending safeguarding-lead approval (M-Safe)**. With no teacher, `SHARING_REQUIRED`
  does not apply to self-paced items, because no third party sees them.

## Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-10-25 | §6 implemented: self-paced list + `POST …/homework/self-paced/{objectiveCode}/items/{itemRef}:submit` (`409 LESSON_ASSIGNED` when a class assigned it); `source`, `marking`, `can_retry`, `compare` fields; an automatic `not_yet` may be retried (one evidence per attempt, `{submission_id}:{attempt}`), an automatic `met` and any teacher mark are final; disclosure screen list in `contexts/safeguarding/disclosure_phrases.json`; migration `0017_self_paced_homework`. Self-paced answers are not shown to teachers. | Engineering |
| 2026-10-24 | §6 AI-led path: self-paced homework, reliable auto-marking only, open answers self-check, AI marking inert until FD-03. | Engineering |
| 2026-10-24 | Implementation notes: `SHARING_REQUIRED`, one row per item with `attempt`, the concern route. | Engineering |
| 2026-10-24 | Contract adopted: written items, learner homework + submission, teacher marking, evidence, safeguarding hook, privacy. | Engineering |
