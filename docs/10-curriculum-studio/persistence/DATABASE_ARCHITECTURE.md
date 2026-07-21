# Curriculum Studio — Persistence Architecture

Status: Design (pre-implementation). Author role: Principal Database Architect.
Scope: the durable persistence layer for the `curriculum_studio` bounded context.
Companion documents: [ERD.md](ERD.md), [POSTGRES_SCHEMA.md](POSTGRES_SCHEMA.md),
[EVENT_MODEL.md](EVENT_MODEL.md). Consistent with (and where noted, refining)
[`docs/02-architecture/09-database-design.md`](../../02-architecture/09-database-design.md),
[`54-capacity-and-scale-model.md`](../../02-architecture/54-capacity-and-scale-model.md),
[`56-bcdr-plan.md`](../../02-architecture/56-bcdr-plan.md), and
[`docs/05-education/21-curriculum-engine.md`](../../05-education/21-curriculum-engine.md).

This document is the contract the implementation must satisfy. It exists so that persistence
is designed once, reviewed, and then implemented — not discovered during coding. It is written
to hold for the next decade without a redesign of the storage model, only additive migrations.

---

## 0. The single most important decision: what this store is, and is not

The brief asks the persistence layer to "design for 1,000,000+ students; millions of lesson
interactions." A Principal Architect's first duty is to place that scale in the **right store**.
Curriculum Studio is the **authoring system of record**, not the runtime that serves a million
children. Conflating the two would produce a schema that is wrong for both.

| Concern | Owning context | Store | Cardinality | Access pattern |
| --- | --- | --- | --- | --- |
| Curriculum objects (lessons, objectives, assessments, media) | **Curriculum Studio (this doc)** | PostgreSQL `curriculum_studio` schema | **tens of thousands**, + version/audit history | Low-concurrency authoring writes; internal reads |
| Published curriculum consumed by learners | Curriculum Engine / AI Knowledge Base | Read replicas + Redis cache + RAG/search index, fed by our **outbox** | tens of thousands, read-heavy | 1M-student read fan-out (never hits the authoring primary) |
| Student lesson interactions / attempts | Lesson Delivery, Assessment | Sharded PostgreSQL by `student_ref` (doc 09 §sharding) | **millions–billions** | Per-student OLTP |
| Interaction analytics | Analytics / Warehouse | Column store (ClickHouse-compatible), fed by events | billions | OLAP roll-ups |

**Consequence for this design.** Curriculum Studio's OLTP tables are deliberately modest in row
count (tens of thousands of live objects; audit/version history is the only large-growth table,
and it is partitioned). It does **not** store student rows, attempts, or interaction telemetry —
those belong to sharded/warehouse stores in other contexts and reach us only as **aggregated,
anonymous** `item_statistics` fed back through events for the authoring-improvement loop
(§16). The million-student read load is served from **derived read models** (published snapshots
replicated to the Engine + cached + indexed), never from the authoring primary (§10, §11).

This boundary is what lets the authoring schema be fully normalized, richly indexed, auditable,
and immutable-versioned without paying a scale tax — the scale lives where it belongs. It is also
the single assumption most likely to be challenged in review, so it is stated first and defended
in §16 and the review (§21).

Design principles applied throughout (from the Engineering Constitution and the brief):

- No shortcuts; no denormalization unless explicitly justified in-line (search `JUSTIFIED`).
- Every table has a documented Purpose. Every index has a documented Justification. Every foreign
  key is intentional and its `ON DELETE` behaviour is stated. Every migration is reversible.
- Child safety and provenance first: the store **cannot** hold copyrighted third-party content
  (provenance columns + a DB-level check), and holds **no** child PII in this context.
- Additive evolution: new curricula, provinces, and countries are **rows**, not schema changes.

---

## 1. Logical data model

The logical model is derived directly from the implemented domain (`contexts/curriculum_studio/
domain/`) and the entity model in `CURRICULUM_DATA_MODEL.md`. It has three layers.

**Taxonomy layer (the curriculum skeleton — slowly changing, shared).**

- `EducationSystem` — a curriculum authority/edition (e.g. NCP-2023-National). Self-referential:
  a provincial or international variant points to its parent via `parent_system_id`. This is the
  single extension point for "future provincial variants" and "future international curriculum".
