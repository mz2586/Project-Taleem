# 01 · Curriculum Resource Inventory — Pakistan (Official & Public Sources)

| | |
|---|---|
| **Mission** | Maximize use of *official, publicly available* Pakistani curriculum resources — without commercial publisher partnerships — while using only appropriately-sourced content. |
| **Date** | 2026-07-20 |
| **Method** | Web investigation of official government/board sites + license verification (3 parallel research streams, cross-checked). |
| **Companions** | [02_MASTER_CURRICULUM_MATRIX.md](./02_MASTER_CURRICULUM_MATRIX.md) · [03_CONTENT_GAP_ANALYSIS.md](./03_CONTENT_GAP_ANALYSIS.md) · [04_CURRICULUM_INGESTION_PIPELINE.md](./04_CURRICULUM_INGESTION_PIPELINE.md) |
| **Curriculum engine** | [docs/05-education/21-curriculum-engine.md](../docs/05-education/21-curriculum-engine.md) · [docs/05-education/58-mastery-and-assessment-validity.md](../docs/05-education/58-mastery-and-assessment-validity.md) |

## 0. Headline finding

> **The single most important asset — the curriculum *standards* layer — is fully public and free.** The
> **National Curriculum of Pakistan (NCP)** (the renamed Single National Curriculum), its **Scheme of
> Studies**, its **subject Progression Grids containing the Student Learning Outcomes (SLOs) for Grades
> 1–12**, the **National Curriculum Framework**, and **per-subject SLO Assessment Frameworks** are all
> downloadable free PDFs from the National Curriculum Council (`ncc.gov.pk`), with no login.
>
> **Therefore no commercial publisher partnership is required** to build a curriculum-*aligned* school:
> the public standards are the alignment spine, and we author our own original content to them. The one
> hard constraint is **licensing** — every government source is "All Rights Reserved" with **no open
> license**, so *free-to-view ≠ free-to-reuse*.

## 1. The four usage rights (assess each resource against all four)

Because "free to download" says nothing about reuse, every resource is assessed against four distinct
rights (this is a legal framing, not settled advice — route to counsel):

| Right | Meaning |
|---|---|
| **R1 · Read / reference** | Humans read it; we align our own content to its standards. Lowest risk. |
| **R2 · Index** | Store links/metadata/citations to it. Low risk for public pages. |
| **R3 · Derive** | Build a structured, *re-expressed* curriculum taxonomy from its standards. Medium risk — depends on the expression-vs-facts line. |
| **R4 · AI-RAG / ingest** | Load its *verbatim* text into a retrieval/training corpus. Highest risk — needs an open license or written permission. |

**Governing legal principle (for counsel, not asserted as settled):** copyright protects the *expression*
(the document's wording/layout, a textbook's prose), **not** the underlying *facts, ideas, or curriculum
standards*. So an independently re-expressed SLO taxonomy (R3) stands on different footing from copying
the government's verbatim wording (R4). Pakistan has **no automatic public-domain for government works**
(Copyright Ordinance 1962), so absent an explicit license, the safe path for R3/R4 is **written
permission (an MoU) from NCC/MoFEPT**.

## 2. Resource inventory

Legend — **Avail:** ✅ free public · 💲 sold · 🔒 login/app · ❓ unverified. **License:** ARR = all rights
reserved (gov/board) · CC = open Creative-Commons · OD = open-data license · PROP = proprietary private.

### 2.1 Curriculum standards layer (federal) — the alignment spine

