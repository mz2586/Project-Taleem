# Curriculum Studio — Physical PostgreSQL Schema

Companion to [DATABASE_ARCHITECTURE.md](DATABASE_ARCHITECTURE.md) and [ERD.md](ERD.md).
Target: **PostgreSQL 16+**. All objects in schema `curriculum_studio`. This is the authoritative
physical reference; the Alembic baseline migration (`0001_initial`) implements exactly this.

Conventions:

- **Keys**: `uuid` primary keys, values generated **UUIDv7** (time-ordered) in the application
  layer (`ids.uuid7()`), so B-tree PK inserts stay append-friendly. (Postgres 18's native
  `uuidv7()` can replace the app default later with no schema change — the column type is unchanged.)
- **Time**: `timestamptz` everywhere, UTC. `now()` defaults where a server timestamp is correct.
- **Text**: `text` (never `varchar(n)` unless a length is a real domain rule); length rules are
  `CHECK`s so they are visible and named.
- **Money/scores**: `numeric` (never float) for `p_value`/`discrimination`.
- Every table has a `COMMENT` (its Purpose). Every non-obvious column has a `COMMENT`.
- No table uses `BYTEA` for large binaries — bytes live in object storage; the DB holds pointers.

Each table below lists **Purpose**, its DDL, and its indexes with justification. A consolidated
foreign-key table (with `ON DELETE` rationale) and the trigger/RLS/partition definitions follow.

---

## Extensions and schema

```sql
CREATE SCHEMA IF NOT EXISTS curriculum_studio;
SET search_path = curriculum_studio, public;

-- pg_trgm: fuzzy/substring authoring search (architecture §5).
CREATE EXTENSION IF NOT EXISTS pg_trgm;
-- btree_gin: composite GIN (tsvector + scalar) if needed for combined search filters.
CREATE EXTENSION IF NOT EXISTS btree_gin;
-- NOTE: UUIDs are generated app-side (UUIDv7). No uuid-ossp/pgcrypto dependency required.
```

---

## Taxonomy layer

### `education_system`

Purpose: one curriculum authority/edition (e.g. NCP national, a provincial variant, or a future
international curriculum). Self-referential `parent_system_id` is **the** extension point for
provincial and international variants — new curricula are rows, never DDL (architecture §1, §3).

```sql
CREATE TABLE education_system (
    id                 uuid PRIMARY KEY,
    parent_system_id   uuid REFERENCES education_system (id) ON DELETE RESTRICT,
    system_key         text NOT NULL,               -- e.g. 'NCP-2023-NATIONAL'
    name               text NOT NULL,
    jurisdiction       text NOT NULL,               -- 'national' | 'provincial' | 'international'
    curriculum_version text NOT NULL,               -- edition tag, e.g. '2023'
    created_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_system_key UNIQUE (system_key),
    CONSTRAINT ck_system_jurisdiction
        CHECK (jurisdiction IN ('national', 'provincial', 'international'))
);
COMMENT ON TABLE education_system IS
  'Curriculum authority/edition; parent_system_id yields provincial/international variants.';
```

Indexes: PK; `uq_system_key` (business identity, and the lookup key lessons/objectives resolve
against). No other index — the table has tens of rows.

### `grade`

Purpose: the grade offering within a system (KG–G10 for NCP). Ordered for UI.

```sql
CREATE TABLE grade (
    id            uuid PRIMARY KEY,
    system_id     uuid NOT NULL REFERENCES education_system (id) ON DELETE CASCADE,
    grade_key     text NOT NULL,                    -- 'KG','G1'..'G10'
    display_order int  NOT NULL,
    CONSTRAINT uq_grade UNIQUE (system_id, grade_key)
);
COMMENT ON TABLE grade IS 'Grade offering within an education system.';
```

Indexes: PK; `uq_grade` (identity + the join key). `ON DELETE CASCADE`: grades are owned by their
system and meaningless without it.

### `subject`

Purpose: the subject offering within a system, with localized titles and the religious-track flag
(NCP separates the faith track). `titles` is JSONB `{locale: title}`.

