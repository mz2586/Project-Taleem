# Content Style Guide

| | |
|---|---|
| **Status** | Phase 3 · How Taleem content reads and looks · Related: [LESSON_STANDARD](./LESSON_STANDARD.md) · [17 UI Design System](../04-design/17-ui-design-system.md) |
| **Date** | 2026-07-20 |

## 1. Voice & tone

Warm, encouraging, calm, never patronising ([Authoring Brief §7](../_meta/authoring-brief.md)). Speak
*to* the child ("you can do this"). Short sentences. Concrete before abstract. Celebrate effort, not just
correctness. Never shame a wrong answer.

## 2. Readability (grade-banded, machine-checked)

| Grade band | Sentence length (avg words) | New vocabulary/lesson | Notes |
|---|---|---|---|
| KG / 1–3 | ≤ 8 | ≤ 5 | mostly audio + image; minimal decode load |
| 4–5 | ≤ 12 | ≤ 8 | |
| 6–8 | ≤ 16 | ≤ 10 | |
| 9–10 | ≤ 20 | ≤ 12 | |

The readability gate ([QA §2](./QUALITY_ASSURANCE_STANDARD.md)) computes avg sentence length + vocabulary
load per lesson and fails if outside the band. Urdu readability uses an Urdu-aware metric (not English
formulas).

## 3. Writing rules

- **Plain language**; define every new term in `vocabulary` with pronunciation audio.
- **Icon + text**, never icon-only ([16](../04-design/16-accessibility-standards.md)).
- **Worked examples** show every step; no leaps.
- **Hints are graduated** — nudge → strategy → near-answer; never the answer first.
- **Culturally grounded, neutral** on religion and gender; inclusive, respectful examples; names and
  contexts from across Pakistan.
- **No dark patterns**, no fear-based motivation.

## 4. Visual & media style

- SVG/diagrams: simple, high-contrast (token palette, [59 Token Values](../04-design/59-design-token-values.md)),
  labelled, alt-texted. **Sun `#F59E0B` never carries text.**
- Images optimised to budget (≤ 60 KB typical); lite variants; original or CC0 only — **never copyrighted
  textbook images**.
- Audio: clear, paced for the grade; Urdu-first; transcript always available.
- Numerals per pedagogical context — Eastern-Arabic ۰-۹ in Urdu-medium early math ([FD-15](../../FOUNDER_DECISIONS.md)).

## 5. Structure conventions

- Summary ≤ 5 points. Revision notes scannable. Parent notes ≤ 3 sentences, plain.
- One clear primary action per screen ([16 §9](../04-design/16-accessibility-standards.md)).

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-20 | Content style guide: voice/tone, grade-banded readability, writing rules, visual/media style, structure conventions. | Curriculum Studio |
