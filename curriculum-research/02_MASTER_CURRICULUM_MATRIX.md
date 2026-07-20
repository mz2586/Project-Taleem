# 02 · Master Curriculum Matrix — KG–10 (NCP-aligned)

| | |
|---|---|
| **Date** | 2026-07-20 |
| **Aligns to** | National Curriculum of Pakistan (NCP / SNC), Scheme of Studies 2024, subject Progression Grids ([01 Inventory](./01_CURRICULUM_RESOURCE_INVENTORY.md)) |
| **Feeds** | [docs/05-education/21-curriculum-engine.md](../docs/05-education/21-curriculum-engine.md) · [docs/05-education/58-mastery-and-assessment-validity.md](../docs/05-education/58-mastery-and-assessment-validity.md) |

## ⚠️ Copyright & authenticity notice (read first)

The official SLOs are **copyright-reserved government text** ([01 §1](./01_CURRICULUM_RESOURCE_INVENTORY.md)).
This matrix therefore contains:

- ✅ **Verified structure** — the real subject roster per grade band and the real hierarchy
  (Standard → Benchmark → SLO), sourced from the public NCP Scheme of Studies and Progression Grids.
- ✅ **Illustrative, independently re-expressed examples** — clearly labeled `[ILLUSTRATIVE]`. These are
  **our own wording** of the *kind* of outcome each domain contains, **not** the government's verbatim
  SLOs, and are placeholders until the [ingestion pipeline](./04_CURRICULUM_INGESTION_PIPELINE.md)
  populates the authoritative taxonomy (under an NCC/MoFEPT MoU) or our authors write the SLO-aligned set.
- ❌ **No verbatim official SLO text** is reproduced here.

Full, authoritative population of every SLO across KG–10 is a **Phase-3 deliverable**
([FINAL_ROADMAP.md](../FINAL_ROADMAP.md)); this document is the **schema + roster + worked pattern**.

## 1. The curriculum data model

The matrix maps 1:1 onto the curriculum-engine entities:

```text
Grade band → Subject → Unit/Chapter → Topic → Learning Outcome (SLO) → Competency → Assessment item(s)
   │            │          │            │            │                     │              │
 KG..10   NCP subject   NCP domain   sub-topic   what the child can do   skill class   how we verify
```

| Level | NCP term | Engine entity ([21](../docs/05-education/21-curriculum-engine.md)) | Notes |
|---|---|---|---|
| Grade band | Grade / stage | `grade` | KG(ECE), 1–5, 6–8, 9–10 |
| Subject | Subject | `subject` | verified roster §2 |
| Unit/Chapter | Standard / Domain | `unit` | a themed group |
| Topic | Benchmark / sub-domain | (unit sub-group) | |
| **SLO** | Student Learning Outcome | `objective` + **mastery criteria** | the atomic, gradable unit; the north-star currency |
| Competency | Competency/skill | objective attribute (skill class) | knowledge / comprehension / application / analysis |
| Assessment | Assessment blueprint | `item` / `assessment` ([23](../docs/05-education/23-assessment-engine.md)) | maps each SLO → item type + mastery rule ([58](../docs/05-education/58-mastery-and-assessment-validity.md)) |

Every SLO carries machine-readable **mastery criteria** and links to ≥1 **assessment item** and a
**competency class**, so mastery ([58](../docs/05-education/58-mastery-and-assessment-validity.md)) and the
north-star event derive directly from this matrix.

## 2. Verified subject roster (NCP, KG–10)

Sourced from the public NCP Scheme of Studies + subject list ([01 §2.1](./01_CURRICULUM_RESOURCE_INVENTORY.md)).
Religious education is a **student-attribute track**: Islamiat (Muslim) ↔ Ethics/Akhlaqiat (non-Muslim),
per [docs/05-education/21](../docs/05-education/21-curriculum-engine.md) (audit AR-C-20).

| Grade band | Core subjects (NCP) |
|---|---|
| **KG / Pre-I (ECE)** | Integrated Early Childhood Education: emergent literacy (Urdu/English readiness), emergent numeracy, world-around-us, socio-emotional, motor, Islamic/moral foundation |
| **Grades 1–3 (Early Primary)** | Urdu · English · Mathematics · **General Knowledge** (integrates science/social/health) · Islamiat/Ethics (from Gr 3) |
| **Grades 4–5 (Primary)** | Urdu · English · Mathematics · **General Science** · **Social Studies** · Islamiat/Ethics |
| **Grades 6–8 (Middle)** | Urdu · English · Mathematics · General Science · Social Studies (History + Geography) · Islamiat/Ethics · **Computer Science** |
| **Grades 9–10 (SSC/Matric)** | Urdu · English · Mathematics · **Physics · Chemistry · Biology** (or Computer Science stream) · **Pakistan Studies** · Islamiat/Ethics |

## 3. Coverage grid (what the full matrix must contain)