```sql
CREATE TABLE subject (
    id              uuid PRIMARY KEY,
    system_id       uuid NOT NULL REFERENCES education_system (id) ON DELETE CASCADE,
    subject_key     text NOT NULL,                  -- 'math','urdu','islamiat',...
    titles          jsonb NOT NULL DEFAULT '{}'::jsonb,
    religious_track boolean NOT NULL DEFAULT false,
    CONSTRAINT uq_subject UNIQUE (system_id, subject_key)
);
COMMENT ON TABLE subject IS 'Subject offering within an education system (localized titles).';
```

Indexes: PK; `uq_subject`.

### `curriculum_objective`

Purpose: a Student Learning Outcome (SLO) with a stable `standard_code`, owned by a
system + `curriculum_version`. Lessons align to these; they form the prerequisite DAG. Versioning
the taxonomy independently (architecture §6) means a new NCP edition is a new set of rows and old
lessons keep referencing the edition they were authored against.

```sql
CREATE TABLE curriculum_objective (
    id                 uuid PRIMARY KEY,
    system_id          uuid NOT NULL REFERENCES education_system (id) ON DELETE RESTRICT,
    standard_code      text NOT NULL,               -- e.g. 'MATH-G1-N-01'
    curriculum_version text NOT NULL,
    grade_key          text NOT NULL,
    subject_key        text NOT NULL,
    competency         text NOT NULL DEFAULT '',
    description        jsonb NOT NULL DEFAULT '{}'::jsonb,   -- LocalizedText
    provenance         jsonb NOT NULL DEFAULT '{}'::jsonb,
    lock_version       int  NOT NULL DEFAULT 1,
    created_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_objective_code UNIQUE (system_id, curriculum_version, standard_code)
);
COMMENT ON TABLE curriculum_objective IS
  'Versioned SLO taxonomy; the alignment + prerequisite-DAG node lessons reference.';
```

Indexes:

- `uq_objective_code` — SLO identity within a system+version; the resolution key. Justification:
  every lesson-to-objective link and coverage query resolves by this.
- `ix_objective_placement (system_id, grade_key, subject_key)` — "which SLOs exist for this
  grade+subject" (coverage/authoring). Justification: the objective-picker and coverage report.

### `objective_prereq`

Purpose: the prerequisite **DAG** edges between objectives (doc 58 prerequisite graph). Composite
PK is the edge; the reverse index serves "what does this unlock".

```sql
CREATE TABLE objective_prereq (
    objective_id    uuid NOT NULL REFERENCES curriculum_objective (id) ON DELETE CASCADE,
    prerequisite_id uuid NOT NULL REFERENCES curriculum_objective (id) ON DELETE CASCADE,
    PRIMARY KEY (objective_id, prerequisite_id),
    CONSTRAINT ck_prereq_no_self CHECK (objective_id <> prerequisite_id)
);
COMMENT ON TABLE objective_prereq IS 'Prerequisite DAG edges between SLOs (acyclicity enforced in app).';
```

Indexes: PK `(objective_id, prerequisite_id)` (prerequisites-of traversal + edge identity);
`ix_prereq_reverse (prerequisite_id)` (unlocks traversal). `ON DELETE CASCADE`: an edge is
meaningless if either endpoint objective is removed. Acyclicity is enforced in the application
(a cycle check on insert) — Postgres cannot express a DAG constraint declaratively; documented.

---

## Authoring layer

### `lesson`

Purpose: the Lesson aggregate root and mutable working head (architecture §2, §3, §11). Queryable
facets are columns; the authored document is `body` JSONB; `search_vector` powers FTS.

