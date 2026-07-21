"""curriculum_studio baseline schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-20

Creates the entire curriculum_studio schema exactly as specified in
docs/10-curriculum-studio/persistence/POSTGRES_SCHEMA.md: 18 tables (one partitioned), all
constraints and indexes (partial where the design calls for it), the FTS search-vector column +
trigger, the append-only/immutability triggers, and RLS on the lesson table.

Reversibility: the baseline is fully reversible — ``downgrade`` drops the schema (CASCADE), removing
every object created here. Shared extensions (pg_trgm, btree_gin) live in ``public`` and are left in
place on downgrade because other contexts may depend on them (they are created IF NOT EXISTS).

This migration is PostgreSQL-specific by design (JSONB, tsvector, partitioning, triggers, RLS). The
unit-test suite exercises the ORM against SQLite via ``metadata.create_all``; this migration is the
authoritative production schema and is verified upgrade->downgrade->upgrade against real PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_STATEMENTS: tuple[str, ...] = (
    "CREATE SCHEMA IF NOT EXISTS curriculum_studio",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE EXTENSION IF NOT EXISTS btree_gin",
    # ---------------------------------------------------------------- taxonomy layer
    """
    CREATE TABLE curriculum_studio.education_system (
        id                 uuid PRIMARY KEY,
        parent_system_id   uuid REFERENCES curriculum_studio.education_system (id) ON DELETE RESTRICT,
        system_key         text NOT NULL,
        name               text NOT NULL,
        jurisdiction       text NOT NULL,
        curriculum_version text NOT NULL,
        created_at         timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_system_key UNIQUE (system_key),
        CONSTRAINT ck_system_jurisdiction
            CHECK (jurisdiction IN ('national','provincial','international'))
    )
    """,
    "COMMENT ON TABLE curriculum_studio.education_system IS "
    "'Curriculum authority/edition; parent_system_id yields provincial/international variants.'",
    """
    CREATE TABLE curriculum_studio.grade (
        id            uuid PRIMARY KEY,
        system_id     uuid NOT NULL REFERENCES curriculum_studio.education_system (id) ON DELETE CASCADE,
        grade_key     text NOT NULL,
        display_order int  NOT NULL,
        CONSTRAINT uq_grade UNIQUE (system_id, grade_key)
    )
    """,
    """
    CREATE TABLE curriculum_studio.subject (
        id              uuid PRIMARY KEY,
        system_id       uuid NOT NULL REFERENCES curriculum_studio.education_system (id) ON DELETE CASCADE,
        subject_key     text NOT NULL,
        titles          jsonb NOT NULL DEFAULT '{}'::jsonb,
        religious_track boolean NOT NULL DEFAULT false,
        CONSTRAINT uq_subject UNIQUE (system_id, subject_key)
    )
    """,
    """
    CREATE TABLE curriculum_studio.curriculum_objective (
        id                 uuid PRIMARY KEY,
        system_id          uuid NOT NULL REFERENCES curriculum_studio.education_system (id) ON DELETE RESTRICT,
        standard_code      text NOT NULL,
        curriculum_version text NOT NULL,
        grade_key          text NOT NULL,
        subject_key        text NOT NULL,
        competency         text NOT NULL DEFAULT '',
        description        jsonb NOT NULL DEFAULT '{}'::jsonb,
        provenance         jsonb NOT NULL DEFAULT '{}'::jsonb,
        lock_version       int  NOT NULL DEFAULT 1,
        created_at         timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_objective_code UNIQUE (system_id, curriculum_version, standard_code)
    )
    """,
    "CREATE INDEX ix_objective_placement ON curriculum_studio.curriculum_objective "
    "(system_id, grade_key, subject_key)",
    """
    CREATE TABLE curriculum_studio.objective_prereq (
        objective_id    uuid NOT NULL REFERENCES curriculum_studio.curriculum_objective (id) ON DELETE CASCADE,
        prerequisite_id uuid NOT NULL REFERENCES curriculum_studio.curriculum_objective (id) ON DELETE CASCADE,
        PRIMARY KEY (objective_id, prerequisite_id),
        CONSTRAINT ck_prereq_no_self CHECK (objective_id <> prerequisite_id)
    )
    """,
    "CREATE INDEX ix_prereq_reverse ON curriculum_studio.objective_prereq (prerequisite_id)",
    # ---------------------------------------------------------------- authoring layer
    """
    CREATE TABLE curriculum_studio.lesson (
        id                     uuid PRIMARY KEY,
        system_id              uuid NOT NULL REFERENCES curriculum_studio.education_system (id) ON DELETE RESTRICT,
        lesson_key             text NOT NULL,
        grade_key              text NOT NULL,
        subject_key            text NOT NULL,
        chapter_key            text NOT NULL DEFAULT '',
        topic_key              text NOT NULL DEFAULT '',
        state                  text NOT NULL DEFAULT 'draft',
        difficulty             text NOT NULL DEFAULT 'intro',
        estimated_duration_min int  NOT NULL DEFAULT 15,
        author_role            text NOT NULL DEFAULT 'subject_author',
        derivation             text NOT NULL DEFAULT 'authored-original',
        license                text NOT NULL DEFAULT 'authored-original',
        content_hash           text NOT NULL DEFAULT '',
        current_version_no     int  NOT NULL DEFAULT 0,
        lock_version           int  NOT NULL DEFAULT 1,
        tags                   text[] NOT NULL DEFAULT '{}',
        body                   jsonb NOT NULL,
        search_vector          tsvector,
        created_at             timestamptz NOT NULL DEFAULT now(),
        updated_at             timestamptz NOT NULL DEFAULT now(),
        deleted_at             timestamptz,
        created_by             text NOT NULL DEFAULT '',
        updated_by             text NOT NULL DEFAULT '',
        CONSTRAINT uq_lesson_system_key UNIQUE (system_id, lesson_key),
        CONSTRAINT ck_lesson_state CHECK (state IN
            ('draft','in_review','subject_expert','educational_qa','accessibility',
             'language','ai_safety','approved','published','archived')),
        CONSTRAINT ck_lesson_difficulty CHECK (difficulty IN
            ('intro','developing','secure','challenge')),
        CONSTRAINT ck_lesson_duration CHECK (estimated_duration_min BETWEEN 1 AND 240),
        CONSTRAINT ck_lesson_provenance CHECK (
            derivation IN ('authored-original','ingested')
            AND license NOT ILIKE '%all rights reserved%'
        )
    )
    """,
    "COMMENT ON TABLE curriculum_studio.lesson IS "
    "'Lesson aggregate root / mutable working head; body holds the authored document.'",
    # Partial indexes (hot paths exclude soft-deleted rows) — architecture §4.
    "CREATE INDEX ix_lesson_placement ON curriculum_studio.lesson "
    "(system_id, grade_key, subject_key, state) WHERE deleted_at IS NULL",
    "CREATE INDEX ix_lesson_state ON curriculum_studio.lesson (state) WHERE deleted_at IS NULL",
    "CREATE INDEX ix_lesson_updated_at ON curriculum_studio.lesson (updated_at DESC)",
    "CREATE INDEX gin_lesson_search ON curriculum_studio.lesson USING gin (search_vector)",
    "CREATE INDEX gin_lesson_body ON curriculum_studio.lesson USING gin (body jsonb_path_ops)",
    "CREATE INDEX gin_lesson_tags ON curriculum_studio.lesson USING gin (tags)",
    "CREATE INDEX ix_lesson_trgm_key ON curriculum_studio.lesson USING gin (lesson_key gin_trgm_ops)",
    """
    CREATE TABLE curriculum_studio.lesson_version (
        id                    uuid PRIMARY KEY,
        lesson_id             uuid NOT NULL REFERENCES curriculum_studio.lesson (id) ON DELETE RESTRICT,
        version_no            int  NOT NULL,
        content_hash          text NOT NULL,
        body_snapshot         jsonb NOT NULL,
        gate_results_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
        change_summary        text NOT NULL DEFAULT '',
        author_role           text NOT NULL DEFAULT '',
        created_at            timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_version_lesson_no UNIQUE (lesson_id, version_no)
    )
    """,
    "CREATE INDEX ix_version_lesson_created ON curriculum_studio.lesson_version "
    "(lesson_id, created_at DESC)",
    """
    CREATE TABLE curriculum_studio.lesson_objective (
        lesson_id    uuid NOT NULL REFERENCES curriculum_studio.lesson (id) ON DELETE CASCADE,
        objective_id uuid NOT NULL REFERENCES curriculum_studio.curriculum_objective (id) ON DELETE RESTRICT,
        role         text NOT NULL,
        PRIMARY KEY (lesson_id, objective_id, role),
        CONSTRAINT ck_lo_role CHECK (role IN ('outcome','prerequisite'))
    )
    """,
    "CREATE INDEX ix_lo_objective ON curriculum_studio.lesson_objective (objective_id, role)",
    """
    CREATE TABLE curriculum_studio.quality_gate_result (
        id            uuid PRIMARY KEY,
        lesson_id     uuid NOT NULL REFERENCES curriculum_studio.lesson (id) ON DELETE CASCADE,
        gate          text NOT NULL,
        passed        boolean NOT NULL,
        mode          text NOT NULL,
        reviewer_role text NOT NULL DEFAULT '',
        findings      jsonb NOT NULL DEFAULT '[]'::jsonb,
        created_at    timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_gate_mode CHECK (mode IN ('auto','human')),
        CONSTRAINT uq_gate_per_lesson UNIQUE (lesson_id, gate)
    )
    """,
    "CREATE INDEX ix_gate_lesson ON curriculum_studio.quality_gate_result (lesson_id, gate)",
    """
    CREATE TABLE curriculum_studio.workflow_transition (
        id         uuid PRIMARY KEY,
        lesson_id  uuid NOT NULL REFERENCES curriculum_studio.lesson (id) ON DELETE CASCADE,
        from_state text NOT NULL,
        to_state   text NOT NULL,
        action     text NOT NULL,
        actor_role text NOT NULL,
        note       text NOT NULL DEFAULT '',
        at         timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX ix_transition_lesson_at ON curriculum_studio.workflow_transition (lesson_id, at)",
    # ---------------------------------------------------------------- supporting layer
    """
    CREATE TABLE curriculum_studio.media_asset (
        id           uuid PRIMARY KEY,
        kind         text NOT NULL,
        storage_key  text,
        content_hash text NOT NULL,
        mime         text NOT NULL,
        byte_size    bigint NOT NULL DEFAULT 0,
        license      text NOT NULL,
        origin       text NOT NULL,
        scan_status  text NOT NULL DEFAULT 'pending',
        alt_text     jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at   timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_media_hash UNIQUE (content_hash),
        CONSTRAINT ck_media_scan CHECK (scan_status IN ('pending','clean','flagged')),
        CONSTRAINT ck_media_origin CHECK (origin IN ('authored','cc0','licensed')),
        CONSTRAINT ck_media_provenance CHECK (license NOT ILIKE '%all rights reserved%')
    )
    """,
    "CREATE INDEX ix_media_scan ON curriculum_studio.media_asset (scan_status)",
    """
    CREATE TABLE curriculum_studio.lesson_media (
        lesson_id uuid NOT NULL REFERENCES curriculum_studio.lesson (id) ON DELETE CASCADE,
        media_id  uuid NOT NULL REFERENCES curriculum_studio.media_asset (id) ON DELETE RESTRICT,
        role      text NOT NULL,
        PRIMARY KEY (lesson_id, media_id, role)
    )
    """,
    "CREATE INDEX ix_lesson_media_media ON curriculum_studio.lesson_media (media_id)",
    """
    CREATE TABLE curriculum_studio.attachment (
        id           uuid PRIMARY KEY,
        lesson_id    uuid NOT NULL REFERENCES curriculum_studio.lesson (id) ON DELETE CASCADE,
        kind         text NOT NULL,
        storage_key  text NOT NULL,
        content_hash text NOT NULL,
        byte_size    bigint NOT NULL DEFAULT 0,
        version_no   int NOT NULL DEFAULT 0,
        created_at   timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX ix_attachment_lesson ON curriculum_studio.attachment (lesson_id)",
    """
    CREATE TABLE curriculum_studio.offline_package (
        id          uuid PRIMARY KEY,
        lesson_id   uuid NOT NULL REFERENCES curriculum_studio.lesson (id) ON DELETE CASCADE,
        version_no  int NOT NULL,
        manifest    jsonb NOT NULL,
        storage_key text NOT NULL,
        byte_size   bigint NOT NULL DEFAULT 0,
        checksum    text NOT NULL,
        built_at    timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_offline_pkg UNIQUE (lesson_id, version_no)
    )
    """,
    """
    CREATE TABLE curriculum_studio.translation (
        id            uuid PRIMARY KEY,
        entity_type   text NOT NULL,
        entity_id     uuid NOT NULL,
        field_path    text NOT NULL,
        locale        text NOT NULL,
        status        text NOT NULL DEFAULT 'missing',
        reviewer_role text NOT NULL DEFAULT '',
        updated_at    timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_translation UNIQUE (entity_type, entity_id, field_path, locale),
        CONSTRAINT ck_translation_status
            CHECK (status IN ('missing','draft','translated','reviewed'))
    )
    """,
    "CREATE INDEX ix_translation_target ON curriculum_studio.translation "
    "(entity_type, entity_id, locale)",
    "CREATE INDEX ix_translation_status ON curriculum_studio.translation (status, locale)",
    # audit_log: partitioned by month on `at`; DEFAULT partition guarantees inserts never fail,
    # monthly partitions are provisioned ahead by a maintenance job (architecture §7, §20).
    """
    CREATE TABLE curriculum_studio.audit_log (
        id             uuid NOT NULL,
        entity_type    text NOT NULL,
        entity_id      uuid NOT NULL,
        action         text NOT NULL,
        actor_role     text NOT NULL DEFAULT '',
        before         jsonb,
        after          jsonb,
        at             timestamptz NOT NULL DEFAULT now(),
        correlation_id text NOT NULL DEFAULT '',
        prev_hash      text NOT NULL DEFAULT '',
        row_hash       text NOT NULL,
        PRIMARY KEY (id, at)
    ) PARTITION BY RANGE (at)
    """,
    "CREATE TABLE curriculum_studio.audit_log_default "
    "PARTITION OF curriculum_studio.audit_log DEFAULT",
    "CREATE INDEX ix_audit_entity ON curriculum_studio.audit_log (entity_type, entity_id, at)",
    "CREATE INDEX ix_audit_correlation ON curriculum_studio.audit_log (correlation_id)",
    """
    CREATE TABLE curriculum_studio.outbox (
        id                uuid PRIMARY KEY,
        aggregate_type    text NOT NULL,
        aggregate_id      uuid NOT NULL,
        event_type        text NOT NULL,
        event_version     int  NOT NULL DEFAULT 1,
        payload           jsonb NOT NULL,
        occurred_at       timestamptz NOT NULL DEFAULT now(),
        published_at      timestamptz,
        delivery_attempts int NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX ix_outbox_unpublished ON curriculum_studio.outbox (occurred_at) "
    "WHERE published_at IS NULL",
    "CREATE INDEX ix_outbox_aggregate ON curriculum_studio.outbox "
    "(aggregate_type, aggregate_id, occurred_at)",
    """
    CREATE TABLE curriculum_studio.item_statistics (
        id                     uuid PRIMARY KEY,
        item_ref               text NOT NULL,
        lesson_id              uuid REFERENCES curriculum_studio.lesson (id) ON DELETE CASCADE,
        attempts               bigint NOT NULL DEFAULT 0,
        p_value                numeric(5,4),
        discrimination         numeric(5,4),
        mean_time_s            numeric(8,2),
        misconception_hit_rate jsonb NOT NULL DEFAULT '{}'::jsonb,
        sample_window          text NOT NULL DEFAULT '',
        updated_at             timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_item_stats UNIQUE (item_ref, sample_window)
    )
    """,
    "CREATE INDEX ix_item_stats_lesson ON curriculum_studio.item_statistics (lesson_id)",
    # ---------------------------------------------------------------- FTS trigger (architecture §5)
    """
    CREATE FUNCTION curriculum_studio.cs_lesson_search_vector() RETURNS trigger AS $$
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
    $$ LANGUAGE plpgsql
    """,
    "CREATE TRIGGER trg_lesson_search BEFORE INSERT OR UPDATE OF body, tags "
    "ON curriculum_studio.lesson FOR EACH ROW "
    "EXECUTE FUNCTION curriculum_studio.cs_lesson_search_vector()",
    # ------------------------------------------------- append-only / immutable guards (§6, §7)
    """
    CREATE FUNCTION curriculum_studio.cs_forbid_mutation() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'append-only table %: % is forbidden', TG_TABLE_NAME, TG_OP;
    END;
    $$ LANGUAGE plpgsql
    """,
    "CREATE TRIGGER trg_version_immutable BEFORE UPDATE OR DELETE "
    "ON curriculum_studio.lesson_version FOR EACH ROW "
    "EXECUTE FUNCTION curriculum_studio.cs_forbid_mutation()",
    "CREATE TRIGGER trg_transition_immutable BEFORE UPDATE OR DELETE "
    "ON curriculum_studio.workflow_transition FOR EACH ROW "
    "EXECUTE FUNCTION curriculum_studio.cs_forbid_mutation()",
    # audit_log is partitioned; attach the immutability trigger to the partition that receives rows.
    "CREATE TRIGGER trg_audit_immutable BEFORE UPDATE OR DELETE "
    "ON curriculum_studio.audit_log_default FOR EACH ROW "
    "EXECUTE FUNCTION curriculum_studio.cs_forbid_mutation()",
    # ---------------------------------------------------------------- RLS (defence in depth, doc 09)
    "ALTER TABLE curriculum_studio.lesson ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY lesson_visibility ON curriculum_studio.lesson
        USING (deleted_at IS NULL OR current_setting('app.can_see_deleted', true) = 'on')
    """,
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Fully reversible baseline: dropping the schema removes every table, index, trigger, function,
    # and policy created above. Shared public extensions are intentionally left in place.
    op.execute("DROP SCHEMA IF EXISTS curriculum_studio CASCADE")
