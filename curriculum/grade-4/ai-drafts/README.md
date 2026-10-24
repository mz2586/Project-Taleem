# Grade 4 AI drafts — reviewer guide

**Status:** first drafts written by an AI model on 2026-10-24. **No human has reviewed them.**
They are not curriculum. No child sees them until a lesson passes the 5-stage human review and
has recorded Urdu audio.

There is one JSON file per Grade 4 objective (139). The format and import rules are in
[`tools/curriculum_ai_drafts.py`](../../../services/core-api/src/taleem_core/tools/curriculum_ai_drafts.py).
The ingest
([`INGESTION_REPORT.md`](../INGESTION_REPORT.md)) imports them into the Studio drafts with these
rules:

- Human-authored text in the design documents always wins. A draft fills only fields the documents
  leave empty, plus the missing language of a text field the documents wrote in one language only.
- Every lesson the drafts touch is tagged `ai-drafted` and
  `content-status:ai-draft-pending-review`, plus `ai-drafted-field:<name>` for each field. The
  report marks those fields **(AI)**.
- Lessons stay in `draft` and no gate result is recorded. Provenance stays `authored-original`:
  the drafts are original writing, with no textbook text.
- After a reviewer edits a field in the Studio, re-running the ingest never overwrites it.

## Where to start

1. Each file's `review_flags` lists the checks a reviewer should make first. There are 361
   flags in total.
2. **Islamiat (16):** every lesson needs a scholar's review. The drafts contain no Qur'anic Arabic,
   verse translation, hadith wording or du'a text. Wherever scripture is needed there is a marked
   placeholder for a scholar to fill (AKH-03, AKH-04, IBA-04, QUR-02, QUR-03, QUR-04).
3. **Safeguarding:** the Ethics lessons HON-03, HON-04, KIN-03, KIN-04, RES-02, RES-04, REP-01
   and REP-04 cover trusted adults, unsafe secrets, bullying and strangers. They need the
   safeguarding reviewer.
4. **Urdu terminology:** every subject flags school terms to confirm against NCP Grade 4 usage.

## Problems found in the human-authored sources (not changed here)

The importer keeps human text exactly as written, so these need an author:

- `GRADE4_MATH_CURRICULUM.md` §4: the correction for `m-unit-mix` says "1 m = 100 cm". It is
  attached to the mass and capacity lessons too (ME-02, ME-03), where it is wrong.
  `m-graph-scale-ignored` talks about bar squares and doesn't fit pictographs (DA-01).
- Math: ME-01's worked example is in Urdu only. The worked examples for GE-01 and DA-01 are
  instructions to authors, not scripts. ML-02's parent note is English text written with Urdu
  digits, so the importer treats it as the Urdu side.
- Fixed 2026-10-24: math homework that asked for a house number (NB-01) and family members' ages
  (NB-03) was reworded to page numbers and prices. The Studio validator now blocks any lesson
  whose learner-facing text asks for a home address, house or phone number, or family ages
  (`domain/safety.py`), and a test scans every Grade 4 lesson for this.
- Math NB-03: the wording of `m-bigger-number-more-digits-always` is the reverse of the error that
  its correction fixes.
- List fields (hints, worked examples) written in one language stay in that language. Drafts fill
  the missing side only for plain text fields. ENG-G4-GR-03's hints, for example, are Urdu only.
- New misconception ids are proposed but not yet in the libraries: `m-unequal-parts`,
  `m-ray-segment`, `m-square-rectangle`.

## Limits of the current product that affect these lessons

- Every auto-graded item follows
  [`ITEM_INTERACTION_CONTRACT.md`](../../../docs/10-curriculum-studio/ITEM_INTERACTION_CONTRACT.md):
  choose, fill, order, match or sort. `practice_questions` are all choose items. Activities use
  the other kinds and are played before practice. 21 bespoke activities (clock hands,
  place-value mats, arrays, shading) remain *widgets*: they are not played until a widget runtime
  exists, and each one is flagged.
- Listening lessons (URD-LS-01, ENG-LS-01, ENG-LS-02) have no audio. A mentor reads the script in
  `mentor_notes` aloud until a recording exists.
- Writing and speaking work is marked by a mentor with the drafted rubrics. There is no
  handwriting or voice capture.
- No lesson has `visual_concepts` or an `offline_package`. Each `accessibility_notes` says which
  diagram and alt text are still to be made.
