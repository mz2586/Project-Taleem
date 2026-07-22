# Content Standards

Status: **Phase 7 — Curriculum Production System. The "what good looks like" specification.** Defines
the production standards every lesson must meet, per dimension. These are the criteria the pipeline's
review gates ([CONTENT_PRODUCTION_PIPELINE.md](CONTENT_PRODUCTION_PIPELINE.md)) enforce and the QA
checklists ([QUALITY_ASSURANCE_CHECKLISTS.md](QUALITY_ASSURANCE_CHECKLISTS.md)) verify. Companion to
[CURRICULUM_FRAMEWORK.md](CURRICULUM_FRAMEWORK.md).

Overriding principle: **child safety first; quality never yields to schedule** (Engineering
Constitution). A standard breach in safety or accuracy is a hard block, not a trade-off.

---

## 1. Lesson quality

- **Teach before test:** an explanation + at least one worked example precede practice.
- **One coherent objective per lesson**, with the ten required fields complete (framework §6).
- **Difficulty is honest:** `INTRO`/`CORE`/`STRETCH` reflects genuine cognitive load, not length.
- **Item pool ≥ 5 distinct** per objective (mastery requires 4/5 distinct); items progress simple→hard;
  no item repeats within a mastery check.
- **Graduated hints** (H1 orient → H2 strategy → H3 worked re-teach → mentor) that **never reveal the
  answer before H3**.
- **Misconceptions** are named (ref + detector + correction); a wrong option maps to the correct
  misconception ref.
- **Homework** is one short, everyday, resource-light task tied to the objective.
- **Provenance:** `authored-original`, `[RE-EXPRESSED]` outcome, `aligned_slo_codes` set.

## 2. Language quality

- **Correct, natural, age-appropriate** language in a **simple child register** (not heavy literary
  Urdu, not adult English).
- **Bilingual integrity:** English support accurately conveys the Urdu meaning (not a literal
  mistranslation); terminology is consistent across lessons (a per-subject glossary).
- **Notation + numerals:** Eastern-Arabic numerals in Urdu-medium content (FD-15); correct RTL
  rendering; symbols written for correct spoken rendering (e.g. `۱/۴` → "ایک بٹا چار").
- **Clarity:** short sentences, active voice, direct address to the child ("آپ").

## 3. Urdu-first support

- **Urdu is primary; English is support.** Every student-facing string has an **Urdu narration**
  (audio-first) so a non-reader can complete a session by listening (per
  [AUDIO_SCRIPT_GUIDE.md](AUDIO_SCRIPT_GUIDE.md)).
- **Construct-validity exception:** where **reading itself is the assessed construct** (Urdu/English
  reading-comprehension items), the passage carries **no audio scaffolding** — audio would invalidate
  the measurement (master matrix §4.2). This is a per-item rule; audio-first applies everywhere else.
- **Captions** accompany every audio segment (accessibility).
- **Cultural fit:** examples, names, and contexts are familiar to Pakistani children.

## 4. Accessibility (WCAG 2.2 AA)

- **Every visual/media has meaningful `alt_text`** (localized; no faces/brands).
- **No reliance on color or sound alone** to convey meaning.
- **Text + audio + captions** are all present and consistent for each teaching string.
- **Usable by a non-reader** (audio path complete) **and a screen-reader user**; keyboard/AT operable.
- **Mobile-first + low-end-device friendly** touch targets and layout; readable at the Urdu minimum
  font size.

## 5. Assessment quality

- **Validity:** each item measures its objective's competency class; deterministic-answer items are
  auto-graded, constructed items are mentor-mediated.
- **Correctness:** exactly one defensible correct answer for auto-graded items; distractors are
  plausible (not trick answers) and, where useful, map to a named misconception.
- **Fairness:** no cultural/linguistic bias that disadvantages a learner unrelated to the construct.
- **Mastery discipline:** ≥ 5-item distinct pool; confirmed at ≥ 4/5; spaced re-check with distinct
  items; **summative is mentor-mediated — never auto-promotion.**
- **No answer keys on the device** — grading is server-side.

## 6. Difficulty progression

- **Within a lesson:** items ramp INTRO → CORE → STRETCH.
- **Within a unit:** lessons build on declared prerequisites; the unit is a coherent arc.
- **Across the year:** the prerequisite DAG has no gaps and no cycles; a learner never meets an
  objective before its prerequisites; the decision engine can sequence it deterministically.
- **Spacing:** mastered objectives re-surface on the forgetting schedule; difficulty of re-checks
  matches the original.

## 7. Parent guidance

- **Plain-language, Urdu-first** guidance per subject/grade (the [PARENT_GUIDE.md](PARENT_GUIDE.md)
  pattern): what the child is learning, how the AI-helper + human-mentor model works, and **2-minute,
  no-expertise-needed** ways to help at home.
- **Encouragement framing:** praise effort not cleverness; mistakes are normal; sessions short.
- **Rights + safety:** what data is collected (only what's needed; pseudonymous), consent, a human is
  always reachable, opt-out — no PII requests of the family.

## 8. Teacher guidance

- **Facilitation, not lecture** (the [TEACHER_GUIDE.md](TEACHER_GUIDE.md) pattern): mentors circulate,
  reinforce named misconception corrections in person, and **own the mentor-mediated summative**.
- **Misconception quick-reference** per subject (what to watch for, what to reinforce).
- **Safeguarding:** every distress/stuck escalation reaches a human within SLA; follow the safeguarding
  runbook; be present.
- **Feedback loop:** mentors log content issues, sticking points, engagement, accessibility, and safety
  — a primary input to the next production cycle.

---

## 9. Standards → pipeline gate → QA checklist map

| Standard | Enforced at (pipeline gate) | Verified by (QA §) |
| --- | --- | --- |
| 1 Lesson quality | Educational Review | Educational quality |
| 2 Language quality | Quality Review (Language) | Educational + Accessibility |
| 3 Urdu-first support | Quality Review (Language + Accessibility) | Accessibility + Offline |
| 4 Accessibility | Quality Review (Accessibility) | Accessibility |
| 5 Assessment quality | Educational Review | Educational quality |
| 6 Difficulty progression | Educational Review | Educational quality |
| 7 Parent guidance | Educational Review | Educational quality |
| 8 Teacher guidance | Educational Review | Educational quality |
| Child-safety (cross-cutting) | Child Safety Review | Child safety |
| Licensing/originality | Educational Review (subject-expert) | Licensing/originality |
| Offline/technical | Offline Packaging | Technical + Offline compatibility |

No lesson publishes until it meets **every** applicable standard; safety and accuracy are
non-negotiable.
