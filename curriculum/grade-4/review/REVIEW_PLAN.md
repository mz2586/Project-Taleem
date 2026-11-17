> **AI-GENERATED DRAFT — NOT REVIEWED — NOT OFFICIAL CURRICULUM**
>
> This plan covers 139 Grade 4 AI first drafts that no human has reviewed. The plan itself was
> written with AI help and needs sign-off from the curriculum architect before it is used.

# Grade 4 Review Plan

This is the order of work for the human review of the Grade 4 AI drafts. It does not repeat the
[reviewer guide](../ai-drafts/README.md), which explains the draft format, the import rules and the
known problems in the human-authored sources.

| File | What it is |
| --- | --- |
| [REVIEW_TRACKER.md](REVIEW_TRACKER.md) | Generated. Every objective with its status, open flags, review lane and sign-offs |
| [review_flags.csv](review_flags.csv) | Generated. One row per flag, with empty reviewer, decision and date columns |
| [REVIEWER_CHECKLISTS.md](REVIEWER_CHECKLISTS.md) | What each Studio role checks, plus the provenance check every reviewer confirms |
| [`curriculum_review_tracker.py`](../../../services/core-api/src/taleem_core/tools/curriculum_review_tracker.py) | The generator. `--check` fails when the two generated files are stale |

All counts below come from the tracker (generated 2026-11-17 from the committed drafts).

## 1. Where things stand

- 139 objectives, each with one AI draft, all `ai-draft-unreviewed`. No lesson has left `draft`.
- 361 open review flags: Mathematics 82, Urdu 46, English 46, Science 44, Social Studies 52,
  Islamiat 48, Ethics 43.
- All 16 Islamiat lessons need a scholar (7 scripture placeholders). 8 Ethics lessons need the
  safeguarding reviewer.
- 21 activities are bespoke widgets with no learner runtime, and 3 flags block release until audio
  is recorded.

### The Studio cannot take these lessons into review yet