- `Grade`, `Subject` — the offering grid within a system (KG–G10 × the NCP subject roster).
- `CurriculumObjective` (SLO) — a Student Learning Outcome with a stable `standard_code`, owned
  by a system+curriculum-version. Objectives form a **prerequisite DAG** via `objective_prereq`.

**Authoring layer (the aggregate under active editing — the heart of this store).**

- `Lesson` (aggregate root) — the atomic authored unit. Holds queryable placement/state columns
  plus the rich authored `body` (see §3 for the aggregate boundary and §2 for why the body is a
  document). Aligned to objectives via `lesson_objective` (outcomes and prerequisites).
- `LessonVersion` — an **immutable** published snapshot (content hash + full body + gate results).
- `QualityGateResult`, `WorkflowTransition` — the current-head gate outcomes and the append-only
  workflow trail (both snapshot into `LessonVersion` at publish).

**Supporting layer (assets, language, events, audit).**

- `MediaAsset` + `lesson_media` — the media registry and its M:N link to lessons.
- `Attachment`, `OfflinePackage` — downloadable artifacts and offline day-packs.
- `Translation` — per-field localization status/coverage index (multilingual governance).
- `AuditLog` — hash-chained, append-only, tamper-evident record of every mutation.
- `Outbox` — transactional domain-event log drained by a relay (the only egress to other contexts).

Entities, attributes, and relationships are drawn in [ERD.md](ERD.md); physical types and
constraints are in [POSTGRES_SCHEMA.md](POSTGRES_SCHEMA.md).

---

## 2. Physical model shape: relational skeleton + JSONB document body (JUSTIFIED)

The `Lesson` domain aggregate is deep and document-like: ~30 fields, many of them lists of nested
value objects (`WorkedExample`, `Hint`, `Misconception`, `AssessmentItem`, `AITeachingObject`,
`LocalizedText` maps). It is authored, validated, versioned, and published **as a single unit**;
there is no use case that mutates one hint in isolation across the catalogue, and no query that
filters lessons by the third step of a worked example.

Two physical options were weighed:

1. **Full normalization** — a table per nested type (`lesson_hint`, `lesson_worked_example`,
   `lesson_worked_example_step`, `assessment_item`, `assessment_item_option`, …). ~15 child
   tables, deep joins to reconstruct one lesson, and a schema migration every time the domain
   adds a content block. High write amplification; brittle against domain evolution.
2. **Hybrid (chosen)** — relational columns for everything that is **queried, filtered, joined,
   constrained, or indexed**; a single `JSONB body` column for the authored document; and
   **generated/extracted columns + a tsvector** for the few body fields that need to be searched
   or constrained.

The hybrid is chosen and is the one *justified* denormalization in the design. Justification:

- The document is the aggregate's transactional and consistency boundary (§3) — storing it as one
  value matches the domain's own `to_dict()`/`content_hash()`/snapshot semantics exactly.
- `JSONB` is validated, typed, indexable (GIN), and diff-able in Postgres — not an opaque blob.
- Queryable facets are **promoted to real columns** (`grade_key`, `subject_key`, `state`,
  `difficulty`, `system_id`, `content_hash`, `estimated_duration_min`) with real constraints and
  indexes, so we never filter inside JSON on a hot path. Alignment to objectives is a real join
  table, not a JSON array, because coverage/ prerequisite queries must be relational (§4).
- Domain evolution (a new content block) becomes a JSON-shape change validated in the domain and
  the app, with **no DDL** — additive by construction.

What is **not** in JSON (kept relational, deliberately): identity, placement, lifecycle state,
version pointers, provenance summary, objective alignment, gate results used for reporting,
media/attachment links, audit, and events. JSON holds authored prose and nested content only.

---

## 3. Aggregate boundaries

Aggregates define transactional consistency. Curriculum Studio has one primary aggregate and a
small number of independent ones. Cross-aggregate references are **by id**, never by object graph,
and are enforced within the single `curriculum_studio` schema (no cross-context FKs — doc 09).

- **Lesson (root)** — boundary includes: the lesson row (`lesson`), its current-head
  `quality_gate_result` rows, its `workflow_transition` trail, and its `lesson_objective` /
  `lesson_media` links. A single Unit of Work commits the lesson and these children atomically.
  Invariant enforced within the boundary: state transitions are legal, gates gate publication,
  provenance is admissible, `lock_version` is monotonic.