```sql
CREATE TABLE lesson (
    id                     uuid PRIMARY KEY,
    system_id              uuid NOT NULL REFERENCES education_system (id) ON DELETE RESTRICT,
    lesson_key             text NOT NULL,               -- author-facing stable key
    grade_key              text NOT NULL,
    subject_key            text NOT NULL,
    chapter_key            text NOT NULL DEFAULT '',
    topic_key              text NOT NULL DEFAULT '',
    state                  text NOT NULL DEFAULT 'draft',
    difficulty             text NOT NULL DEFAULT 'intro',
    estimated_duration_min int  NOT NULL DEFAULT 15,
    author_role            text NOT NULL DEFAULT 'subject_author',
    derivation             text NOT NULL DEFAULT 'authored-original',  -- provenance summary
    license                text NOT NULL DEFAULT 'authored-original',
    content_hash           text NOT NULL DEFAULT '',
    current_version_no     int  NOT NULL DEFAULT 0,
    lock_version           int  NOT NULL DEFAULT 1,     -- optimistic lock (architecture §9)
    tags                   text[] NOT NULL DEFAULT '{}',
    body                   jsonb NOT NULL,              -- the authored document (architecture §2)
    search_vector          tsvector,                   -- maintained by trigger (architecture §5)
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    deleted_at             timestamptz,                -- soft delete (architecture §8)
    created_by             text NOT NULL DEFAULT '',
    updated_by             text NOT NULL DEFAULT '',
    CONSTRAINT uq_lesson_system_key UNIQUE (system_id, lesson_key),
    CONSTRAINT ck_lesson_state CHECK (state IN
        ('draft','in_review','subject_expert','educational_qa','accessibility',
         'language','ai_safety','approved','published','archived')),
    CONSTRAINT ck_lesson_difficulty CHECK (difficulty IN
        ('intro','developing','secure','challenge')),
    CONSTRAINT ck_lesson_duration CHECK (estimated_duration_min BETWEEN 1 AND 240),
    -- Provenance gate at the DB boundary: only original/CC0 content may exist (architecture §10, §13).
    CONSTRAINT ck_lesson_provenance CHECK (
        derivation IN ('authored-original','ingested')
        AND license NOT ILIKE '%all rights reserved%'
    )
);
COMMENT ON TABLE lesson IS
  'Lesson aggregate root / mutable working head; body holds the authored document.';
COMMENT ON COLUMN lesson.body IS 'Authored document (domain Lesson.to_dict minus bookkeeping).';
COMMENT ON COLUMN lesson.lock_version IS 'Optimistic-lock version; stale UPDATE matches 0 rows.';
```

Indexes (each justified in architecture §4):

```sql
CREATE INDEX ix_lesson_placement ON lesson (system_id, grade_key, subject_key, state)
    WHERE deleted_at IS NULL;                 -- console list by placement+state
CREATE INDEX ix_lesson_state ON lesson (state) WHERE deleted_at IS NULL;   -- workflow dashboards
CREATE INDEX ix_lesson_updated_at ON lesson (updated_at DESC);             -- "recently edited"
CREATE INDEX gin_lesson_search ON lesson USING gin (search_vector);        -- FTS
CREATE INDEX gin_lesson_body ON lesson USING gin (body jsonb_path_ops);    -- audit/migration @>
CREATE INDEX gin_lesson_tags ON lesson USING gin (tags);                   -- tag set-membership
CREATE INDEX ix_lesson_trgm_key ON lesson USING gin (lesson_key gin_trgm_ops); -- fuzzy key search
```

### `lesson_version`

Purpose: **immutable** published snapshot (architecture §6). Never updated or deleted; append-only.
Self-contained (`body_snapshot`) so it survives head archival. Grants revoke UPDATE/DELETE and a
trigger backs it.

```sql
CREATE TABLE lesson_version (
    id                    uuid PRIMARY KEY,
    lesson_id             uuid NOT NULL REFERENCES lesson (id) ON DELETE RESTRICT,
    version_no            int  NOT NULL,
    content_hash          text NOT NULL,
    body_snapshot         jsonb NOT NULL,
    gate_results_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
    change_summary        text NOT NULL DEFAULT '',
    author_role           text NOT NULL DEFAULT '',
    created_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_version_lesson_no UNIQUE (lesson_id, version_no)
);
COMMENT ON TABLE lesson_version IS 'Immutable published version snapshots; append-only, never updated.';
```

Indexes: `uq_version_lesson_no` (identity + "get version N"/"latest" ordered scan);
`ix_version_lesson_created (lesson_id, created_at DESC)` (version timeline). `ON DELETE RESTRICT`
on `lesson_id`: a lesson with published versions cannot be hard-deleted (it is soft-deleted).

### `lesson_objective`

Purpose: M:N alignment of lessons to SLOs, with `role` distinguishing outcomes from prerequisites
(architecture §3, §4). Relational (not a JSON array) because coverage and prerequisite queries are
relational.

```sql
CREATE TABLE lesson_objective (
    lesson_id    uuid NOT NULL REFERENCES lesson (id) ON DELETE CASCADE,
    objective_id uuid NOT NULL REFERENCES curriculum_objective (id) ON DELETE RESTRICT,
    role         text NOT NULL,                    -- 'outcome' | 'prerequisite'
    PRIMARY KEY (lesson_id, objective_id, role),
    CONSTRAINT ck_lo_role CHECK (role IN ('outcome','prerequisite'))
);
COMMENT ON TABLE lesson_objective IS 'Lesson↔SLO alignment (outcomes & prerequisites) for coverage queries.';
CREATE INDEX ix_lo_objective ON lesson_objective (objective_id, role);  -- reverse: lessons per SLO
```

