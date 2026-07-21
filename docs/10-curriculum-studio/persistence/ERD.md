# Curriculum Studio — Entity-Relationship Diagram

Companion to [DATABASE_ARCHITECTURE.md](DATABASE_ARCHITECTURE.md) and
[POSTGRES_SCHEMA.md](POSTGRES_SCHEMA.md). All entities live in the single PostgreSQL schema
`curriculum_studio`. There are **no cross-context foreign keys** (doc 09); references to other
bounded contexts are by opaque id only and are not drawn here.

Notation: crow's-foot cardinality. `PK` primary key, `FK` foreign key, `UK` unique key.
`JSONB` columns holding the authored document body are shown as single attributes (their internal
shape is the domain aggregate, not a relational structure — see architecture §2).

---

## 1. Full schema ERD

```mermaid
erDiagram
    EDUCATION_SYSTEM ||--o{ EDUCATION_SYSTEM : "parent_of (variants)"
    EDUCATION_SYSTEM ||--o{ GRADE : offers
    EDUCATION_SYSTEM ||--o{ SUBJECT : offers
    EDUCATION_SYSTEM ||--o{ CURRICULUM_OBJECTIVE : defines
    EDUCATION_SYSTEM ||--o{ LESSON : scopes

    CURRICULUM_OBJECTIVE ||--o{ OBJECTIVE_PREREQ : "is target"
    CURRICULUM_OBJECTIVE ||--o{ OBJECTIVE_PREREQ : "is prerequisite"
    CURRICULUM_OBJECTIVE ||--o{ LESSON_OBJECTIVE : "aligned by"

    LESSON ||--o{ LESSON_OBJECTIVE : aligns
    LESSON ||--o{ LESSON_VERSION : "snapshots into"
    LESSON ||--o{ QUALITY_GATE_RESULT : "has head gates"
    LESSON ||--o{ WORKFLOW_TRANSITION : "has trail"
    LESSON ||--o{ LESSON_MEDIA : references
    LESSON ||--o{ ATTACHMENT : produces
    LESSON ||--o{ OFFLINE_PACKAGE : bundles

    MEDIA_ASSET ||--o{ LESSON_MEDIA : "linked by"

    LESSON {
        uuid id PK
        uuid system_id FK
        string lesson_key UK
        string grade_key
        string subject_key
        string chapter_key
        string topic_key
        string state
        string difficulty
        int estimated_duration_min
        string author_role
        string derivation
        string license
        string content_hash
        int current_version_no
        int lock_version
        string_array tags
        jsonb body
        tsvector search_vector
        timestamptz created_at
        timestamptz updated_at
        timestamptz deleted_at
        string created_by
        string updated_by
    }

    LESSON_VERSION {
        uuid id PK
        uuid lesson_id FK
        int version_no UK
        string content_hash
        jsonb body_snapshot
        jsonb gate_results_snapshot
        string change_summary
        string author_role
        timestamptz created_at
    }

    CURRICULUM_OBJECTIVE {
        uuid id PK
        uuid system_id FK
        string standard_code UK
        string curriculum_version UK
        string grade_key
        string subject_key
        string competency
        jsonb description
        jsonb provenance
        int lock_version
        timestamptz created_at
    }

    OBJECTIVE_PREREQ {
        uuid objective_id PK,FK
        uuid prerequisite_id PK,FK
    }

    LESSON_OBJECTIVE {
        uuid lesson_id PK,FK
        uuid objective_id PK,FK
        string role PK
    }

    QUALITY_GATE_RESULT {
        uuid id PK
        uuid lesson_id FK
        string gate
        boolean passed
        string mode
        string reviewer_role
        jsonb findings
        timestamptz created_at
    }

    WORKFLOW_TRANSITION {
        uuid id PK
        uuid lesson_id FK
        string from_state
        string to_state
        string action
        string actor_role
        string note
        timestamptz at
    }

    MEDIA_ASSET {
        uuid id PK
        string kind
        string storage_key
        string content_hash UK
        string mime
        bigint byte_size
        string license
        string origin
        string scan_status
        jsonb alt_text
        timestamptz created_at
    }

    LESSON_MEDIA {
        uuid lesson_id PK,FK
        uuid media_id PK,FK
        string role PK
    }

    ATTACHMENT {
        uuid id PK
        uuid lesson_id FK
        string kind
        string storage_key
        string content_hash
        bigint byte_size
        int version_no
        timestamptz created_at
    }

    OFFLINE_PACKAGE {
        uuid id PK
        uuid lesson_id FK
        int version_no
        jsonb manifest
        string storage_key
        bigint byte_size
        string checksum
        timestamptz built_at
    }

    EDUCATION_SYSTEM {
        uuid id PK
        uuid parent_system_id FK
        string system_key UK
        string name
        string jurisdiction
        string curriculum_version
        timestamptz created_at
    }

    GRADE {
        uuid id PK
        uuid system_id FK
        string grade_key
        int display_order
    }

    SUBJECT {
        uuid id PK
        uuid system_id FK
        string subject_key
        jsonb titles
        boolean religious_track
    }
```

