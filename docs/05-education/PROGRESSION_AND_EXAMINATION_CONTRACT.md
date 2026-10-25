# Progression and Examination Contract

**Status:** binding · **Adopted:** 2026-10-25 · **Owner:** Learning + Grading & Reporting

Taleem is an AI-led school: a child moves through a structured path of grades, subjects, units and
lessons, sits end-of-unit examinations marked automatically by defined rules, and keeps an academic
record. Before this contract there was no examination, no unit or grade completion, and no
browsable path ("Browse subjects is coming soon").

## 1. The path

- The learner's **grade** (enrolment `gradeLevel`) selects the curriculum pack's grade. Its
  subjects, chapters (**units**) and lessons come from the stored hierarchy and the published
  lessons, filtered by cohort (DEMO_COHORT_CONTRACT).
- Per lesson: `not_started` / `in_progress` (any evidence) / `practised` (the lesson's practice
  finished) / `mastered` (every objective of the lesson is mastered in the student model).
  "Completed" and "demonstrated" are distinct and both shown: finishing practice is never shown as
  mastery.
- Per unit: `not_started` / `in_progress` / `ready_for_check` (every lesson practised) /
  `completed` (unit check passed, §2). Per grade: `completed` when every unit is completed.
- The web shows Subjects → Units → Lessons with these states and the AI's recommended next step.
  It replaces "coming soon".

## 2. Unit checks (examinations)

- A **unit check** is a fixed-length test (default 10 items, a pack setting) assembled from the
  unit's published lessons. It draws from formative and summative pools and practice items, uses
  auto-scored kinds only (ITEM_INTERACTION_CONTRACT), and is balanced across the unit's objectives.
  It never includes an item the learner saw in the last 7 days when the pool allows, so a retake is
  not the same paper.
- Scoring is reproducible: one point per correct item, with the score as a percentage. The pass
  mark is a pack setting (default 70%). The result has a per-objective breakdown and lists the
  misconceptions detected. Answers are scored on the server only, and keys never reach the device.
- A **sitting** is resumable for 24 hours after it starts (interrupted connectivity or app
  restart). Each item can be answered once per sitting; a repeated submission is idempotent. An
  unfinished sitting expires as `incomplete`, never `failed`.
- Retakes are allowed after the learner has done remediation on the missed objectives, or after 24
  hours. Every sitting is kept, and the record shows the best result plus the full history.
- Each answer records evidence (context `summative`, lesson version per provenance), so mastery
  updates. A failed check routes the learner to remediation on the missed objectives.
- **Integrity and claims.** Unit checks are unproctored and **not promotion-bearing**, so they are
  labelled "Taleem unit check" and never presented as certification. Online only in this version
  (assembly and scoring are server-side), and the app says so honestly when offline.

## 3. Academic record

- `GET` routes for the learner (self), the guardian (own child) and an optional teacher (own class)
  return the record: grade, subjects, unit states, unit-check sittings (date, score, pass/fail,
  per-objective breakdown), lessons mastered, report cards (links), and the derivation time.
- Every figure derives from stored sittings and evidence, so nothing on it can be typed in. Grade
  completion is a record entry labelled "Grade 4 completed in Taleem — not an accredited
  certificate".

## 4. Privacy

Sittings are C2 learning records. Guardian export includes them, erasure deletes them, the
completeness gate covers them, and they live in the `learning` schema (alembic migration).

## Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-10-25 | Contract adopted: path states, unit checks, sittings, academic record. | Engineering |
