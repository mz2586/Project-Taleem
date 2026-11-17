> **AI-GENERATED DRAFT — NOT REVIEWED — NOT OFFICIAL CURRICULUM**
>
> These checklists are for reviewing Grade 4 AI first drafts. They were written with AI help and
> need sign-off from the curriculum architect before use. Ticking a box here approves nothing.
> Only an approval recorded in the Curriculum Studio counts.

# Grade 4 Reviewer Checklists

There is one checklist per Curriculum Studio review stage. The stages, roles and gates come from
[`domain/workflow.py`](../../../services/core-api/src/taleem_core/contexts/curriculum_studio/domain/workflow.py)
and `STAGE_GATES` in
[`application/service.py`](../../../services/core-api/src/taleem_core/contexts/curriculum_studio/application/service.py).
Each checklist names the standard behind it. They do not repeat those standards. The Mathematics
pilot has a more detailed per-lesson checklist,
[CONTENT_QA_CHECKLIST.md](../../../CONTENT_QA_CHECKLIST.md), and Mathematics reviewers use both.

| Order | Studio state | Role | Gates the approval certifies |
| --- | --- | --- | --- |
| 1 | `subject_expert` | `subject_expert` (for Islamiat: a qualified scholar) | `technical_accuracy` |
| 2 | `educational_qa` | `instructional_designer` | `educational_review`, `age_appropriateness` |
| 3 | `accessibility` | `a11y_specialist` | `accessibility` |
| 4 | `language` | `language_editor` | `language` |
| 5 | `ai_safety` | `safety_officer` (for the 8 safeguarding lessons: with the safeguarding reviewer) | `ai_safety` |

The other four gates (`curriculum_alignment`, `readability`, `performance`, and the automated part
of `accessibility`) are checked by the validator before a lesson can be submitted.

Rules for every stage:

- Five different people sign the five stages. Nobody reviews a lesson they authored or edited. The
  Studio refuses self-approval.
- Start with the flags routed to your lane in [REVIEW_TRACKER.md](REVIEW_TRACKER.md). Then do the
  whole checklist, because the flags are where to start, not the full extent of the review.
- Any failed check means **request changes**. The lesson goes back to `draft` with your note.
  Child-safety and accuracy failures cannot be waived.
- Write the review note as `Flags: F1 resolved, F3 resolved; Checklist: pass; Sources: …`. Use
  staff ids, never personal details.
- Do not edit `ai-drafts/*.json` to resolve a flag. Fixes go into the Studio draft through a
  subject author.

## 0. Provenance and licensing (every reviewer, every lesson)

Every reviewer confirms all of these before reviewing a lesson. If any one fails, request changes
and stop. Background: [master scope §6.4](../../../PROJECT_TALEEM_MASTER_SCOPE.md) and
[`curriculum-research/01`](../../../curriculum-research/01_CURRICULUM_RESOURCE_INVENTORY.md).

- [ ] The lesson text, items and examples are original. None is copied or closely paraphrased
      from a textbook, guide book, past paper or website. Government textbooks and curriculum
      documents are All Rights Reserved: being free to view does not make them free to reuse.
- [ ] The learning outcome is re-expressed in the lesson's own words. It is not verbatim NCP SLO
      text. Verbatim text needs an NCC/MoFEPT MoU, and there is none.
- [ ] Studio provenance is `authored-original`, with at least one `aligned_slo_codes` entry. Do
      not change it to `ingested`: that needs an open licence or a written `permission_ref`.
- [ ] No source, licence or note refers to a textbook scan or a prohibited repository. The
      validator refuses those (`PROHIBITED_SOURCE_MARKERS` in `domain/provenance.py`).
- [ ] Any image or diagram brief describes a new drawing. Nothing is traced or scanned from a
      published book.
- [ ] Anything you add to the lesson is your own writing. If you recognise drafted text from a
      published source, record the source in your note and request changes.
- [ ] Islamiat only: scripture text and translations supplied by the scholar come from an edition
      or translation whose licence allows reuse, or are the scholar's own translation. The note
      records which.

## 1. Subject expert: technical accuracy

Standard: [LESSON_STANDARD](../../../docs/10-curriculum-studio/LESSON_STANDARD.md),
[ASSESSMENT_STANDARD](../../../docs/10-curriculum-studio/ASSESSMENT_STANDARD.md). Flags: lane `SE`.

- [ ] `teacher_script`, `student_explanation`, `worked_examples` and `summary` are factually
      correct, and every step of every worked example is valid.
- [ ] Every auto-marked item (`practice_questions`, `challenge_problems`, `interactive_activities`)
      has exactly one defensible answer, and its `answer_key` and `accepted_variants` are right.
- [ ] `common_misconceptions` describe real Grade 4 errors, and each correction is true.
      Misconception ids that the reviewer guide marks as proposed are accepted or replaced.
- [ ] The content matches the objective's outcome, difficulty and prerequisites in
      [`spine.json`](../spine.json), and stays within Grade 4.
- [ ] Where the draft and the human design document differ, the flag says which is right, and the
      design document is corrected by an author if it is wrong.
- [ ] Facts that vary by place or time (prices, months, place names, emergency numbers) are
      verified or removed.

### Scholar addendum (all 16 Islamiat lessons)

The Studio has no scholar role. For Islamiat, the person approving the `subject_expert` stage must
be a qualified scholar, or the approval note must reference the scholar's written confirmation.
Flags: lane `Scholar`.

- [ ] Every placeholder of the form `[Verse: …]`, `[Hadith: …]` or `[… to be supplied by a
      scholar]` is filled with verified text and an approved translation, or removed. The tracker
      counts 7 of them across 6 lessons.