---

## 2. Cross-cutting tables (not FK-linked into the aggregate graph)

`translation`, `audit_log`, `outbox`, and `item_statistics` reference domain rows **by
`(entity_type, entity_id)` / natural id, not by foreign key**, because they span entity types and
(for audit/outbox) must survive the deletion or archival of what they describe. Drawing FK edges
would wrongly couple their lifecycle to the referent.

```mermaid
erDiagram
    TRANSLATION {
        uuid id PK
        string entity_type
        uuid entity_id
        string field_path
        string locale
        string status
        string reviewer_role
        timestamptz updated_at
    }

    AUDIT_LOG {
        uuid id PK
        string entity_type
        uuid entity_id
        string action
        string actor_role
        jsonb before
        jsonb after
        timestamptz at
        string correlation_id
        string prev_hash
        string row_hash
    }

    OUTBOX {
        uuid id PK
        string aggregate_type
        uuid aggregate_id
        string event_type
        int event_version
        jsonb payload
        timestamptz occurred_at
        timestamptz published_at
        int delivery_attempts
    }

    ITEM_STATISTICS {
        uuid id PK
        string item_ref
        uuid lesson_id
        int attempts
        numeric p_value
        numeric discrimination
        numeric mean_time_s
        jsonb misconception_hit_rate
        string sample_window
        timestamptz updated_at
    }
```

`entity_type` / `aggregate_type` are logical discriminators (`lesson`, `curriculum_objective`,
`media_asset`, …). Referential integrity for these is enforced in the application/Unit of Work,
not by the database, and this is intentional: it is the standard trade-off for polymorphic audit
and outbox tables (documented in POSTGRES_SCHEMA.md §Foreign keys).

---

## 3. Aggregate boundaries overlaid

The transactional boundaries from architecture §3. A dashed grouping = one aggregate; one Unit of
Work commits within one grouping.

```mermaid
flowchart TB
    subgraph L["Lesson aggregate (one UoW)"]
        LESSON2["lesson (root)"]
        QGR["quality_gate_result (head)"]
        WT["workflow_transition"]
        LO["lesson_objective"]
        LM["lesson_media"]
        LESSON2 --> QGR
        LESSON2 --> WT
        LESSON2 --> LO
        LESSON2 --> LM
    end
    subgraph V["LessonVersion aggregate (immutable)"]
        LV["lesson_version"]
    end
    subgraph O["Objective aggregate"]
        OBJ["curriculum_objective"]
        PRE["objective_prereq"]
        OBJ --> PRE
    end
    subgraph M["Media aggregate"]
        MA["media_asset"]
    end
    subgraph T["Taxonomy aggregate"]
        ES["education_system"]
        GR["grade"]
        SU["subject"]
        ES --> GR
        ES --> SU
    end

    LESSON2 -. "publish → snapshot (by id)" .-> LV
    LO -. "references (by id)" .-> OBJ
    LM -. "references (by id)" .-> MA
    LESSON2 -. "scoped by (by id)" .-> ES

    OUTBOX2["outbox (egress, same UoW as its writer)"]
    LESSON2 -. "emits" .-> OUTBOX2
    OBJ -. "emits" .-> OUTBOX2
```

Solid arrows are intra-aggregate ownership (cascade within the boundary). Dashed arrows are
by-id references across aggregate boundaries (no cascade; eventual consistency via §17 events).
