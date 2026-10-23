"""identity.staff_account — operator-provisioned Curriculum Studio staff

Revision ID: 0010_staff_accounts
Revises: 0009_evidence_erasure
Create Date: 2026-10-23

Curriculum reviewers previously signed in to the Studio by pasting an access token an operator had
minted by hand with the signing key. This table gives each reviewer a real account: an operator
(`system`) creates it with exactly one Studio role, and the reviewer signs in with a passphrase.

Shape:

- Its own table, not a guardian, teacher, or learner row, so no account type can be turned into
  another by flipping a column.
- ``role`` is constrained by a CHECK to the seven Curriculum Studio roles. A staff account can never
  hold ``student``, ``guardian``, ``teacher``, ``mentor`` or ``system`` — even a direct write to the
  table cannot grant one.
- ``staff_ref`` is the token subject (``stf_<uuid7>``): one person, one stable pseudonymous subject,
  which the Studio's self-approval check relies on.
- ``email`` is unique (the sign-in handle); only the PBKDF2 hash of the passphrase is stored.
- ``version`` is the optimistic-lock column, as on the other mutable identity tables.

Reversible: ``downgrade`` drops the table.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_staff_accounts"
down_revision: str | None = "0009_evidence_erasure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STAFF_ROLES = (
    "subject_author",
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
    "curriculum_architect",
)
_ROLE_LIST = ", ".join(f"'{role}'" for role in STAFF_ROLES)

UPGRADE_STATEMENTS: tuple[str, ...] = (
    f"""
    CREATE TABLE identity.staff_account (
        staff_ref       varchar(64) PRIMARY KEY,
        email           varchar(254) NOT NULL UNIQUE,
        passphrase_hash text NOT NULL,
        display_name    varchar(60) NOT NULL,
        role            varchar(32) NOT NULL,
        status          varchar(16) NOT NULL DEFAULT 'active',
        failed_attempts integer NOT NULL DEFAULT 0,
        created_at      double precision NOT NULL DEFAULT 0,
        created_by      varchar(64) NOT NULL DEFAULT '',
        version         integer NOT NULL DEFAULT 1,
        CONSTRAINT ck_staff_role CHECK (role IN ({_ROLE_LIST})),
        CONSTRAINT ck_staff_ref CHECK (left(staff_ref, 4) = 'stf_')
    )
    """,
    "COMMENT ON TABLE identity.staff_account IS "
    "'Operator-provisioned Curriculum Studio staff. Exactly one Studio role per account (CHECK); "
    "staff_ref is the stable pseudonymous token subject. Only the passphrase hash is stored.'",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS identity.staff_account")