- **LessonVersion** — created transactionally with a publish, but thereafter **immutable and
  independent**: a version is never updated. It references its lesson by id and carries a
  self-contained snapshot so it survives even if the working head is later archived.
- **CurriculumObjective (+ prerequisite edges)** — the SLO taxonomy is its own aggregate,
  versioned by `curriculum_version`; lessons reference objectives by `standard_code`/id. Editing
  the taxonomy and editing a lesson are separate transactions.
- **MediaAsset** — an independent aggregate (uploaded once, referenced by many lessons). Its
  lifecycle (virus scan, license check, content-hash dedupe) is independent of any lesson.
- **EducationSystem / Grade / Subject** — a slowly-changing reference aggregate.

Rule: a transaction mutates exactly one aggregate root (plus its owned children). Coordination
across aggregates is **eventual**, via the outbox (§17), never via a distributed transaction.

---

## 4. Index strategy

Every index below is justified by a concrete access path. No speculative indexes. Composite
column order follows the equality-then-range rule. Full DDL in POSTGRES_SCHEMA.md §Indexes.

| Index | Table(s) | Justification (the query it serves) |
| --- | --- | --- |
| PK on `id` (UUIDv7) | all | Primary access by id; UUIDv7 is time-ordered so PK inserts stay B-tree-append-friendly (no page-split storm of random UUIDv4). |
| `uq_lesson_system_key` (`system_id`, `lesson_key`) | `lesson` | Business identity; a lesson key is unique within a curriculum system. Prevents duplicate authoring. |
| `ix_lesson_placement` (`system_id`, `grade_key`, `subject_key`, `state`) `WHERE deleted_at IS NULL` | `lesson` | The console/list query: "lessons for this grade+subject in state X". Partial (excludes soft-deleted) keeps it lean. |
| `ix_lesson_state` (`state`) `WHERE deleted_at IS NULL` | `lesson` | Workflow dashboards ("everything in `ai_safety`"). |
| `ix_lesson_updated_at` (`updated_at DESC`) | `lesson` | "Recently edited" ordering in the authoring UI. |
| `gin_lesson_search` (`search_vector`) | `lesson` | Full-text authoring search (§5). GIN on the maintained tsvector. |
| `gin_lesson_body` (`body jsonb_path_ops`) | `lesson` | Occasional containment queries into the body during audits/migrations; `jsonb_path_ops` is smaller/faster for `@>`. |
| `uq_version_lesson_no` (`lesson_id`, `version_no`) | `lesson_version` | Version identity + fast "get version N"/"latest" (ordered scan). |
| `ix_version_lesson_created` (`lesson_id`, `created_at DESC`) | `lesson_version` | Version-history timeline for a lesson. |
| `uq_objective_code` (`system_id`, `curriculum_version`, `standard_code`) | `curriculum_objective` | SLO identity within a system+version; the lookup key used by lessons. |
| `ix_objective_placement` (`system_id`, `grade_key`, `subject_key`) | `curriculum_objective` | Coverage queries: which SLOs exist for a grade+subject. |
| PK (`objective_id`, `prerequisite_id`) + `ix_prereq_reverse` (`prerequisite_id`) | `objective_prereq` | DAG traversal both directions (prerequisites-of / unlocks). |
| `uq_lesson_objective` (`lesson_id`, `objective_id`, `role`) + `ix_lo_objective` (`objective_id`, `role`) | `lesson_objective` | "objectives covered by lesson" and the reverse "lessons covering objective" (curriculum-coverage reports). |
| `ix_gate_lesson` (`lesson_id`, `gate`) | `quality_gate_result` | Render the 9-gate strip for a lesson; enforce all-green on publish. |
| `ix_transition_lesson_at` (`lesson_id`, `at`) | `workflow_transition` | Ordered workflow trail per lesson. |
| `uq_media_hash` (`content_hash`) | `media_asset` | Content-addressed dedupe of uploads; also the integrity check. |
| `ix_translation_target` (`entity_type`, `entity_id`, `locale`) + `ix_translation_status` (`status`, `locale`) | `translation` | Per-object localization state, and the "what still needs `ur`/`en`" backlog. |
| `ix_audit_entity` (`entity_type`, `entity_id`, `at`) | `audit_log` | Reconstruct the history of one object. |
| `ix_audit_correlation` (`correlation_id`) | `audit_log` | Trace one request's full footprint. |
| `ix_outbox_unpublished` (`occurred_at`) `WHERE published_at IS NULL` | `outbox` | The relay's hot poll: fetch undelivered events in order. Partial index stays tiny (only the backlog). |

