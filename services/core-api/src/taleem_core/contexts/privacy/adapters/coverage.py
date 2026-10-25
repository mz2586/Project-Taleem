"""The explicit map of every table that is *not* learner data, and why.

Every table in every schema must be either covered by a ``LearnerDataPort`` or listed here. The
completeness test introspects all ORM metadata (and, on PostgreSQL, the live catalog), so a newly
added table fails CI until someone decides which side it belongs on.
"""

from __future__ import annotations

_CURRICULUM = (
    "education_system",
    "grade",
    "subject",
    "curriculum_objective",
    "objective_prereq",
    "lesson",
    "lesson_version",
    "lesson_objective",
    "quality_gate_result",
    "workflow_transition",
    "media_asset",
    "lesson_media",
    "attachment",
    "offline_package",
    "translation",
    "audit_log",
    "outbox",
    "item_statistics",
)

EXEMPT_TABLES: dict[str, str] = {
    "identity.guardian_account": (
        "the guardian is a separate data subject; erasing a learner leaves the adult account"
    ),
    "identity.guardian_recovery_code": (
        "the guardian's own recovery codes (adult credential, separate data subject): PBKDF2 "
        "digests only, never a learner ref; the guardian sees counts/timestamps only (/me); "
        "deleted with the guardian account (FK cascade) and superseded sets are deleted"
    ),
    "identity.rate_limit_bucket": (
        "short-lived window counters keyed by a SHA-256 digest (a client network identifier, or a "
        "rate-limited subject such as a safeguarding raiser); no ref in clear; purged by window"
    ),
    "identity.staff_account": (
        "a Curriculum Studio staff member, a separate adult data subject; no learner data"
    ),
    "ops.kill_switch": "operator control state; no learner data",
    "school.organization": "a school (tenant); no learner data",
    "school.teacher_account": "an adult staff member, a separate data subject; no learner data",
    "school.classroom": "a teacher's class; no learner data",
    "school.assignment": "lessons a teacher assigned to a class; no learner ref",
    **{
        f"curriculum_studio.{t}": "authored curriculum content and its workflow; no learner data"
        for t in _CURRICULUM
    },
}
# Bookkeeping tables outside the ORM metadata that exist in a migrated database.
EXEMPT_CATALOG_TABLES: dict[str, str] = {
    "public.alembic_version": "migration revision marker",
    "curriculum_studio.audit_log_default": "default partition of curriculum_studio.audit_log",
}
