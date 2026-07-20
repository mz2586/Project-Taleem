# Accessibility Standard (Curriculum Content)

| | |
|---|---|
| **Status** | Phase 3 · A11y rules for authored content · Related: [16 Accessibility](../04-design/16-accessibility-standards.md) · [59 Token Values](../04-design/59-design-token-values.md) |
| **Date** | 2026-07-20 |

## 1. Bar

**WCAG 2.2 AA is the floor**, plus WCAG **COGA** (cognitive accessibility) guidance for child/low-literacy
users, RTL-complete Urdu, and usable on a 360px low-end screen. Content that excludes a category of
children fails the accessibility gate ([QA gate 5](./QUALITY_ASSURANCE_STANDARD.md)).

## 2. Per-lesson requirements (machine + human checked)

| Requirement | Check |
|---|---|
| **Recorded Urdu audio** on all core-path text | auto: audio ref present; human: quality |
| **Alt text** on every image/diagram/visual concept | auto: non-empty; human: meaningful |
| **Captions/transcript** on all audio/video | auto: present |
| **Contrast** meets AA (use semantic tokens only) | auto: token-valid ([59](../04-design/59-design-token-values.md)) |
| **Never colour-only** signalling | human |
| **RTL-complete** Urdu; correct bidi for mixed math/English | human + visual regression |
| **Minimum type size** (18px Urdu floor) | auto |
| **Touch targets ≥ 44px** in interactives | auto |
| **Reading vs listening** — audio does not scaffold a *reading* assessment (validity) | human |
| **Screen-reader operable** in Urdu + English | human (assistive-tech pass) |
| **Low-literacy** — icon+text, plain language, audio-first navigation | human |

## 3. Multi-modal rule

Content must degrade to **each** sensory channel: audio-first for non-readers **and** text/alt for the
deaf/hard-of-hearing **and** screen-reader/labels for the blind. No single modality may be the only path
to an activity (reconciles audio-first vs icon-first — [16](../04-design/16-accessibility-standards.md)).

## 4. Disability considerations

- Low vision: high-contrast theme support; scalable text; no thin-stroke-only Nastaʿlīq at small sizes.
- Motor: large targets; no precise-timing-only interactions.
- Cognitive: short steps, consistent patterns, "how this screen works" affordance, reduced motion honoured.

## 5. Validation

The accessibility gate runs automated checks (alt text, audio presence, contrast tokens, type size, target
size) on `:validate`, then an a11y specialist reviews the human criteria before approval. Real-device +
assistive-tech validation is required before the content ships to children (EV-05/06,
[EXTERNAL_VALIDATION_CHECKLIST](../../EXTERNAL_VALIDATION_CHECKLIST.md)).

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-20 | Content accessibility standard: AA+COGA bar, per-lesson checks, multi-modal rule, disability considerations, validation. | Curriculum Studio |