Indexing discipline: partial indexes exclude soft-deleted/published rows from hot paths; covering
columns are added only where an index-only scan is demonstrably needed (called out in the DDL).

---

## 5. Full-text search strategy

Authoring search ("find the lesson about fractions") runs **inside Postgres** in this context —
the volume is tens of thousands of rows, so a dedicated search cluster is unjustified here. (The
learner-facing search over *published* content is a separate concern owned by the Engine/Search
context and fed by our events; it may use Meilisearch/OpenSearch — out of scope for this store.)

- Each `lesson` has a `search_vector tsvector` maintained by a `BEFORE INSERT OR UPDATE` trigger
  (not a `GENERATED` column, because the source fields live inside `body` JSONB and we weight them).
- Weighting: title (`A`) > learning outcomes / keywords (`B`) > summary / description (`C`) >
  body prose (`D`). Extracted from the JSONB body in the trigger.
- Language: Urdu is the primary content language. Postgres ships no Urdu stemmer, so we index with
  the `simple` configuration (no stemming, exact+prefix) for Urdu and `english` for English text,
  stored in one combined vector. This is honest about capability — no fake stemming — and is
  documented as a known limitation with an upgrade path (custom dictionary / trigram assist).
- `pg_trgm` GIN on title is added for fuzzy/substring matching and typo tolerance in the console.
- Justification for GIN over GiST: read-heavy authoring search favours GIN's faster lookups; the
  slower GIN build/update cost is irrelevant at this write volume.

If authoring search ever outgrows Postgres (it will not at tens of thousands of rows), the same
outbox that feeds the learner index can feed an authoring index — no schema change required.

---

## 6. Versioning strategy

Immutable, snapshot-based versioning, aligned with the domain's `VersionHistory`/`Version` and
the curriculum-engine immutability rule (doc 21 §5).

- The `lesson` row is the **mutable working head** (the current draft/approved content).
- On **publish**, the service computes `content_hash()` over content fields and writes an
  **immutable** `lesson_version` row: `(lesson_id, version_no, content_hash, body_snapshot,
  gate_results_snapshot, change_summary, author_role, created_at)`. Version rows are never updated
  or deleted (enforced by trigger + by revoking `UPDATE`/`DELETE` at the DB grant level).
- `version_no` is monotonic per lesson (`next_version_number()`), enforced by the unique
  `(lesson_id, version_no)` constraint; concurrent publishes are serialized by optimistic locking
  (§9) so two publishes cannot claim the same number.
- **Content-addressing**: `content_hash` makes versions verifiable and de-duplicable; publishing
  an unchanged head is a no-op (same hash) rather than a spurious new version.
- **Rollback** does not mutate history: it creates a *new* head from a prior version's snapshot
  (a forward-moving "revert" version), preserving the full lineage — you can always see that vN
  restored vN-2.
- The taxonomy is versioned independently by `curriculum_version` on `curriculum_objective`, so a
  new NCP edition is a new set of objective rows, and old lessons keep referencing the edition
  they were authored against (no silent standard drift).

Storage note: snapshots duplicate body content across versions by design (immutability > space).
At tens of thousands of lessons this is trivial; if it ever matters, snapshots compress well
(TOAST + `lz4`) and cold versions can be tiered (§18). Space is not a constraint worth denormalizing
away immutability for.

---

## 7. Audit strategy

Complete, tamper-evident, append-only audit — a hard requirement (AR-C-21) and a child-safety /
governance control.

- `audit_log` records every mutation: `(entity_type, entity_id, action, actor_role, before JSONB,
  after JSONB, at, correlation_id, prev_hash, row_hash)`.
- **Hash chaining**: `row_hash = sha256(prev_hash || canonical(this row))`, where `prev_hash` is
  the previous row's hash for the same entity. Any retro-active edit or deletion breaks the chain
  and is detectable by a verifier job. This gives tamper-evidence without external infrastructure.
- Append-only is enforced three ways: `UPDATE`/`DELETE` revoked at grant level; a trigger that
  raises on `UPDATE`/`DELETE`; and the hash chain as a detection backstop.
