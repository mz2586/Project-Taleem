# Quality Assurance — Validation Checklists

Status: **Phase 7 — Curriculum Production System. The pass/fail gates before a grade is declared
production-ready.** Six validation checklists covering educational quality, accessibility, technical
compatibility, offline compatibility, child safety, and licensing/originality. These operationalize
[CONTENT_STANDARDS.md](CONTENT_STANDARDS.md) and extend the per-lesson
[CONTENT_QA_CHECKLIST.md](CONTENT_QA_CHECKLIST.md) (Grade 4 Math) to any grade/subject.

**Rules:** run per lesson **and** per grade package. **Child safety (§5)** and **educational accuracy
(§1)** are hard blockers — no waiver. Record pass/fail + reviewer + date; any fail → fix → re-review.

---

## 1. Educational quality

- [ ] Learning outcome present, `[RE-EXPRESSED]`, NCP-domain-aligned (not verbatim SLO text).
- [ ] Teaches before it tests (explanation + worked example precede practice).
- [ ] Difficulty (`INTRO`/`CORE`/`STRETCH`), prerequisites, and duration set and sensible for the grade.
- [ ] Item pool ≥ 5 distinct per objective; items ramp simple→hard; no repeat within a mastery check.
- [ ] Every worked example is correct + complete; every auto-graded item has exactly one defensible
      answer; distractors plausible; misconception refs correct.
- [ ] Graduated hint ladder present; never reveals the answer before H3; escalates to a mentor.
- [ ] Constructed items flagged formative / mentor-mediated (never auto-promoted).
- [ ] Homework is one short, everyday, resource-light task tied to the objective.
- [ ] Prerequisite DAG for the unit/year has no gaps and no cycles.

## 2. Accessibility (WCAG 2.2 AA)

- [ ] Every visual/media has meaningful localized `alt_text` (no faces/brands).
- [ ] Nothing relies on color or sound alone.
- [ ] Text + audio + captions present and consistent for each teaching string.
- [ ] Usable by a non-reader (audio path complete) and a screen-reader user; AT/keyboard operable.
- [ ] Mobile-first, low-end-device friendly; readable at the Urdu minimum font size; RTL correct.
- [ ] Reading-construct items correctly carry **no audio scaffolding** (validity), while all other
      content is audio-first.

## 3. Technical compatibility

- [ ] The lesson maps onto the existing `Lesson` / `LessonView` / `ItemView` model with **no schema
      change** (mirrors `fractions_lesson.py`).
- [ ] `provenance` = `authored-original` with `aligned_slo_codes`; objective code follows
      `SUBJ-G<grade>-<DOMAIN>-NN`.
- [ ] Passes the platform's data gates: no new child-data tables; pseudonymous `student_ref` only.
- [ ] Renders correctly in the Student Portal (today/session/homework/progress) and derived read models.
- [ ] Publishes cleanly through the Curriculum Studio workflow (Draft → … → Published) with a complete
      transition history.

## 4. Offline compatibility

- [ ] The lesson packages fully into an offline package (content JSON + audio + captions + visuals).
- [ ] The package is **content-hashed and Ed25519-signed** (6.2C-1); the client verifies signature +
      hash before install.
- [ ] **No answer keys** in the offline content (prompts/options/hints only; grading server-side).
- [ ] Plays end-to-end **offline** on a low-end device; attempts queue and sync as durable evidence
      with no double-count (6.2B).
- [ ] Package size within budget; audio speech-optimized; graceful "audio not available" if missing.

## 5. Child safety (zero tolerance)

- [ ] No request for personal information (name, location, contacts, photos).
- [ ] No brands, real people, faces, logos, or violent content.
- [ ] No frightening, shaming, or pressuring language; mistakes handled kindly.
- [ ] Culturally + religiously safe and respectful for Pakistani children; sensitive subjects (Social
      Studies, Islamiat/Ethics) explicitly safety-cleared, with the correct religious track.
- [ ] AI teaching uses **approved content only** (templated; no generative LLM to children); never
      claims to be a human teacher.
- [ ] Distress/confusion escalates to a mentor within SLA; no dead ends; no infinite hint loops.

## 6. Licensing / originality

- [ ] Content is `authored-original` — not copied from any textbook or third party.
- [ ] Learning outcomes are `[RE-EXPRESSED]`, **not verbatim** government/NCP SLO text.
- [ ] No third-party images, passages, audio, or trademarks without a cleared licence (default: none —
      original assets only).
- [ ] Any external reference (e.g. a public fact) is common knowledge, verifiable, and not reproduced
      verbatim from a copyrighted source.
- [ ] Provenance + attribution recorded for every asset.

---

## 7. Grade-package sign-off (whole grade, before "production-ready")

- [ ] Every core subject's units + objectives are authored to the framework contract.
- [ ] Every lesson passes checklists §1–§6.
- [ ] The cross-subject year plan is coherent (no contradictions; literacy load reasonable).
- [ ] Every published lesson has a signed offline package verified on the pilot device model.
- [ ] Parent + teacher guides exist for the grade; misconception quick-references complete.
- [ ] Educational review + child-safety review are **signed** for the grade (the M-Content gate).
- [ ] A dated sign-off record is filed (approver + date) per subject and for the grade as a whole.

---

## 8. Sign-off record (per lesson / per subject)

| Checklist | Owner role | Pass/Fail | Reviewer | Date |
| --- | --- | --- | --- | --- |
| 1 Educational quality | subject_expert + instructional_designer | | | |
| 2 Accessibility | a11y_specialist | | | |
| 3 Technical compatibility | engineering + subject_expert | | | |
| 4 Offline compatibility | engineering + a11y_specialist | | | |
| 5 Child safety | safety_officer | | | |
| 6 Licensing/originality | subject_expert | | | |

**Publish decision:** publishable only when §1–§6 all pass; §1 and §5 are hard blockers. Record the
final GO/NO-GO, approver, and date.
