# Audio Script Guide — Urdu Audio Layer (Grade 4 Math Pilot)

Status: **Content/production spec (WS5). Plan + production-ready scripts only.** No synthetic audio is
generated here; this document specifies **how** the Urdu narration is written, segmented, timed, and
packaged so a human narrator (or, later, an approved neural-TTS pass under review) can record
production audio for the [Grade 4 Math pilot curriculum](GRADE4_MATH_CURRICULUM.md).

This closes PRR **B4** (no Urdu audio) for the pilot scope. Audio-first is a **content gate**
(M-Content) — non-readers must be able to complete a session by listening.

---

## 0. Principles

- **Urdu-first, audio-first.** Every student-facing teaching string (explanation, worked-example step,
  hint, item stem) has an Urdu narration. English support audio is **optional/secondary**.
- **Read the meaning, not the markup.** Narration reads clean spoken Urdu — never reads out symbols
  like "slash" or "underscore". `۱/۴` is narrated "ایک بٹا چار".
- **Numerals spoken in Urdu, shown Eastern-Arabic** (FD-15): `۲۴` is narrated "چوبیس".
- **No audio scaffolding where reading is the construct.** Not applicable to math (audio allowed
  throughout), but the rule is honored platform-wide (master matrix §4.2).
- **Child-safe voice.** Warm, calm, unhurried, encouraging; never alarming; never impersonates a human
  teacher's identity (the runtime already forbids "claim to be a human teacher").
- **Accessibility.** Audio pairs with on-screen text + captions; every visual has alt-text; nothing
  relies on color or sound alone (WCAG 2.2 AA).

---

## 1. Voice + delivery spec

| Attribute | Spec |
| --- | --- |
| Language / register | Standard spoken Urdu, simple child register; avoid heavy literary vocabulary |
| Tone | Warm, patient, encouraging; smile-in-the-voice; never stern |
| Reading speed | **~90–110 words/min** for explanations (slower than adult narration); ~80 wpm for worked-example steps; a deliberate pause between steps |
| Pausing | 300–500 ms between sentences; 700–1000 ms between worked-example steps; 500 ms before a question is asked |
| Pronunciation | Verified Urdu pronunciation of math terms (see §5 glossary); consistent across all lessons |
| English support | Same script, neutral Pakistani-English pronunciation, secondary priority |
| Loudness | Normalized to a consistent target across all clips; no clipping; quiet, low-noise room |
| Prohibited | Background music under speech (distraction/accessibility); sound effects that could startle; any named person/brand |

---

## 2. Sentence segmentation model

Audio is authored and stored as **short, independently-addressable segments**, not one long file per
lesson. This is what makes replay, "read this part again", per-step highlighting, and offline chunking
work.

- **One segment = one idea** (a sentence or a single worked-example step).
- Each **teaching string** in a lesson maps to one Urdu segment (+ optional English segment).
- Segments are ordered within a lesson; the player concatenates or plays them on demand.
- Long explanations are split at natural clause boundaries, never mid-phrase.
- A segment id is derived from `lesson_id` + role + index (see §4).

Example segmentation (from L1.1, MATH-G4-NB-01):

| Seg | Role | Urdu text (spoken) | Approx. words |
| --- | --- | --- | --- |
| 1 | explanation | ہم عدد کو دائیں سے پڑھتے ہیں: اکائی، دہائی، سو، ہزار۔ | 9 |
| 2 | worked-step | دو ہزار پانچ میں پانچ اکائیاں ہیں۔ | 6 |
| 3 | worked-step | اسے ہم دو ہزار پانچ لکھتے اور پڑھتے ہیں۔ | 7 |
| 4 | item-stem | یہ عدد پڑھیں: تین ہزار چار سو چھپن۔ | 7 |

---

## 3. Reading-speed + timing metadata

Every segment carries timing metadata so the player can highlight text in sync, show progress, and
size offline packages. **This metadata is authored as data that accompanies the content — it does not
change any backend model.** Suggested shape (illustrative JSON; lives beside the content package):

```json
{
  "segment_id": "L-math-g4-nb-read-write:ur:explanation:1",
  "lesson_id": "L-math-g4-nb-read-write",
  "locale": "ur",
  "role": "explanation",
  "order": 1,
  "text": "ہم عدد کو دائیں سے پڑھتے ہیں: اکائی، دہائی، سو، ہزار۔",
  "word_count": 9,
  "target_wpm": 100,
  "est_duration_ms": 5400,
  "measured_duration_ms": null,
  "audio_ref": "audio/ur/math-g4-nb-read-write/explanation-1.mp3",
  "caption_ref": "captions/ur/math-g4-nb-read-write/explanation-1.vtt"
}
```

- `est_duration_ms` = `word_count / target_wpm * 60000`, padded for pauses; **authoring estimate**.
- `measured_duration_ms` is filled after real recording (null until then — never fabricate a duration).
- `audio_ref` mirrors the pattern already used in the live fractions lesson
  (`audio/ur/fractions.mp3`), extended to per-segment paths.