- Audit is written **in the same transaction** as the mutation (via the Unit of Work), so there is
  no window where a change exists without its audit row. The chain is **per-entity** and serialized
  by the aggregate's optimistic lock (§9): because the audit row and the state change commit in one
  UoW under the same `lock_version` check, two concurrent writers to the same entity cannot both
  commit, so they cannot fork the chain (the loser retries and re-reads the new `prev_hash`). An
  append-only entity with no lock would instead take `SELECT … FOR UPDATE` on the chain tail. It is not derived from the outbox (which
  is for inter-context integration and may be pruned after delivery) — audit and events are
  separate concerns with separate retention.
- Partitioned by month (`RANGE` on `at`) so the table stays maintainable and old partitions can be
  detached to cold storage under the retention policy (doc 57) without deleting live data.
- Workflow-specific audit (`workflow_transition`) is kept as its own first-class, queryable table
  in addition to the generic log, because review lineage is a product feature, not just a control.

---

## 8. Soft delete policy

- Curriculum objects are **soft-deleted**: `deleted_at timestamptz NULL`, `deleted_by`. Nothing an
  author "deletes" is physically removed — history and downstream references must survive.
- All hot-path indexes and the default repository queries filter `WHERE deleted_at IS NULL`;
  soft-deleted rows are invisible to normal reads but present for audit/restore.
- Row-Level Security (RLS) additionally scopes visibility (doc 09) so soft-deleted + tenant rules
  compose.
- `lesson_version` and `audit_log` are **never** soft- or hard-deleted (immutable/append-only);
  archival is by partition detach, not row deletion.
- **Hard delete** exists only for one lawful reason — erasure obligations — and never applies to
  child data (there is none here). Because content is original and non-personal, the mechanism is
  simple physical deletion of the specific object under a governed, audited admin path; there is no
  student PII requiring crypto-shredding *in this context* (that mechanism lives in contexts that
  hold PII, per doc 56). Media assets removed for license/takedown reasons are hard-deleted from
  object storage and tombstoned in `media_asset` (row kept, `storage_key` nulled, reason recorded).

---

## 9. Optimistic locking

Concurrent authoring (two editors, or an editor + an automated enrichment job) must not silently
lose writes.

- Every mutable aggregate root (`lesson`, `curriculum_objective`, taxonomy tables) carries a
  `lock_version integer NOT NULL` incremented on every update.
- SQLAlchemy's `version_id_col` maps to `lock_version`; a stale update matches zero rows and raises
  `StaleDataError`, surfaced to the API as `409 Conflict` (RFC 9457 problem) so the client re-reads
  and retries. No lost updates, no last-writer-wins.
- Publishing uses the same mechanism to serialize version-number allocation (§6): the publish
  transaction reads the head at `lock_version = n`, writes the new version, and bumps to `n+1`; a
  racing publish fails the version check and retries against the new head.
- Pessimistic `SELECT … FOR UPDATE` is reserved for the narrow case of the outbox relay claiming
  rows (`FOR UPDATE SKIP LOCKED`) — a throughput pattern, not an authoring one.

---

## 10. Publishing workflow

Publication is the gate between the authoring store and everything a learner ever sees. It is a
transaction with a strict precondition and a single durable side effect (an event), never a direct
write into another context's store.

Preconditions (enforced server-side in the domain/service, re-checked at the DB boundary):

- Workflow state is `approved` (the 5-gate review chain completed, no self-approval).
- All 9 quality gates are green (`quality_gate_result` all `passed = true`).
- Provenance is admissible (original/CC0 only; no prohibited source) — a DB `CHECK` backs the
  domain rule so a bad row cannot exist even via a bug.

Transaction (single Unit of Work):

1. Recompute `content_hash`; if unchanged from latest version, no-op (idempotent publish).
2. Insert immutable `lesson_version` (snapshot of body + gate results).
3. Advance `lesson.state → published`, bump `lock_version`, set `current_version_no`.
4. Append `workflow_transition` and `audit_log` rows.
5. Enqueue a `LessonPublished` event in `outbox` (payload = version id + hash + placement).

Everything after step 5 is **asynchronous and eventual**: the outbox relay delivers
`LessonPublished` to the Curriculum Engine / AI Knowledge Base / learner search index, which build
their own read-optimized copies. The authoring primary is never in the learner read path, which is
what keeps the 1M-student load off this store (§0). Delivery is at-least-once with idempotent
consumers keyed on `(lesson_id, version_no)`.

---

## 11. Draft vs Published model

