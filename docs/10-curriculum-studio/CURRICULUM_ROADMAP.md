# Curriculum Roadmap

| | |
|---|---|
| **Status** | Phase 3 · How Curriculum Studio and content evolve · Related: [FINAL_ROADMAP](../../FINAL_ROADMAP.md) · [03 Content Gap](../../curriculum-research/03_CONTENT_GAP_ANALYSIS.md) |
| **Date** | 2026-07-20 |

## 1. Two tracks

- **Platform track** — Curriculum Studio itself (this Phase-3 build → hardening).
- **Content track** — authoring KG–10 lessons (gated behind the platform + governance; **no production
  content in Phase 3**).

## 2. Platform track

| Stage | Deliverable | Status |
|---|---|---|
| **CS-1 · Foundation (this build)** | Data models, workflow SM, versioning, validation, quality gates, provenance, API + OpenAPI, authoring UI scaffold, tests | ✅ this phase |
| **CS-2 · Persistence + media** | Sharded Postgres repo + migrations; media pipeline (SVG/audio/offline packages); real editor UX | ☐ |
| **CS-3 · AI-assisted authoring** | AI drafting behind the LLM gateway (human-reviewed); item generation | ☐ |
| **CS-4 · Ingestion + MoU** | Standards ingestion pipeline live under NCC/MoFEPT MoU ([04 pipeline](../../curriculum-research/04_CURRICULUM_INGESTION_PIPELINE.md)) | ☐ |
| **CS-5 · Analytics + continuous improvement** | Item statistics, lesson efficacy, misconception analytics → author feedback loop | ☐ |

## 3. Content track (gated)

Aligned to [FINAL_ROADMAP Phase 3](../../FINAL_ROADMAP.md); begins only when the platform + governance
gates are met.

| Stage | Scope | Depends on |
|---|---|---|
| **C-1 · KG–G5 core** | Urdu, English, Math, GK/Science, Islamiat/Ethics | CS-2/3; SLO taxonomy (MoU or re-express) |
| **C-2 · G6–G8** | + Social Studies, Computer Science | C-1 |
| **C-3 · G9–G10** | + Physics/Chem/Bio, Pak Studies | C-2 |
| **C-4 · Additional languages** | Sindhi/Pashto/Punjabi/Balochi via localization pipeline | localization pipeline |

**Scale driver:** ~5–12k SLOs, ~30–90k items ([03 §3](../../curriculum-research/03_CONTENT_GAP_ANALYSIS.md)) —
AI-assisted authoring (CS-3) + human review is the throughput lever.

## 4. Continuous improvement

Every published lesson is instrumented: item difficulty/discrimination, mastery rates, misconception
frequency, time-on-task, and (privacy-preserving) learning outcomes feed back to authors. Poorly-performing
items are retired; lessons are revised (new immutable versions). Curriculum is a **living system**, not a
one-time write.

## 5. Quality never yields to scale

No lesson publishes without all 9 gates ([QUALITY_ASSURANCE_STANDARD](./QUALITY_ASSURANCE_STANDARD.md)) and
the review chain. Content-band launch is gated on sufficient validated item banks
([58 §4](../05-education/58-mastery-and-assessment-validity.md)). Nothing ships on a deadline.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-20 | Curriculum roadmap: platform track (CS-1..5) + gated content track (C-1..4), scale drivers, continuous-improvement loop, quality-over-scale rule. | Curriculum Studio |