Each ✓ is a Grade × Subject cell whose SLO set must be authored/ingested. Rough scale for planning.

| Subject \ Grade | KG | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Urdu | ◐ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| English | ◐ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Mathematics | ◐ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| General Knowledge | — | ✓ | ✓ | ✓ | — | — | — | — | — | — | — |
| General Science | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | — | — |
| Physics/Chem/Bio | — | — | — | — | — | — | — | — | — | ✓ | ✓ |
| Social Studies | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | — | — |
| Pakistan Studies | — | — | — | — | — | — | — | — | — | ✓ | ✓ |
| Islamiat/Ethics | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Computer Science | — | — | — | — | — | — | ✓ | ✓ | ✓ | ◐ | ◐ |

Legend: ✓ full subject · ◐ integrated/optional · — not offered. **Planning-assumption scale:** ~10 subjects
× ~11 grades ≈ **~80–90 grade-subject cells**, each with ~6–12 units, ~3–8 SLOs/unit → an order of
**~5,000–12,000 SLOs** for KG–10 (to be confirmed against the actual Progression Grids). This number is
the core content-authoring workload driver in [03](./03_CONTENT_GAP_ANALYSIS.md).

## 4. Worked pattern (illustrative — NOT verbatim official SLOs)

The pattern every cell follows, shown for three cells. **All SLO wording below is `[ILLUSTRATIVE]` — our
re-expression of the domain, not the government's text.**

### 4.1 Mathematics · Grade 1 · Unit "Numbers up to 100"

| Topic | SLO `[ILLUSTRATIVE]` | Competency | Assessment (blueprint) | Mastery rule ref |
|---|---|---|---|---|
| Counting | The child can count objects up to 100 and read/write the numerals | Application | MCQ + count-the-objects interactive; auto-graded | [58 §1](../docs/05-education/58-mastery-and-assessment-validity.md) |
| Place value | The child can identify tens and ones in a two-digit number | Comprehension | drag-to-bucket; auto-graded | confirmed-mastery + spaced re-check |
| Comparison | The child can compare two numbers using >, <, = | Application | MCQ; auto-graded | distinct-item pool ≥5× |

*(Numerals rendered per pedagogical context — Eastern-Arabic ۰-۹ in Urdu-medium early math, per
[FOUNDER_DECISIONS FD-15](../FOUNDER_DECISIONS.md).)*

### 4.2 English · Grade 3 · Unit "Reading comprehension"

| Topic | SLO `[ILLUSTRATIVE]` | Competency | Assessment | Note |
|---|---|---|---|---|
| Literal comprehension | The child can answer literal questions about a short read text | Comprehension | short-answer + MCQ | **reading is the construct** → no audio scaffolding on the passage (validity, [58 §3](../docs/05-education/58-mastery-and-assessment-validity.md)) |
| Vocabulary | The child can infer word meaning from context | Application | MCQ | |

### 4.3 General Science · Grade 6 · Unit "Cells and living things"

| Topic | SLO `[ILLUSTRATIVE]` | Competency | Assessment | Note |
|---|---|---|---|---|
| Cell structure | The child can identify the basic parts of a plant/animal cell | Knowledge | labelled-diagram + MCQ | audio + image (Urdu-first) |
| Function | The child can explain, in their own words, what a cell does | Comprehension | short-answer (human/AI-assisted grade) | subjective → mentor-mediated at summative |

## 5. Assessment mapping (every SLO → item type)

Per [58](../docs/05-education/58-mastery-and-assessment-validity.md) and the FBISE SLO model
([01 §2.2](./01_CURRICULUM_RESOURCE_INVENTORY.md)):

| Competency class | Default item types | Grading | Summative identity |
|---|---|---|---|
| Knowledge / Comprehension | MCQ, true/false, match, label | auto | formative device-ok |
| Application | numeric, structured, interactive | auto where deterministic | formative device-ok |
| Analysis / constructed | short/long answer, oral | human / AI-assisted-then-human | **mentor-mediated** (redesign) |

## 6. How this matrix gets populated (authoritatively)

1. **Ingest the public Progression Grids** (under NCC/MoFEPT MoU) → authoritative SLO taxonomy — via the
   [ingestion pipeline](./04_CURRICULUM_INGESTION_PIPELINE.md); **or**
2. **Author an SLO-aligned taxonomy** by re-expression (counsel-reviewed) if the MoU is pending;
3. **Curriculum Architects** validate every cell (standards-coverage report must be clean —
   [21 §4](../docs/05-education/21-curriculum-engine.md)); **content-QA sign-off** before publish;
4. **Psychometric review** of the assessment blueprints ([58](../docs/05-education/58-mastery-and-assessment-validity.md)).

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-20 | Master matrix: data model, verified NCP subject roster KG–10, coverage grid (~80–90 cells, ~5–12k SLOs planning estimate), illustrative worked pattern (non-verbatim), assessment mapping, authoritative-population path. | Curriculum discovery |