`ON DELETE CASCADE` from lesson (links are owned by the lesson); `RESTRICT` from objective (you
cannot delete an SLO still referenced — protects coverage integrity).

### `quality_gate_result`

Purpose: current-head outcome of each of the 9 quality gates (architecture §7, §10). Rendered as
the gate strip; publication requires all green. Snapshots into `lesson_version` at publish.

```sql
CREATE TABLE quality_gate_result (
    id            uuid PRIMARY KEY,
    lesson_id     uuid NOT NULL REFERENCES lesson (id) ON DELETE CASCADE,
    gate          text NOT NULL,
    passed        boolean NOT NULL,
    mode          text NOT NULL,                    -- 'auto' | 'human'
    reviewer_role text NOT NULL DEFAULT '',
    findings      jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_gate_mode CHECK (mode IN ('auto','human')),
    CONSTRAINT uq_gate_per_lesson UNIQUE (lesson_id, gate)   -- one current result per gate
);
COMMENT ON TABLE quality_gate_result IS 'Current-head quality-gate outcomes; all must be green to publish.';
CREATE INDEX ix_gate_lesson ON quality_gate_result (lesson_id, gate);
```

### `workflow_transition`

Purpose: append-only workflow/review trail (architecture §7). A queryable first-class table because
review lineage is a product feature and a governance control.

```sql
CREATE TABLE workflow_transition (
    id         uuid PRIMARY KEY,
    lesson_id  uuid NOT NULL REFERENCES lesson (id) ON DELETE CASCADE,
    from_state text NOT NULL,
    to_state   text NOT NULL,
    action     text NOT NULL,
    actor_role text NOT NULL,
    note       text NOT NULL DEFAULT '',
    at         timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE workflow_transition IS 'Append-only review/workflow trail per lesson.';
CREATE INDEX ix_transition_lesson_at ON workflow_transition (lesson_id, at);
```

---

## Supporting layer

### `media_asset`

Purpose: content-addressed media registry (architecture §13). Bytes in object storage; DB holds
metadata + pointer. `content_hash` unique → dedupe + integrity. Provenance/scan `CHECK`s enforce
original/CC0-only and clean-before-link.

```sql
CREATE TABLE media_asset (
    id           uuid PRIMARY KEY,
    kind         text NOT NULL,                     -- svg|diagram|animation|audio|image|widget
    storage_key  text,                              -- null after license takedown (tombstone)
    content_hash text NOT NULL,
    mime         text NOT NULL,
    byte_size    bigint NOT NULL DEFAULT 0,
    license      text NOT NULL,
    origin       text NOT NULL,                     -- 'authored'|'cc0'|'licensed'
    scan_status  text NOT NULL DEFAULT 'pending',   -- 'pending'|'clean'|'flagged'
    alt_text     jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_media_hash UNIQUE (content_hash),
    CONSTRAINT ck_media_scan CHECK (scan_status IN ('pending','clean','flagged')),
    CONSTRAINT ck_media_provenance CHECK (
        origin IN ('authored','cc0','licensed')
        AND license NOT ILIKE '%all rights reserved%'
    )
);
COMMENT ON TABLE media_asset IS 'Content-addressed media registry (original/CC0 only, scanned).';
```

Indexes: `uq_media_hash` (dedupe/integrity + lookup); `ix_media_scan (scan_status)` for the
"pending scan" worklist.

### `lesson_media`

Purpose: M:N lesson↔asset links with role (architecture §13) — makes GC, offline packaging, and
integrity relational.

```sql
CREATE TABLE lesson_media (
    lesson_id uuid NOT NULL REFERENCES lesson (id) ON DELETE CASCADE,
    media_id  uuid NOT NULL REFERENCES media_asset (id) ON DELETE RESTRICT,
    role      text NOT NULL,
    PRIMARY KEY (lesson_id, media_id, role)
);
COMMENT ON TABLE lesson_media IS 'Lesson↔media links (role-tagged) for packaging & integrity.';
CREATE INDEX ix_lesson_media_media ON lesson_media (media_id);   -- reverse: lessons using an asset
```