- Captions (`.vtt`) are required for every segment (accessibility) and carry word-level timing when
  available.

---

## 4. Audio asset specification

| Attribute | Spec |
| --- | --- |
| Format | MP3 (broad device support) + optional Opus for smaller offline packages |
| Sample rate / channels | 44.1 kHz, mono (speech) |
| Bitrate | ~64–96 kbps mono (speech-optimized; keeps offline packages small) |
| Naming | `audio/{locale}/{lesson_slug}/{role}-{order}.mp3` |
| Captions | `captions/{locale}/{lesson_slug}/{role}-{order}.vtt` |
| Loudness | Consistent normalized target across all clips |
| Silence trim | Leading/trailing silence trimmed to ≤ 150 ms |
| Packaging | All of a lesson's segments ship inside that lesson's `offline_package` (`pkg/…`) so it plays fully offline |
| Size budget | Target a small per-lesson audio footprint suitable for low-end devices and intermittent networks (measured during Pilot 0) |
| Provenance | Each asset records narrator + record date + script version; `authored-original` |

**Roles** (segment `role` values): `title`, `explanation`, `worked-step`, `item-stem`, `hint`,
`misconception-correction`, `summary`, `encouragement`.

---

## 5. Math-term pronunciation glossary (Urdu)

Consistent narration of key terms across all 31 lessons. (Term — spoken Urdu — English support.)

| Concept | Urdu (spoken) | English |
| --- | --- | --- |
| digit | ہندسہ | digit |
| number | عدد | number |
| place value | جگہ کی قیمت | place value |
| addition / sum | جوڑ | addition |
| subtraction | تفریق | subtraction |
| carry | (ایک) لے جانا | carry |
| borrow | ادھار لینا | borrow |
| multiply / times | ضرب / گنا | multiply |
| times-table | پہاڑا | times-table |
| divide | تقسیم | divide |
| remainder | باقی | remainder |
| fraction | کسر | fraction |
| numerator | شمار کنندہ (اوپر کا نمبر) | numerator |
| denominator | نسب نما (نیچے کا نمبر) | denominator |
| equal parts | برابر حصے | equal parts |
| length | لمبائی | length |
| mass / weight | وزن | mass |
| capacity | گنجائش | capacity |
| angle | زاویہ | angle |
| right angle | قائمہ زاویہ | right angle |
| symmetry | تناسب | symmetry |
| line of symmetry | محورِ تناسب | line of symmetry |
| pictograph | تصویری خاکہ | pictograph |
| bar graph | سلاخی خاکہ | bar graph |
| scale (graph) | پیمانہ | scale |

**Fraction reading convention:** `a/b` is narrated "a بٹا b" (e.g. `۳/۴` → "تین بٹا چار"), matching
the live fractions lesson.

---

## 6. Script-writing rules (for the author)

- Write the **spoken** form, not the written form: expand numerals to words, expand `۱/۴` to
  "ایک بٹا چار", read `>` as "بڑا ہے".
- Keep each segment to **one idea**; short sentences; active voice; direct address to the child ("آپ").
- **Encouragement segments** are short, sincere, and effort-focused ("اچھی کوشش!" / "Good try!") —
  never hollow praise, never comparative ("better than others").
- **Hint audio** follows the graduated ladder (H1→H2→H3) — never narrate the answer before H3.
- **Misconception-correction audio** states the correction warmly, not as "wrong" — mirrors the live
  correction style ("More parts means smaller parts").
- No content that asks the child to speak/record personal data; no external names, brands, or people.
- Every script segment is reviewed against [CONTENT_QA_CHECKLIST.md](CONTENT_QA_CHECKLIST.md) before
  recording.

---

## 7. Production workflow (per lesson)

1. **Author** the Urdu segments from the lesson's teaching strings (this doc's rules).
2. **Segment + tag** with role/order; compute `est_duration_ms`.
3. **QA the script** (checklist: age, accuracy, register, safety, pronunciation).
4. **Record** with an approved narrator in a quiet room (human voice for pilot; no synthetic audio in
   this deliverable).
5. **Post-process** — trim, normalize, export MP3/Opus + `.vtt` captions.
6. **Fill `measured_duration_ms`**; align caption timing.
7. **Package** into the lesson's `offline_package`; verify offline playback on a low-end device.
8. **Sign-off** (content QA + accessibility) before publish.

---

## 8. Coverage target for the pilot

| Item | Target |
| --- | --- |
| Lessons with full Urdu narration | 31 / 31 teaching + 8 revision |
| Segments per lesson (approx.) | 12–25 (explanation + worked steps + item stems + hints + summary) |
| English support audio | provided where it aids access; secondary priority |
| Captions | 100% of segments (WCAG) |
| Offline playback verified | 100% of packaged lessons (Pilot 0) |

No lesson is "pilot-ready" until its Urdu audio + captions are recorded, packaged, and verified
offline. Until then the surface shows the honest "audio not available" state (as the current Student
Portal already does) rather than a silent failure.
