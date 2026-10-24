"""school.submission (homework + marking), audit object refs, teacher-raised safeguarding concerns

Revision ID: 0013_homework
Revises: 0012_safeguarding
Create Date: 2026-10-24

HOMEWORK_AND_MARKING_CONTRACT.md. A child answers a written item of an assigned lesson; their
teacher marks it or returns it for another try.

- ``school.submission`` — child data (C2): the learner's own words (``text``), the teacher's mark
  and feedback. Pseudonymous ``student_ref`` only. One row per (assignment, item, learner): a
  resubmission replaces the text of the same row and bumps ``attempt``. Status and outcome are
  closed lists enforced by CHECKs, ``outcome`` is present exactly when ``status = 'marked'``, text
  and feedback are bounded, and ``version`` is the optimistic lock (two teachers marking at once:
  one gets a 409). The class and assignment foreign keys cascade, as enrolments do. Exported and
  erased with the learner by the privacy context.
- ``school.enrolment_audit.object_ref`` — the ``submission_id`` of a ``submission.*`` audit event
  ('' for enrolment events). The audit still holds refs only, never answer text or feedback.
- ``safeguarding.concern`` — ``raised_by_role`` admits ``teacher`` (a teacher's concern about a
  learner in their own class), and ``context_submission_id`` names the homework submission that
  prompted it.

Reversible. ``downgrade`` drops ``school.submission``, the audit column and
``context_submission_id``. It **refuses** while any teacher-raised concern exists: the restored
two-role CHECK cannot hold them, re-keying them would show them to a guardian, and a schema
rollback must never delete safeguarding records.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013_homework"
down_revision: str | None = "0012_safeguarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUBMISSION_STATUSES = ("submitted", "returned", "marked")
MARK_OUTCOMES = ("met", "not_yet")
RAISER_ROLES = ("student", "guardian", "teacher")
PREVIOUS_RAISER_ROLES = ("student", "guardian")
MAX_TEXT = 2000  # the longest written item's cap (long / word_problem)
MAX_FEEDBACK = 1000


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


UPGRADE_STATEMENTS: tuple[str, ...] = (
    f"""
    CREATE TABLE school.submission (
        submission_id   varchar(64) PRIMARY KEY,
        organization_id varchar(64) NOT NULL,
        class_id        varchar(64) NOT NULL
            REFERENCES school.classroom (class_id) ON DELETE CASCADE,
        assignment_id   varchar(64) NOT NULL
            REFERENCES school.assignment (assignment_id) ON DELETE CASCADE,
        objective_code  varchar(64) NOT NULL,
        item_ref        varchar(128) NOT NULL,
        student_ref     varchar(64) NOT NULL,
        text            text NOT NULL,
        status          varchar(16) NOT NULL,
        attempt         integer NOT NULL DEFAULT 1,
        max_score       integer,
        outcome         varchar(16),
        score           integer,
        feedback        text NOT NULL DEFAULT '',
        submitted_at    double precision NOT NULL,
        created_at      double precision NOT NULL,
        returned_at     double precision,
        marked_at       double precision,
        reviewed_by     varchar(64),
        version         integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_submission_item_learner UNIQUE (assignment_id, item_ref, student_ref),
        CONSTRAINT ck_submission_ref CHECK (left(submission_id, 4) = 'sub_'),
        CONSTRAINT ck_submission_status CHECK (status IN ({_in(SUBMISSION_STATUSES)})),
        CONSTRAINT ck_submission_outcome
            CHECK (outcome IS NULL OR outcome IN ({_in(MARK_OUTCOMES)})),
        CONSTRAINT ck_submission_marked_has_outcome
            CHECK ((status = 'marked') = (outcome IS NOT NULL)),
        CONSTRAINT ck_submission_text_bounded
            CHECK (char_length(text) BETWEEN 1 AND {MAX_TEXT}),
        CONSTRAINT ck_submission_feedback_bounded
            CHECK (char_length(feedback) <= {MAX_FEEDBACK}),
        CONSTRAINT ck_submission_attempt CHECK (attempt >= 1),
        CONSTRAINT ck_submission_score
            CHECK (score IS NULL OR (max_score IS NOT NULL AND score BETWEEN 0 AND max_score))
    )
    """,
    "CREATE INDEX ix_submission_org_class_status "
    "ON school.submission (organization_id, class_id, status)",
    "CREATE INDEX ix_submission_student ON school.submission (student_ref)",
    "COMMENT ON TABLE school.submission IS "
    "'Homework answers (C2 child data: the learner''s own words) and the teacher''s mark. "
    "Pseudonymous refs only; exported and erased with the learner.'",
    "ALTER TABLE school.enrolment_audit " "ADD COLUMN object_ref varchar(64) NOT NULL DEFAULT ''",
    "COMMENT ON TABLE school.enrolment_audit IS "
    "'Class-membership changes and homework submit/mark/return. Pseudonymous refs only, never "
    "answer text; erased with the learner.'",
    "ALTER TABLE safeguarding.concern ADD COLUMN context_submission_id varchar(64)",
    "ALTER TABLE safeguarding.concern DROP CONSTRAINT ck_concern_raised_by_role",
    f"ALTER TABLE safeguarding.concern ADD CONSTRAINT ck_concern_raised_by_role "
    f"CHECK (raised_by_role IN ({_in(RAISER_ROLES)}))",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Safeguarding records are never destroyed by a schema rollback: the restored two-role CHECK
    # cannot hold teacher-raised concerns, so refuse while any exist and leave the decision to the
    # safeguarding lead (export or re-home them first).
    teacher_concerns = (
        op.get_bind()
        .exec_driver_sql(
            "SELECT count(*) FROM safeguarding.concern WHERE raised_by_role = 'teacher'"
        )
        .scalar()
    )
    if teacher_concerns:
        raise RuntimeError(
            f"refusing to downgrade 0013_homework: {teacher_concerns} teacher-raised safeguarding "
            "concern(s) exist and would have to be deleted; resolve them with the safeguarding "
            "lead first"
        )
    op.execute("ALTER TABLE safeguarding.concern DROP CONSTRAINT ck_concern_raised_by_role")
    op.execute(
        f"ALTER TABLE safeguarding.concern ADD CONSTRAINT ck_concern_raised_by_role "
        f"CHECK (raised_by_role IN ({_in(PREVIOUS_RAISER_ROLES)}))"
    )
    op.execute("ALTER TABLE safeguarding.concern DROP COLUMN IF EXISTS context_submission_id")
    op.execute("ALTER TABLE school.enrolment_audit DROP COLUMN IF EXISTS object_ref")
    op.execute(
        "COMMENT ON TABLE school.enrolment_audit IS "
        "'Class-membership changes (join/leave). Pseudonymous refs only; erased with the learner.'"
    )
    op.execute("DROP TABLE IF EXISTS school.submission")