A **single-table head + immutable-version** model (not two separate draft/published tables):

- `lesson` = the working head. Its `state` column carries the lifecycle
  (`draft → in_review → … → approved → published → archived`).
- `lesson_version` = the immutable published history. "The published content" a consumer sees is
  always a specific `lesson_version`, addressed by `content_hash`/`version_no` — never the mutable
  head. A lesson can be `published` (head) while continuing to be edited toward the next version;
  learners keep seeing the last published *version* until a new one is published.
- This avoids the classic dual-table drift (draft and published copies diverging) and matches the
  domain: the head is mutable, versions are frozen. Read models in other contexts subscribe to
  published versions only (§10) — drafts never leak past the authoring boundary.
- Rationale for not using a separate `lesson_draft` table: it would double the write paths, require
  a copy-on-publish/copy-on-edit dance, and create a consistency question the version model answers
  for free. Rejected.

---

## 12. Translation model

Urdu-first multilingual content, with governance over coverage and review status.

- **Content** localization lives *in the body*: `LocalizedText` is a `{locale: text}` +
  `{locale: audio_ref}` map, so a lesson's Urdu and English prose travel with the aggregate and
  version atomically (a version is internally consistent across languages). This is correct —
  translations are not independent entities, they are facets of one authored object.
- **Governance** localization lives in the `translation` table: one row per
  `(entity_type, entity_id, field_path, locale)` recording `status`
  (`missing | draft | translated | reviewed`), `reviewer_role`, `updated_at`. This is the index
  that powers the language gate, the "what still needs Urdu audio" backlog, and future-language
  readiness dashboards — queries that must be relational and are impossible to run efficiently
  inside every lesson's JSON.
- Adding a **future language** (e.g. Sindhi, Pashto, or an international English variant) is
  additive: a new `Locale` value, new `translation` rows, new keys in the body maps — **no DDL**.
  The `locale` column is a free-form BCP-47-style string constrained by an app-level allowlist, not
  a DB enum, precisely so new languages need no migration.
- The mandatory-audio rule (Urdu audio required on core paths) is validated in the domain and
  reflected as a `translation` row per field, so audio coverage is auditable.

---

## 13. Media model

- `media_asset` is a **content-addressed registry**: `(id, kind, storage_key, content_hash,
  mime, byte_size, license, alt_text JSONB, origin, scan_status, created_at)`. The bytes live in
  S3-compatible object storage; the DB holds metadata + the pointer. `content_hash` is unique →
  automatic dedupe and integrity verification.
- **Provenance/child-safety on media**: `license` and `origin` are constrained to original/CC0
  values by a `CHECK`; `scan_status` must be `clean` before a media asset may be linked to a lesson
  that publishes (enforced in the publish precondition). No hotlinking — assets are ingested and
  owned, never referenced by external URL (this directly encodes the "no competitor image hotlinks"
  and original-content lessons learned elsewhere).
- `lesson_media` (M:N) links lessons to assets with a `role` (`visual_concept | diagram | audio |
  widget | …`). This makes garbage-collection ("which assets are unreferenced"), offline packaging,
  and integrity checks relational, rather than parsing every lesson body.
- The body still carries `MediaRef.media_id` for in-place rendering; `lesson_media` is the
  authoritative link table kept in sync within the Lesson aggregate's transaction.

---

## 14. Attachment model

- `attachment` holds generated, downloadable artifacts tied to a lesson:
  `(id, lesson_id, kind, storage_key, content_hash, byte_size, version_no, created_at)` where
  `kind ∈ {worksheet_pdf, printable, teacher_pack, …}`. Distinct from `media_asset` (reusable
  building blocks) — attachments are per-lesson outputs.
- `offline_package` is the specialization for the offline-sync requirement: a self-contained bundle
  for a lesson version — `(id, lesson_id, version_no, manifest JSONB, storage_key, byte_size,
  checksum, built_at)`. The `manifest` lists every asset + checksum + total size so a low-end
  Android/3G client can verify and resume a download. Built from a specific immutable
  `lesson_version`, so an offline pack is reproducible and pinned to exactly what was published.
- Both reference object storage for bytes and keep only metadata in Postgres — the DB never stores
  large binaries (BYTEA is disallowed for these by policy; justified: keeps the OLTP small, backups
  fast, and lets a CDN serve bytes).

---

## 15. Metadata model

