# Translation & Localization Standard

| | |
|---|---|
| **Status** | Phase 3 · Urdu-first localization of curriculum content · Related: [CONTENT_STYLE_GUIDE](./CONTENT_STYLE_GUIDE.md) · [16 Accessibility](../04-design/16-accessibility-standards.md) |
| **Date** | 2026-07-20 |

## 1. Principle

**Urdu-first, English-second.** Content is authored so both languages are *native-quality*, not one a
literal translation of the other. Additional languages (Sindhi, Pashto, Punjabi, Balochi) are first-class
data later, via the localization pipeline.

## 2. Every localized field carries

```json
{ "ur": { "text": "...", "audio_ref": "...", "reviewed_by": "language_editor", "status": "approved" },
  "en": { "text": "...", "audio_ref": "...", "reviewed_by": "language_editor", "status": "approved" } }
```

- **Both `ur` and `en` required** for core-path text before publish (language gate).
- **Recorded audio** required for the primary medium (Urdu mandatory; audit AR-C-19).
- **Parity check:** the two languages must convey the same learning content (not diverge in meaning).

## 3. Rules

- **Native Urdu**, not translationese; correct Nastaʿlīq; register appropriate to the grade.
- **Bidi/mixed-script**: Latin words, numerals, and math expressions inside Urdu text use correct bidi
  isolation; math rendering has an explicit RTL spec ([16 §6](../04-design/16-accessibility-standards.md)).
- **Numerals** per pedagogical context — Eastern-Arabic ۰-۹ in Urdu-medium early math; Western for IDs/
  board-facing ([FD-15](../../FOUNDER_DECISIONS.md)).
- **Terminology glossary** — consistent Urdu terms for "objective", "mastery", "cohort", finalised with
  educators so they read naturally, not as jargon.
- **Culturally grounded** examples that work in both languages; no untranslatable idioms in core text.

## 4. Pipeline (for scale)

Strings are externalized (no hardcoded copy); a translation-management workflow with **native-educator
review** governs each language; ICU message format for plurals/gender; pseudo-localization in CI to catch
layout breakage. Per-language font + shaping + TTS + recorded-audio requirements are validated before a
language is enabled.

## 5. Validation (language gate)

Rejects content where: a required language is missing/unreviewed; audio is missing for the primary medium;
the parity check fails; or bidi/numeral rules are violated. Human language editors (Urdu + English) approve
before the language gate passes.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-20 | Translation standard: Urdu-first parity model, localized-field schema, bidi/numeral/terminology rules, localization pipeline, language-gate validation. | Curriculum Studio |