| Resource | Official source | Classes | Subjects | Lang | Avail | Format | License | R1 | R2 | R3 | R4 |
|---|---|---|---|---|:--:|---|---|:--:|:--:|:--:|:--:|
| **National Curriculum of Pakistan (NCP / SNC)** | `ncc.gov.pk`, `mofept.gov.pk` | Pre-I–XII (1-5, 6-8, 9-12 phased) | English, Urdu, Math, Islamiat, GK, Social/General Science, History, Geography, Pak Studies; 9-12 add Physics/Chem/Bio/CS | En + Ur | ✅ | PDF | **ARR** (©MOFEPT) | ✅ | ✅ | ⚠️ perm | ⚠️ perm |
| **Scheme of Studies** ("Inclusive Scheme of Studies 2024") | `ncc.gov.pk` (single PDF) | Pre-I–XII | All streams + period allocation | En | ✅ | PDF (image-heavy → OCR) | **ARR** | ✅ | ✅ | ⚠️ perm | ⚠️ perm |
| **Subject Progression Grids (contain the SLOs)** | `ncc.gov.pk` per-subject PDFs | 1–12 | Per compulsory subject (e.g. Math PG 1-12) | En/Ur | ✅ | PDF | **ARR** | ✅ | ✅ | ⚠️ perm | ⚠️ perm |
| **National Curriculum Framework (NCF)** | `mofept.gov.pk`, `pc.gov.pk` mirror | ECE–XII | Cross-subject policy | En | ✅ | PDF | **ARR** | ✅ | ✅ | ⚠️ perm | ⚠️ perm |
| **SLO Assessment Frameworks** | `ncc.gov.pk` (e.g. Pak Studies 9-12) | 9–12 (expanding) | Per subject | En | ✅ | PDF | **ARR** | ✅ | ✅ | ⚠️ perm | ⚠️ perm |
| **National Curriculum Council (NCC)** — the publishing body | `ncc.gov.pk` | ECE–XII | steers all above | En/Ur | ✅ | HTML+PDF | **ARR** (©2026 MOFEPT) | ✅ | ✅ | ⚠️ perm | ⚠️ perm |

### 2.2 Assessment layer (federal exam board)

| Resource | Official source | Classes | Subjects | Lang | Avail | Format | License | R1 | R2 | R3 | R4 |
|---|---|---|---|---|:--:|---|---|:--:|:--:|:--:|:--:|
| **FBISE — SLO-based model papers + assessment frameworks** | `fbise.edu.pk` | 9–12 (SSC/HSSC) | All examined subjects | En/Ur | ✅ | PDF | **ARR** (gov) | ✅ | ✅ | ⚠️ perm | ⚠️ perm |

> FBISE is an *exam* board (no textbooks). Its **SLO-based assessment model** (since 2022; Section A MCQ
> ~20% / B short ~50% / C long ~30%) is the most naturally "assessment-shaped" public spec — valuable as
> a *reference* for our own assessment blueprint design ([58](../docs/05-education/58-mastery-and-assessment-validity.md)).

### 2.3 Textbook layer (provincial + federal) — reference only, not reusable without permission

| Resource | Official source | Classes | Subjects | Province | Lang | Avail | Format | License | R1 | R2 | R3 | R4 |
|---|---|---|---|---|---|:--:|---|---|:--:|:--:|:--:|:--:|
| **PCTB e-books** | `pctb.punjab.gov.pk/E-Books` | 1–12 (SNC Pre-I–V withheld) | Core subjects | Punjab | Ur+En | ✅ | PDF | **ARR** ("personal viewing"*) | ✅ | ⚠️ | ❌ | ❌ |
| **STBB e-books** | `ebooks.stbb.edu.pk` | ECCE–XII | Core + regional | Sindh | **Sindhi**+Ur+En | ✅ | PDF | **ARR** (no terms found) | ✅ | ⚠️ | ❌ | ❌ |
| **KPTBB** | `tbb.kp.gov.pk` | 1–12 | Core | KP | Ur+En+**Pashto** | ❓ (mostly print; PDFs unconfirmed) | print/PDF? | **ARR** | ✅ | ❌ | ❌ | ❌ |
| **BTBB** | `btbb.com.pk` | 1–12 | Core | Balochistan | Ur+En | ❓ | PDF/app? | **ARR** (©2025 BTBB) | ✅ | ❌ | ❌ | ❌ |
| **National Book Foundation (NBF)** | `nbf.org.pk` | Primer–XII | SNC full set | Federal + GB | Ur+En | 💲 (sold; online reader + sample chapters) | print/HTML | **ARR** (©NBF; sells books) | ✅ | ❌ | ❌ | ❌ |

*PCTB "personal viewing only" is per a search index of the official page (page not directly readable this
session) — **re-verify live** before any licensing decision. **Third-party scanned textbook PDFs
(Taleem360, Ustad360, Internet Archive, etc.) carry no license and must never be ingested.**

### 2.4 Government digital learning platforms — reference only

| Resource | Official source | Classes | Subjects | Lang | Avail | Format | License | R1 | R2 | R3 | R4 |
|---|---|---|---|---|:--:|---|---|:--:|:--:|:--:|:--:|
| **eLearn.gov.pk / TeleSchool** (MoFEPT) | `elearn.gov.pk`, `teleschool.etaleem.gov.pk` | KG–12 | Math, Science, Language, Social | Ur+En | ✅ | video/TV/app | **ARR** (gov) | ✅ | ✅ | ❌ | ❌ |
| **eLearn.Punjab** (PITB+PCTB) | `elearn.punjab.gov.pk` | 4–12 | Science, Maths (+13k videos, sims, offline packs) | En+Ur | ✅ | HTML+video, offline | **ARR** (PCTB ©) | ✅ | ✅ | ❌ | ❌ |