- Structured, queryable metadata is promoted to **columns** on `lesson`: `system_id`, `grade_key`,
  `subject_key`, `chapter_key`, `topic_key`, `difficulty`, `estimated_duration_min`, `author_role`,
  `state`, `current_version_no`, timestamps, and the provenance summary
  (`derivation`, `license`). These are the facets everything filters, joins, and reports on.
- Open-ended, low-cardinality descriptive metadata (`tags`, `keywords`, `vocabulary`) lives in the
  body / a `text[]` column where set-membership queries are needed (`tags text[]` with a GIN index
  for `@>`), because tags are unbounded and author-defined — a column-per-tag or a tag table would
  be over-engineering for an internal authoring facet.
- `provenance` is stored both as a summarized set of columns (for the DB `CHECK` and for
  filtering/reporting) and in full within the body (the complete `Provenance` value object with
  `aligned_slo_codes`, `permission_ref`, etc.). The columns are the enforcement surface; the body
  is the record of truth — kept consistent within the aggregate transaction.

---

## 16. Analytics model

This is where the §0 boundary is defended concretely.

- Curriculum Studio does **not** store learner interactions, attempts, or per-student telemetry.
  Those are millions–billions of rows owned by Lesson Delivery / Assessment / the Analytics
  warehouse. Putting them here would corrupt the authoring store's size, backup profile, and
  security posture (it would suddenly hold child-linked data). Rejected by design.
- What the authoring store *does* hold is **aggregated, de-identified feedback** for the
  content-improvement loop: an `item_statistics` table keyed by `assessment_item_id` (or lesson id)
  carrying `attempts, p_value (difficulty), discrimination, mean_time_s, misconception_hit_rate
  JSONB, sample_window, updated_at`. These are computed **in the warehouse** and pushed back to
  Curriculum Studio via an inbound event so authors can see "this item is too hard / mis-keyed" and
  revise. Rows here number in the tens of thousands (one per item), never per-interaction.
- No `student_ref` ever appears in any Curriculum Studio table. This is a security invariant, not
  just a modelling choice: it keeps this context out of scope for child-data controls entirely.
- Authoring-process analytics (throughput, gate pass rates, review latency) are derived from
  `workflow_transition` and `audit_log` — already present, no new store needed.

---

## 17. Event model (summary; full spec in EVENT_MODEL.md)

- **Transactional outbox** is the only egress from this context. Domain events are written to
  `outbox` in the same transaction as the state change, then delivered at-least-once by a relay
  (poll `WHERE published_at IS NULL … FOR UPDATE SKIP LOCKED`, or logical-decoding CDC later).
- Consumers are idempotent, keyed on natural ids (`lesson_id + version_no`, `objective id +
  curriculum_version`). Ordering is per-aggregate via `occurred_at` + monotonic version.
- Core events: `LessonPublished`, `LessonVersionRolledBack`, `LessonArchived`,
  `ObjectiveAdded/Updated`, `MediaAssetApproved`. Full envelopes, schemas, versioning, and consumer
  contracts are in [EVENT_MODEL.md](EVENT_MODEL.md).
- Events are integration facts, retained until delivery + a short audit window, then pruned —
  **distinct from `audit_log`**, which is the permanent record.

---

## 18. Backup strategy

Aligned with doc 56 (BC/DR) and doc 57 (retention); tuned to this store's profile (small OLTP,
append-heavy audit/version tables).

- **Continuous WAL archiving + base backups (PITR).** Daily base backup; WAL shipped continuously
  to object storage in a separate region. Target **RPO ≤ 5 minutes** (doc 56).
- **Logical dumps** of the `curriculum_studio` schema nightly for portability and fine-grained
  restore (a single accidentally-corrupted lesson can be restored without a full cluster PITR).
- **Immutable/versioned backup bucket** with object-lock (WORM) so backups themselves are
  tamper-evident and ransomware-resistant — consistent with the audit-integrity posture.
- **Version/audit tables** are append-only, so incremental backups are cheap; cold partitions are
  backed up once and then immutable.
- **Restore is tested, not assumed.** A scheduled restore-rehearsal job (monthly) restores the
  latest backup into a scratch instance, runs the audit hash-chain verifier and a row-count
  reconciliation, and reports. A backup that has never been restored is not a backup.
- Encryption at rest for backups; keys managed per doc 56; backup access is least-privilege and
  audited.

