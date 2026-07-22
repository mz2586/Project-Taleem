# Content QA Checklist — Grade 4 Mathematics Pilot

Status: **Quality gate (WS4/WS5/WS10). Plan only.** The sign-off checklist every lesson, item, audio
segment, and visual must pass **before publish** for the Grade 4 Mathematics pilot. It operationalizes
the quality bar in the [curriculum](GRADE4_MATH_CURRICULUM.md) §0 and the master matrix §6, and the
child-safety non-negotiables from [MASTER_EXECUTION_PLAN.md](MASTER_EXECUTION_PLAN.md) §2.

**Nothing ships to a child until every applicable box is checked and signed off.** A single failed
child-safety or accuracy item is a **blocker** — quality never yields to schedule (Engineering
Constitution).

---

## How to use

- Run this per **lesson** (covers its items, audio, visuals, homework).
- Each section lists the check and its **owner role** (who signs off): **SME** (subject-matter/maths),
  **EdReview** (educational/pedagogy), **Lang** (Urdu language/translation), **Access** (accessibility),
  **Safety** (child-safety/safeguarding), **Audio** (narration/production).
- Record pass/fail + reviewer + date per lesson. Any fail → fix → re-review. No waivers on §2/§6.

---

## 1. Curriculum alignment + provenance (SME, EdReview)

- [ ] Learning outcome is present and `[RE-EXPRESSED]` — **not verbatim** government/NCP SLO text.
- [ ] Outcome aligns to the intended NCP Grade 4 Mathematics domain.
- [ ] Content is `authored-original` (not copied from any textbook or third party).
- [ ] `provenance` records derivation + `aligned_slo_codes`; objective code follows the scheme
      (`MATH-G4-<domain>-NN`).
- [ ] Difficulty, prerequisites, and estimated duration are set and sensible for Grade 4.
- [ ] Prerequisites match the dependency map in [LESSON_CATALOG.md](LESSON_CATALOG.md) §4.

## 2. Child safety + appropriateness (Safety) — ZERO TOLERANCE

- [ ] No content asks the child to reveal personal information (name, location, contacts, photos).
- [ ] No brands, real people, faces, logos, political/religious-sensitive or violent content.
- [ ] No frightening, shaming, or pressuring language; mistakes are handled kindly.
- [ ] No open-ended free-text that could surface unsafe input from a child in the pilot scope.
- [ ] AI teaching uses **approved lesson content only** (templated) — no generative LLM to children.
- [ ] The lesson never claims the AI is a human teacher; escalation-to-human path is intact.
- [ ] Any distress/confusion escalation routes to a mentor (no dead ends, no infinite hint loops).
- [ ] Culturally safe + inclusive for Pakistani children (context, names, examples, imagery).

## 3. Mathematical accuracy (SME)

- [ ] Every worked example is arithmetically correct and complete (each step valid).
- [ ] Every practice/assessment item has exactly one defensible correct answer (for auto-graded items).
- [ ] `correct_option` is right for every item; distractors are plausible, not trick answers.
- [ ] Each wrong option that maps to a misconception uses the **correct** `option_misconception` ref.
- [ ] Misconception corrections are mathematically true and match the §4 library.
- [ ] Numerals, units, and notation are correct and consistent (Eastern-Arabic in Urdu, FD-15).

## 4. Pedagogy + item quality (EdReview)

- [ ] The lesson teaches before it tests (explanation + worked example precede practice).
- [ ] Item pool has **≥ 5 distinct items** per objective (mastery requires 4/5 distinct).
- [ ] Items progress from simpler to harder; no item repeats within a mastery check.
- [ ] Hint ladder is graduated (H1 orient → H2 strategy → H3 worked re-teach) and **never** reveals the
      answer before H3.
- [ ] Homework is one short, doable, everyday task tied to the objective.
- [ ] Revision triggers are declared and point to the right objective/misconception.
- [ ] Constructed-response items are flagged formative/mentor-mediated (never auto-promoted).

## 5. Urdu-first language quality (Lang)