The Studio validator blocks `:submit` on all 139 drafts because each one lacks `visual_concepts`
and an `offline_package` (see [INGESTION_REPORT.md](../INGESTION_REPORT.md), "Submission
blockers"). The accessibility gate also needs recorded Urdu audio. So the review runs in two
passes:

1. **Pass A, content pre-review (can start now).** Reviewers read the drafts and the tracker,
   work through the flags in their lane and record each decision in a copy of `review_flags.csv`.
   Fixes are made by a subject author in the Studio draft, never in the `ai-drafts/*.json` files.
   The ingest never overwrites a field a person has edited in the Studio. Pass A records no
   approval and changes no status.
2. **Pass B, formal Studio review (after the assets exist).** Once a lesson has its diagrams, alt
   text, recorded Urdu audio and offline package, the author submits it. It then goes through the
   five stages in order, each approved by a different person who did not author it. Only Pass B
   counts. A lesson is reviewed only when the Studio records all five approvals.

Pass A means Pass B should mostly be confirmation, not discovery.

## 2. Recommended first subject: Mathematics

Phase B is accepted when at least one complete Grade 4 subject is published with all 9 gates green,
`authored-original` provenance, end-to-end rendering in the student portal, and verified offline
packages ([master scope §21](../../../PROJECT_TALEEM_MASTER_SCOPE.md)). Mathematics should be
that subject.

Reasons:

- **It is the pilot subject.** The pilot curriculum is Grade 4 Mathematics
  ([MASTER_EXECUTION_PLAN.md](../../../MASTER_EXECUTION_PLAN.md),
  [LESSON_CATALOG.md](../../../LESSON_CATALOG.md)), and the
  [content QA checklist](../../../CONTENT_QA_CHECKLIST.md) is already written for it. No other
  subject meets Phase B and the pilot at the same time.
- **It has the most human writing.** All 31 Mathematics objectives carry human-authored content
  from [`GRADE4_MATH_CURRICULUM.md`](../../../GRADE4_MATH_CURRICULUM.md). In the other subjects
  only the one exemplar per track does. The drafts fill gaps around human text instead of standing
  alone.
- **It has the lowest sensitivity load.** It has no scholar or safeguarding flags, no
  mentor-mediated objectives and no audio blockers. Its flags sit with the subject expert (45),
  the language editor (19), the instructional designer (14) and accessibility (4). Answers can be
  checked objectively.
- **The groundwork exists.** The misconception library is in the Mathematics design document
  (§4), and the one end-to-end lesson fixture is a Mathematics lesson (FR-01,
  `vertical_slice/fractions_lesson.py`).

What makes Mathematics harder:

- **It is the largest subject.** It has 31 objectives in 8 units and 82 flags.
- **13 of the 21 widget activities are Mathematics activities** (carry boxes, arrays, clock hands,
  bar shading). The instructional designer decides, lesson by lesson, whether the lesson can be
  published without its activity until a widget runtime exists, or must wait.
- **The human source has errors that need an author before review.** The reviewer guide lists
  them: the `m-unit-mix` correction attached to mass and capacity, the reversed
  `m-bigger-number-more-digits-always` wording, and the GE-01 and DA-01 worked examples, which are
  instructions to authors rather than scripts.
- **One-language fields need an author.** List fields keep the language the human wrote them in.
  In Mathematics, `hints` are Urdu only in 27 lessons and `homework` is English only in 30 (from
  the ingestion report). A person writes the missing side. The AI drafts do not fill it.

**Fallback.** If a Mathematics subject expert cannot be found quickly, start with General
Science instead. It has 20 objectives, the fewest flags per objective (2.2), 1 widget and no
audio blockers. Science alone does not unblock the pilot.

**Do not start with Islamiat or Ethics.** They form one Studio subject (`islamiat_ethics`, 32
objectives), so neither is complete without the other. Islamiat needs a scholar for all 16
lessons. Ethics needs a safeguarding reviewer, and the safeguarding gate (M-Safe) is not closed.

## 3. Review order

| # | Subject | Objectives | Flags | Why here |
| --- | --- | --- | --- | --- |
| 1 | Mathematics (`math`) | 31 | 82 | Phase B and the pilot (above) |
| 2 | General Science (`science`) | 20 | 44 | Lowest flag density, mostly factual checks; 5 safety-officer flags on home activities |
| 3 | English (`english`) | 20 | 46 | 8 mentor-mediated objectives; 2 listening lessons wait for audio |
| 4 | Urdu (`urdu`) | 20 | 46 | 9 mentor-mediated objectives; URD-LS-01 cannot run until its story is recorded |
| 5 | Social Studies (`social_studies`) | 16 | 52 | Highest flag density (3.2), regional and cultural balance, 6 widgets |
| 6 | Islamiat + Ethics (`islamiat_ethics`) | 32 | 91 | Needs a scholar (16 lessons) and the safeguarding reviewer (8 lessons) |

Within a subject:

1. Review unit by unit in tracker order. That follows the prerequisite chain, so a reviewer never
   approves a lesson whose prerequisite still changes.
2. Review the exemplar ★ lessons of a unit first. They set the vocabulary and house style the
   other lessons follow.
3. Within a lesson, clear the flags in Studio stage order: subject expert, instructional designer,
   accessibility, language editor, safety officer. The tracker's "By lane" column shows who has
   work on each lesson.

## 4. Mathematics: before Pass A starts

1. **Staff five people**, one per Studio role (`subject_expert`, `instructional_designer`,
   `a11y_specialist`, `language_editor`, `safety_officer`), plus at least one `subject_author` to
   make the fixes. Nobody may review a lesson they edited. The Studio refuses it.
2. **Get the source errors fixed by an author** in `GRADE4_MATH_CURRICULUM.md`, then re-run the
   ingest. The list is in the [reviewer guide](../ai-drafts/README.md).
3. **Make the widget decision** for the 13 Mathematics widget activities (instructional designer
   and curriculum architect).
4. **Order the assets** that Pass B needs for all 31 lessons: diagrams with alt text, recorded
   Urdu audio and offline packages.
5. **Give every reviewer** the [provenance check](REVIEWER_CHECKLISTS.md#0-provenance-and-licensing-every-reviewer-every-lesson)
   before their first lesson.

Mathematics is done when all 31 lessons are `published` in the Studio with all 9 gates green and
the Phase B acceptance checks pass. Until then, report it as "in review", never as reviewed.

## 5. Keeping the tracker in sync

From `services/core-api`:

```sh
python -m taleem_core.tools.curriculum_review_tracker          # regenerate after a draft changes
python -m taleem_core.tools.curriculum_review_tracker --check  # exit 1 if stale
```

`tests/test_curriculum_review_tracker.py` fails the build when the committed tracker does not
match the drafts. The tracker shows the state of the AI drafts. It cannot show a review, because
review decisions live only in the Studio workflow.