---

## 19. Disaster recovery

- **Tiers (doc 56).** AZ failure → automatic failover to a synchronous standby, **RTO minutes,
  RPO 0**. Region failure → promote the cross-region asynchronous replica, **RTO ≤ 1 hour, RPO ≤ 5
  min** (bounded by async lag).
- **Replication topology.** Primary + synchronous standby in-region (HA) + asynchronous replica
  cross-region (DR). Read replicas additionally offload internal reporting reads.
- **Because publication is event-driven and idempotent**, a DR failover that replays a few
  in-flight outbox rows is safe: consumers dedupe on `(lesson_id, version_no)`, so at-least-once
  redelivery after failover cannot double-publish. This is a concrete payoff of the outbox design.
- **Runbook.** Detect → verify replica health/lag → promote → repoint the app via service discovery
  (no hardcoded primary) → resume the outbox relay (it picks up unpublished rows) → verify audit
  hash chain intact → announce. The runbook is rehearsed in DR game-days (doc 56).
- **Data-integrity check post-DR**: run the hash-chain verifier and `content_hash` re-computation on
  a sample of versions to prove nothing was silently corrupted in the failover.

---

## 20. Migration strategy

- **Alembic**, one linear history, autogenerate-assisted but **always human-reviewed** (autogen
  misses partial indexes, triggers, RLS, partitioning — these are hand-authored in the migration).
- **Every migration is reversible.** Each has a real `downgrade()` that restores the prior schema;
  irreversible operations (a destructive drop) are forbidden without an explicit, reviewed data
  backfill/rollback plan. Reversibility is tested in CI (`upgrade head` → `downgrade base` →
  `upgrade head` on a throwaway Postgres) — not just asserted.
- **Expand/contract (parallel-change) for zero-downtime**: additive expand (new nullable column /
  new table / new index `CONCURRENTLY`) → backfill → dual-write/dual-read in the app → switch reads
  → contract (drop old) in a *later* release. No single migration both adds and removes a
  contract-visible shape.
- **Online-safe operations only** on live tables: `CREATE INDEX CONCURRENTLY`, `ADD COLUMN` with no
  volatile default, `NOT VALID` constraints then `VALIDATE` — never a long table rewrite under lock.
- **Partitioned tables** (`audit_log`) get partitions provisioned ahead of time by a maintenance
  migration/job so writes never hit a missing partition.
- **Seed/reference data** (education systems, grades, subjects, the NCP objective roster) ships as
  **data migrations** that are idempotent (upsert-by-natural-key) and reversible, kept separate
  from schema migrations.
- The baseline migration (`0001_initial`) creates the schema, all tables, constraints, indexes,
  triggers (search vector, audit append-only, version immutability), and RLS policies — reviewed as
  a unit and verified against a real Postgres before implementation proceeds.

---

## Traceability

| Requirement in the brief | Addressed by |
| --- | --- |
| 1,000,000+ students | §0 boundary — served by derived read models, not this store |
| millions of lesson interactions | §0, §16 — owned by Delivery/Analytics; only aggregates return |
| tens of thousands of curriculum objects | §2–§4 — normalized authoring schema sized for this |
| complete audit history | §7 — hash-chained append-only `audit_log` (+ `workflow_transition`) |
| version control | §6, §11 — immutable snapshot versions + content hashing + rollback |
| multilingual content | §12 — body `LocalizedText` + `translation` governance index |
| AI teaching objects | §2 — in `body`, validated by the domain; searchable via extracted fields |
| assessment objects | §2, §16 — in `body`; item stats fed back as aggregates |
| media assets | §13 — content-addressed registry + M:N + object storage |
| offline synchronization | §14 — `offline_package` manifest pinned to an immutable version |
| future provincial variants | §1, §3 — `education_system.parent_system_id`; additive rows |
| future international curriculum | §1, §12 — new systems + locales are rows, no DDL |
| No shortcuts / justified denormalization | §2 — the one hybrid choice, justified in-line |
| Every table documented | POSTGRES_SCHEMA.md — Purpose on each |
| Every index justified | §4 + POSTGRES_SCHEMA.md |
| Every FK intentional | POSTGRES_SCHEMA.md — FK table with ON DELETE rationale |
| Every migration reversible | §20 — tested in CI |
| Decade without redesign | Additive-by-construction taxonomy, JSONB body evolution, outbox egress |