- [ ] Urdu text is correct, natural, and in a simple child register (not heavy literary Urdu).
- [ ] English support text is accurate and matches the Urdu meaning (not a literal mistranslation).
- [ ] Math terms match the [audio guide](AUDIO_SCRIPT_GUIDE.md) §5 glossary (consistent across lessons).
- [ ] Fractions/symbols are written for correct spoken rendering (`۱/۴` → "ایک بٹا چار").
- [ ] RTL rendering is correct; no broken mixed-script or numeral direction.

## 6. Audio layer (Audio, Lang, Access)

- [ ] Every student-facing string has an Urdu narration segment (audio-first; closes PRR B4).
- [ ] Segments are one-idea, correctly ordered, and tagged with role/order (per audio guide §2).
- [ ] Reading speed, tone, and pauses meet the voice spec (~90–110 wpm; warm, unhurried).
- [ ] Narration reads meaning, not markup; numerals spoken in Urdu words.
- [ ] Captions (`.vtt`) exist for **every** segment; `measured_duration_ms` filled after recording
      (not fabricated).
- [ ] Audio assets meet the format/naming/loudness spec and are packaged in the lesson's
      `offline_package`.
- [ ] No background music under speech; no startling sounds; no named person/brand in audio.

## 7. Accessibility (Access) — WCAG 2.2 AA

- [ ] Every visual/media has meaningful `alt_text` (localized; no faces/brands).
- [ ] Nothing relies on color or sound alone to convey meaning.
- [ ] Text + audio + captions are all present and consistent for each teaching string.
- [ ] Content is usable by a non-reader (audio path complete) and by a screen-reader user.
- [ ] Touch targets/layout assumptions are mobile-first and low-end-device friendly.

## 8. Offline + mobile (Access, SME)

- [ ] The lesson packages fully into `pkg/…` (text + audio + captions + visuals).
- [ ] The lesson plays end-to-end **offline** on a low-end device (verified in Pilot 0).
- [ ] Package size is within the pilot budget; audio is speech-optimized.
- [ ] Graceful degradation: if a media asset is missing, the surface shows an honest state (e.g.
      "audio not available"), never a silent failure or crash.

## 9. Platform-fit (SME) — no model changes

- [ ] The lesson maps onto the existing `Lesson` / `LessonView` / `ItemView` fields **without** any
      schema change (mirrors `fractions_lesson.py`).
- [ ] `offline_package`, `aligned_slo_codes`, hints, `option_misconceptions`, and corrections all
      populate existing fields.
- [ ] No new backend, frontend, auth, governance, or infra dependency is introduced by the content.

---

## 10. Sign-off record (per lesson)

| Section | Owner | Pass/Fail | Reviewer | Date |
| --- | --- | --- | --- | --- |
| 1 Alignment + provenance | SME + EdReview | | | |
| 2 Child safety | Safety | | | |
| 3 Math accuracy | SME | | | |
| 4 Pedagogy + items | EdReview | | | |
| 5 Urdu language | Lang | | | |
| 6 Audio | Audio + Lang | | | |
| 7 Accessibility | Access | | | |
| 8 Offline + mobile | Access + SME | | | |
| 9 Platform-fit | SME | | | |

**Publish decision:** a lesson is publishable **only** when sections 1–9 all pass. Sections **2
(safety)** and **3 (accuracy)** are hard blockers with no waiver. Record the final GO/NO-GO, the
approver, and the date.

---

## 11. Batch-level gates (whole curriculum, before pilot)

- [ ] All 31 teaching lessons + 8 revision + 1 summative pass sections 1–9.
- [ ] Every objective has its ≥ 5-item distinct pool authored and reviewed.
- [ ] The 15-entry misconception library is complete, and every detector/correction is used correctly.
- [ ] 100% of segments have Urdu audio + captions; offline playback verified for every package.
- [ ] The mentor-mediated summative is assembled and its constructed items flagged for human review.
- [ ] Educational review + child-safety review are **signed** (M-Content gate,
      [ROADMAP.md](ROADMAP.md)).