- [ ] Every reference (surah and verse, hadith source) is verified. Statements given without a
      citation are either cited or confirmed as needing none.
- [ ] Seerah accounts are accurate, suitably sourced and told gently for Grade 4.
- [ ] Wording is acceptable to Pakistani Muslim learners across schools of thought, and practice
      details that belong to family and teacher are left to them.
- [ ] Images: no depiction of the Prophet (peace be upon him), his family or companions, and no
      Qur'anic text inside an image.

## 2. Instructional designer: educational review and age-appropriateness

Standard: [LESSON_STANDARD](../../../docs/10-curriculum-studio/LESSON_STANDARD.md),
[ITEM_INTERACTION_CONTRACT](../../../docs/10-curriculum-studio/ITEM_INTERACTION_CONTRACT.md),
[HOMEWORK_AND_MARKING_CONTRACT](../../../docs/10-curriculum-studio/HOMEWORK_AND_MARKING_CONTRACT.md).
Flags: lane `ID`.

- [ ] The lesson teaches before it tests: explanation and a worked example come before practice.
- [ ] Items move from easier to harder, cover the objective and give a mastery pool of at least
      5 distinct items.
- [ ] `hints` are graduated and never give the answer before the last hint.
- [ ] Each activity uses an interaction kind the player supports (choose, fill, order, match,
      sort). For a bespoke widget, you have decided whether the lesson can be published without
      it, and recorded that in the note.
- [ ] For mentor-marked work, the rubric levels are usable in the mentor's time, and there is no
      photo or voice upload the product does not have.
- [ ] `homework` is short, possible without buying anything, and safe to do at home.
- [ ] Examples suit 9 to 10 year olds in Pakistan, including children in poorer, rural or
      disabled households. Nothing assumes a car, pocket money, running water or a private phone.
- [ ] `adaptive_remediation` points to the right objective, and `revision_notes` and `summary`
      match what was taught.

## 3. Accessibility specialist: accessibility

Standard: [ACCESSIBILITY_STANDARD](../../../docs/10-curriculum-studio/ACCESSIBILITY_STANDARD.md)
(WCAG 2.2 AA). Flags: lane `A11y`.

- [ ] Every diagram in `visual_concepts` exists and has localised alt text that conveys what the
      picture teaches.
- [ ] Recorded Urdu audio exists for every learner-facing string, with captions. Measured
      durations are real, not estimated.
- [ ] Nothing relies on colour or sound alone, and shaded parts also carry a pattern or label.
- [ ] Every activity can be done by tapping, with no drag required, and works with a screen
      reader.
- [ ] Right-to-left rendering is correct: `<`, `>`, arrows, minus signs, Urdu digits and tatweel
      do not flip or break.
- [ ] Item stems that describe a picture in words are short enough to listen to.
- [ ] The `accessibility_notes` items are done, not just noted.

## 4. Language editor: language

Standard: [TRANSLATION_STANDARD](../../../docs/10-curriculum-studio/TRANSLATION_STANDARD.md),
[CONTENT_STYLE_GUIDE](../../../docs/10-curriculum-studio/CONTENT_STYLE_GUIDE.md),
[AUDIO_SCRIPT_GUIDE](../../../AUDIO_SCRIPT_GUIDE.md) §5 (math terms). Flags: lane `LE`.

- [ ] The Urdu is correct and natural, in a simple child register rather than literary Urdu.
- [ ] The English says the same thing as the Urdu. Where one side is an AI translation of human
      text, it has been checked against the human side.
- [ ] Subject terms match NCP Grade 4 usage and stay the same across lessons. The tracker flags
      known clashes, for example باقی meaning both "difference" and "remainder".
- [ ] One-language list fields (`hints`, `homework`, `worked_examples`) have had their missing
      side written by a person. The AI drafts do not fill these.
- [ ] Numbers are written in the house style (Urdu digits in Urdu text), and fractions and symbols
      read correctly aloud.
- [ ] Names and greetings are inclusive across communities.

## 5. Safety officer: AI safety

Standard: [AI_TEACHING_STANDARD](../../../docs/10-curriculum-studio/AI_TEACHING_STANDARD.md),
[child-safety framework](../../../docs/03-security-privacy/15-child-safety-framework.md).
Flags: lanes `SO` and `Safeg.`.

- [ ] No learner-facing text asks for personal information: name, address, school, phone, photos
      or family details. The validator blocks addresses, house and phone numbers, and family ages.
      You check the rest.
- [ ] Nothing frightens, shames or pressures a child, including children who do not yet pray,
      cannot read, have little food or money, or have no safe home.
- [ ] Home activities are safe: nothing sharp, hot, electrical, deep water or fuel without an
      adult. The safety lines are clear enough for a child alone.
- [ ] `ai_teaching_object` has non-empty `forbidden_behaviours` and `escalation_rules`, routes
      distress to a mentor, and never claims the AI is a human.
- [ ] No brands, real private people, or politically or religiously divisive content.
- [ ] Respect, patience and forgiveness are never framed as hiding harm or obeying unsafe adults.

### Safeguarding addendum (8 Ethics lessons)

The lessons are HON-03, HON-04, KIN-03, KIN-04, REP-01, REP-04, RES-02 and RES-04, as listed in
the tracker under the `Safeg.` lane. The safeguarding reviewer approves these alongside the safety
officer, and the approval note references their confirmation.

- [ ] The trusted-adult, unsafe-secret, bullying and stranger wording follows safeguarding good
      practice: calm, never the child's fault, and telling is not tattling.
- [ ] The lesson does not invite a disclosure inside the app. The mentor disclosure procedure in
      `mentor_notes` matches the programme's procedure.
- [ ] Homework on these topics stays private and asks for no names.