### 2.5 Third-party OER & private platforms — verify license per asset

| Resource | Official source | Classes | Subjects | Lang | Avail | License | Usable for our product? |
|---|---|---|---|---|:--:|---|---|
| **Khan Academy / Khan Academy Urdu** | `khanacademypakistan.org`, YouTube | K–12+ | Math, Science, + | Ur+En | ✅ | **CC-BY-NC-SA** (global; verify per Urdu asset) | ⚠️ **NonCommercial likely blocks a commercial platform**; a sponsorship-funded/non-profit use *may* qualify — **counsel + per-asset verification required**; ShareAlike + attribution apply |
| **Sabaq Foundation** | `sabaq.pk` | KG–12 | Math, Sciences | Ur+En | ✅ view | **PROP** ("all rights reserved; copying prohibited") | ❌ reference only (subject/grade-page linking allowed) |
| **Taleemabad** (Orenda) | `taleemabad.com` | Nursery–5 (+) | Full SNC-aligned | Ur+En | 🔒 app | **PROP** | ❌ reference only |
| **Learn Smart Pakistan** (Knowledge Platform) | `learnsmartpakistan.org` | 6–12 | Math, English, Science | En+Ur | 🔒 | **PROP** | ❌ reference only |
| **TeleTaleem** | `teletaleem.com` | Primary+ | Core | Ur+En | 🔒 B2G/B2B | **PROP** | ❌ reference only |

### 2.6 Context datasets (analytics, not curriculum) — for the "out-of-school" flag, targeting, impact

| Resource | Source | What | License | Usable? |
|---|---|---|---|---|
| **ASER Pakistan** | `aserpakistan.org`, PAL Network | Learning-outcome + OOS survey | reports free; micro-data likely **CC-BY-NC-SA** (verify PK) | ✅ analytics; commercial reuse per license |
| **PSLM / HIES** (PBS) | `pbs.gov.pk`, `data.gov.pk` | Education access/OOS indicators | gov stats; **facts freely usable** | ✅ (facts not copyrightable) |
| **Pakistan Education Statistics** (PIE) | `pie.gov.pk` | Schools/enrolment/teachers | ARR report; facts usable | ✅ facts |
| **World Bank Data Depot — Pakistan** | `datacatalog.worldbank.org` | Aggregated education data | typically **CC-BY 4.0** | ✅ with attribution |
| **Open Data Pakistan / KP Open Data** | `opendata.com.pk`, `opendata.kp.gov.pk` | Datasets | **ODbL / ODC-BY / PDDL** | ✅ genuinely open where marked |

## 3. What this means (determination)

1. **Standards spine is available now** (R1/R2) for free — enough to *align* an entire KG–10 school.
2. **Deriving/ingesting the official docs (R3/R4)** — the efficient path to a structured SLO database +
   RAG — is **not licensed**; pursue an **MoU/written permission from NCC/MoFEPT** (likely grantable for a
   non-profit child-education mission). Until then, build the SLO taxonomy by **independent re-expression**
   (R3, counsel-reviewed), not verbatim copying.
3. **Textbooks (PCTB/STBB/NBF) are reference-only** — never redistribute or RAG their text without
   permission; **never** touch third-party scans.
4. **Only genuinely-open supplements are directly reusable:** Khan Academy (⚠️ NC caveat), open datasets
   (context only).
5. **No commercial publisher partnership is required.** The needed inputs are: the public standards (have),
   our own authored content (to build), an optional NCC/MoFEPT MoU (accelerator), and open supplements.

## 4. Verification caveats (honesty)

Several official pages blocked automated reads this session (mofept.gov.pk & nbf.org.pk TLS errors;
PCTB/FBISE/STBB-index/Khan-support 403/refused). The **document PDFs and portals are live and public**;
the exact *on-page terms* for PCTB/STBB/KA-Urdu were taken from official descriptions/search extracts and
**must be re-confirmed on-source** before any licensing decision. No license was invented; every "open"
claim is tied to a stated CC/OD license, everything else is marked ARR/PROP or NOT-VERIFIED.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-20 | Initial inventory: standards/assessment/textbook/digital/OER/dataset layers with per-resource four-rights licensing assessment; determination that public standards suffice for alignment and no publisher partnership is required. | Curriculum discovery |