`RESTRICT` on media: an asset in use cannot be deleted (integrity); GC only removes unreferenced
assets.

### `attachment`

Purpose: per-lesson generated downloadable artifacts (architecture §14).

```sql
CREATE TABLE attachment (
    id           uuid PRIMARY KEY,
    lesson_id    uuid NOT NULL REFERENCES lesson (id) ON DELETE CASCADE,
    kind         text NOT NULL,                     -- worksheet_pdf|printable|teacher_pack
    storage_key  text NOT NULL,
    content_hash text NOT NULL,
    byte_size    bigint NOT NULL DEFAULT 0,
    version_no   int NOT NULL DEFAULT 0,
    created_at   timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE attachment IS 'Per-lesson generated downloadable artifacts (bytes in object storage).';
CREATE INDEX ix_attachment_lesson ON attachment (lesson_id);
```

### `offline_package`

Purpose: self-contained offline bundle pinned to an immutable version (architecture §14) —
the offline-sync requirement. `manifest` lists assets + checksums + total size for resumable,
verifiable low-bandwidth download.

```sql
CREATE TABLE offline_package (
    id          uuid PRIMARY KEY,
    lesson_id   uuid NOT NULL REFERENCES lesson (id) ON DELETE CASCADE,
    version_no  int NOT NULL,
    manifest    jsonb NOT NULL,
    storage_key text NOT NULL,
    byte_size   bigint NOT NULL DEFAULT 0,
    checksum    text NOT NULL,
    built_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_offline_pkg UNIQUE (lesson_id, version_no)
);
COMMENT ON TABLE offline_package IS 'Offline day-pack bundle pinned to a specific immutable lesson version.';
```

Index: `uq_offline_pkg` (one pack per lesson version; the lookup key for the sync client).

### `translation`

Purpose: per-field localization **governance** index (architecture §12) — status/coverage the
language gate and future-language dashboards run on. Content itself lives in the body.

```sql
CREATE TABLE translation (
    id            uuid PRIMARY KEY,
    entity_type   text NOT NULL,                    -- 'lesson'|'curriculum_objective'|...
    entity_id     uuid NOT NULL,
    field_path    text NOT NULL,                    -- e.g. 'title','summary'
    locale        text NOT NULL,                    -- BCP-47-ish; app allowlist, not a DB enum
    status        text NOT NULL DEFAULT 'missing',
    reviewer_role text NOT NULL DEFAULT '',
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_translation UNIQUE (entity_type, entity_id, field_path, locale),
    CONSTRAINT ck_translation_status
        CHECK (status IN ('missing','draft','translated','reviewed'))
);
COMMENT ON TABLE translation IS 'Per-field localization status/coverage index (governance, not content).';
CREATE INDEX ix_translation_target ON translation (entity_type, entity_id, locale);
CREATE INDEX ix_translation_status ON translation (status, locale);   -- backlog: needs ur/en
```

`locale` is deliberately **not** a DB enum so a new language needs no migration (architecture §12).

### `audit_log`

Purpose: complete, hash-chained, append-only, tamper-evident audit (architecture §7).
**Partitioned by month** on `at`. References entities by `(entity_type, entity_id)`, no FK
(polymorphic + must outlive referents).

```sql
CREATE TABLE audit_log (
    id             uuid NOT NULL,
    entity_type    text NOT NULL,
    entity_id      uuid NOT NULL,
    action         text NOT NULL,                   -- create|update|publish|rollback|delete|...
    actor_role     text NOT NULL DEFAULT '',
    before         jsonb,
    after          jsonb,
    at             timestamptz NOT NULL DEFAULT now(),
    correlation_id text NOT NULL DEFAULT '',
    prev_hash      text NOT NULL DEFAULT '',
    row_hash       text NOT NULL,
    PRIMARY KEY (id, at)                              -- at in PK: required for partition key
) PARTITION BY RANGE (at);
COMMENT ON TABLE audit_log IS 'Hash-chained, append-only, month-partitioned audit of every mutation.';

CREATE INDEX ix_audit_entity ON audit_log (entity_type, entity_id, at);  -- history of one object
CREATE INDEX ix_audit_correlation ON audit_log (correlation_id);         -- one request footprint
```

