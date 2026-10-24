# Report Card Contract (v1)

**Status:** binding · **Adopted:** 2026-10-24 · **Owner:** Grading & Reporting · Implements
[29 Reporting System](29-reporting-system.md) §2–§3 and §5. Promotion decisions (§4) are
**out of scope**: the promotion rule is an open owner question in doc 29.

## 1. What a report card is

A report card is an **immutable, issued snapshot** for one learner and one period
(`period_start`, `period_end`, epoch seconds). Every figure is derived when the card is issued
from records that already exist, and nothing on it can be typed in:

- per subject, then per objective: the mastery state at `period_end` (`mastered` / `developing` /
  `not_started`), the count of auto-scored attempts in the period with how many were correct, and
  the homework outcomes in the period (`met` / `not_yet` counts);
- for every objective listed, the lesson id and **version** the work was actually done on (the
  curriculum version pin), plus the curriculum pack id. The pin is derived from the evidence the
  card counts for that objective in the period (its auto-scored attempts plus the evidence of the
  homework marks listed), as each evidence row recorded it when the learner answered: never the
  version published when the card is issued, so a republish or rollback in between changes
  nothing. Per objective:
  - one recorded version gives `lesson_version`; several give `lesson_versions: [..]`, sorted
    ascending (`lesson_versions` is always present, so one version is `[n]`);
  - `version_source` is `"evidence"` when every counted evidence row carries a version,
    `"unrecorded"` when none does (rows recorded before versions were, an offline attempt whose
    package named none, or no counted evidence row at all), and `"mixed"` otherwise;
    `unversioned_evidence` counts the rows without one. An unrecorded part is shown as such and is
    never silently replaced by the current published version;
  - `lesson_version` stays the single version when the pin is unambiguous (exactly one recorded
    version, one lesson id, `version_source: "evidence"`), for client compatibility; otherwise it
    is `null`. `lesson_id` is the one lesson id the evidence names (`null` when none or several;
    `lesson_ids` lists them);
  - the title and subject grouping still come from the lesson published at issue time (display
    only); an objective with no published lesson is grouped under `other`.

  This is body rule `derivation: "taleem.reporting.derive/2"`. Cards issued under
  `taleem.reporting.derive/1` (which pinned the version published at issue time) are never
  re-derived: they are returned exactly as stored and still verify against their stored hash;
- an optional teacher comment (≤ 1000 chars, the only free text, attributed to the teacher);
- `issued_by` (teacher ref), `issued_at`, `class_id`, `organization_id`, and a `content_hash`
  (sha256 of the canonical JSON body).

Corrections never edit a card. A teacher issues a new card for the same learner and period with
`supersedes = <card_id>`, and the old card is shown as *superseded*. A card with no evidence at all
is allowed but says so plainly. It never shows zeros as if they were results.

## 2. Issuing (teacher, human-accountable)

- `POST /v1/reporting/classes/{class_id}/report-cards:preview` with
  `{period_start, period_end, student_refs?}` returns the bodies that would be issued, without
  storing anything.
- `POST /v1/reporting/classes/{class_id}/report-cards` with
  `{period_start, period_end, student_refs?, comments?: {student_ref: text}, supersedes?: {student_ref: card_id}}`
  issues the cards. Only learners currently in that class with live consent are included; anyone
  else is listed in `skipped` with a reason. Issuing emits `ReportCardIssued` to the outbox and an
  in-app notification for the guardian.
- `period_end` must not be in the future, and `period_start < period_end`. Teachers act only on
  their own classes (other organizations get 404). Every issue is written to an audit log (refs
  only).

## 3. Reading

- Guardian: `GET /v1/reporting/children/{student_ref}/report-cards` lists cards (newest first)
  and `GET /v1/reporting/report-cards/{card_id}` returns one, only for their own child.
  `POST /v1/reporting/report-cards/{card_id}:acknowledge` records that the guardian has seen it
  (once; it returns `acknowledged_at`).
- Learner: `GET /v1/reporting/learners/{student_ref}/report-cards` returns their own cards. It has
  the same live consent gate as every learner surface.
- Teacher: the same list for a learner in their class.
- Every read returns the stored body and `content_hash`, and the server can re-verify the hash.
  The web app has a print-friendly view, so the card is "PDF-able" by printing.

## 4. Privacy

Report cards are C2 learning records (`reporting` schema, migration `0014`). Guardian export
includes them. Erasure deletes them, and the erasure completeness gate covers the new tables.
Retention stays disabled until M-Gov.

## Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-10-24 | Contract adopted: immutable issued snapshot, version pins, supersede-not-edit, teacher issue, guardian/learner read + acknowledge, privacy. | Engineering |
| 2026-10-24 | §1: the version pin is derived from the evidence (each evidence row records its lesson id + version, migration `0015`), `lesson_versions` / `version_source` / `unversioned_evidence` added, `derive/2`; `derive/1` cards stay verifiable. | Engineering |