Partitions are provisioned ahead by a maintenance job (architecture §20). Example first partition:

```sql
CREATE TABLE audit_log_2026_07 PARTITION OF audit_log
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
```

### `outbox`

Purpose: transactional outbox — the only egress (architecture §17, EVENT_MODEL.md). Written in the
same transaction as the state change; drained by the relay.

```sql
CREATE TABLE outbox (
    id               uuid PRIMARY KEY,
    aggregate_type   text NOT NULL,                  -- 'lesson'|'curriculum_objective'|...
    aggregate_id     uuid NOT NULL,
    event_type       text NOT NULL,                  -- 'LessonPublished'|...
    event_version    int  NOT NULL DEFAULT 1,
    payload          jsonb NOT NULL,
    occurred_at      timestamptz NOT NULL DEFAULT now(),
    published_at     timestamptz,                    -- null = undelivered
    delivery_attempts int NOT NULL DEFAULT 0
);
COMMENT ON TABLE outbox IS 'Transactional outbox; relay delivers undelivered rows at-least-once.';
-- Hot poll: only the undelivered backlog, in order. Partial index stays tiny.
CREATE INDEX ix_outbox_unpublished ON outbox (occurred_at) WHERE published_at IS NULL;
CREATE INDEX ix_outbox_aggregate ON outbox (aggregate_type, aggregate_id, occurred_at);
```

### `item_statistics`

Purpose: aggregated, **de-identified** psychometrics fed back from the warehouse for the
content-improvement loop (architecture §16). One row per item — never per-interaction. **No
`student_ref` — ever** (security invariant).

```sql
CREATE TABLE item_statistics (
    id                    uuid PRIMARY KEY,
    item_ref              text NOT NULL,             -- assessment item id within a lesson body
    lesson_id             uuid REFERENCES lesson (id) ON DELETE CASCADE,
    attempts              bigint NOT NULL DEFAULT 0,
    p_value               numeric(5,4),              -- difficulty (proportion correct)
    discrimination        numeric(5,4),
    mean_time_s           numeric(8,2),
    misconception_hit_rate jsonb NOT NULL DEFAULT '{}'::jsonb,
    sample_window         text NOT NULL DEFAULT '',
    updated_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_item_stats UNIQUE (item_ref, sample_window)
);
COMMENT ON TABLE item_statistics IS
  'Aggregated de-identified item psychometrics (from warehouse) for authoring feedback. No PII.';
CREATE INDEX ix_item_stats_lesson ON item_statistics (lesson_id);
```

---

## Foreign keys — consolidated, with `ON DELETE` rationale

Every FK is intentional. Polymorphic tables (`translation`, `audit_log`, `outbox`,
`item_statistics.item_ref`) reference by natural id **without** a DB FK — justified: they span
entity types and must outlive their referents; integrity is enforced in the Unit of Work.

| Child | Parent | On delete | Rationale |
| --- | --- | --- | --- |
| `education_system.parent_system_id` | `education_system` | RESTRICT | A parent curriculum with variants may not be deleted out from under them. |
| `grade.system_id` | `education_system` | CASCADE | Grades are owned by their system. |
| `subject.system_id` | `education_system` | CASCADE | Subjects are owned by their system. |
| `curriculum_objective.system_id` | `education_system` | RESTRICT | SLOs are the referenced taxonomy; deleting a system with SLOs would orphan lesson alignments — block it. |
| `objective_prereq.objective_id` | `curriculum_objective` | CASCADE | Edge is meaningless without its endpoint. |
| `objective_prereq.prerequisite_id` | `curriculum_objective` | CASCADE | Same. |
| `lesson.system_id` | `education_system` | RESTRICT | A lesson pins the system it was authored against. |
| `lesson_version.lesson_id` | `lesson` | RESTRICT | Immutable history must survive; lessons are soft-deleted, never hard-deleted while versioned. |
| `lesson_objective.lesson_id` | `lesson` | CASCADE | Alignment links are owned by the lesson. |
| `lesson_objective.objective_id` | `curriculum_objective` | RESTRICT | Cannot delete an SLO still covered by lessons (coverage integrity). |
| `quality_gate_result.lesson_id` | `lesson` | CASCADE | Head gate results are owned by the lesson. |
| `workflow_transition.lesson_id` | `lesson` | CASCADE | Trail is owned by the lesson (snapshotted into versions before any hard delete). |
| `lesson_media.lesson_id` | `lesson` | CASCADE | Link owned by lesson. |
| `lesson_media.media_id` | `media_asset` | RESTRICT | An asset in use may not be deleted. |
| `attachment.lesson_id` | `lesson` | CASCADE | Per-lesson output. |
| `offline_package.lesson_id` | `lesson` | CASCADE | Per-lesson output. |
| `item_statistics.lesson_id` | `lesson` | CASCADE | Feedback is per-lesson; nullable for orphan-tolerant ingestion. |

---

## Triggers

### Search-vector maintenance (architecture §5)

```sql
CREATE FUNCTION cs_lesson_search_vector() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('simple',
            coalesce(NEW.body #>> '{title,text,ur}', '') || ' ' ||
            coalesce(NEW.body #>> '{title,text,en}', '')), 'A') ||
        setweight(to_tsvector('simple', array_to_string(NEW.tags, ' ')), 'B') ||
        setweight(to_tsvector('english',
            coalesce(NEW.body #>> '{summary,text,en}', '') || ' ' ||
            coalesce(NEW.body #>> '{description,text,en}', '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_lesson_search
    BEFORE INSERT OR UPDATE OF body, tags ON lesson
    FOR EACH ROW EXECUTE FUNCTION cs_lesson_search_vector();
```

### Immutability / append-only guards (architecture §6, §7)

```sql
CREATE FUNCTION cs_forbid_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'append-only table %: % is forbidden', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_version_immutable
    BEFORE UPDATE OR DELETE ON lesson_version
    FOR EACH ROW EXECUTE FUNCTION cs_forbid_mutation();

CREATE TRIGGER trg_audit_immutable
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION cs_forbid_mutation();

CREATE TRIGGER trg_transition_immutable
    BEFORE UPDATE OR DELETE ON workflow_transition
    FOR EACH ROW EXECUTE FUNCTION cs_forbid_mutation();
```

Grants additionally revoke `UPDATE, DELETE` on these tables from the application role (defence in
depth — the trigger is the backstop, the grant is the primary control).

---

## Row-Level Security (doc 09)

RLS is enabled on author-editable tables so multi-author / role scoping composes with soft-delete.
Policies are keyed on a session variable set by the app (`app.actor_role`, `app.system_scope`).

```sql
ALTER TABLE lesson ENABLE ROW LEVEL SECURITY;
CREATE POLICY lesson_visibility ON lesson
    USING (deleted_at IS NULL OR current_setting('app.can_see_deleted', true) = 'on');
-- Additional write policies (who may edit which state) are defined with the auth model; the
-- authoritative workflow/no-self-approval rules remain in the domain/service layer.
```

RLS here is defence-in-depth; the primary authorization is the application PDP (deny-by-default).

---

## Object inventory (Purpose one-liners)

| Object | Kind | Purpose |
| --- | --- | --- |
| `education_system` | table | Curriculum authority/edition; variant extension point |
| `grade` | table | Grade offering within a system |
| `subject` | table | Subject offering within a system |
| `curriculum_objective` | table | Versioned SLO taxonomy node |
| `objective_prereq` | table | Prerequisite DAG edges |
| `lesson` | table | Lesson aggregate root / working head |
| `lesson_version` | table | Immutable published version snapshots |
| `lesson_objective` | table | Lesson↔SLO alignment |
| `quality_gate_result` | table | Current-head quality-gate outcomes |
| `workflow_transition` | table | Append-only review/workflow trail |
| `media_asset` | table | Content-addressed media registry |
| `lesson_media` | table | Lesson↔media links |
| `attachment` | table | Per-lesson downloadable artifacts |
| `offline_package` | table | Offline bundle pinned to a version |
| `translation` | table | Localization status/coverage index |
| `audit_log` | table (partitioned) | Hash-chained append-only audit |
| `outbox` | table | Transactional event outbox (egress) |
| `item_statistics` | table | De-identified item psychometrics feedback |
| `cs_lesson_search_vector` | function/trigger | Maintain FTS vector |
| `cs_forbid_mutation` | function/trigger | Enforce append-only/immutable tables |

Total: 18 tables (one partitioned), 2 trigger functions, RLS on author-editable tables. Every one
maps to a requirement in DATABASE_ARCHITECTURE.md §Traceability.
