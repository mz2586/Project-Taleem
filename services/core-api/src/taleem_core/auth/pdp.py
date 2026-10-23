"""Policy Decision Point — deny-by-default (pure-stdlib).

Implements the core authorization posture from docs/12: **deny by default**, **fail closed**.
M1 carries a tiny governance-safe policy set (only a `system` role may reach the demo protected
route). It implements NO child/guardian/mentor authorization — that is a Phase-2 item.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str


# Role groups for the Curriculum Studio authoring lifecycle.
_REVIEWER_ROLES = (
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
)
_CURRICULUM_ROLES = ("subject_author", "curriculum_architect", *_REVIEWER_ROLES)
# Public view of the Studio role set.
CURRICULUM_ROLES: tuple[str, ...] = _CURRICULUM_ROLES
# The safeguarding triage role (contexts/safeguarding). Deliberately NOT a Studio role and holding
# no curriculum, learning, school or identity permission: it reads safeguarding concerns and nothing
# else. The doc-15 "Safety Officer" curriculum reviewer (`safety_officer`) is a different role.
SAFEGUARDING_ROLES: tuple[str, ...] = ("safeguarding_lead",)
# Every role an operator-provisioned staff account may hold (identity/domain/staff.py pins its own
# copy equal to this one in a test).
STAFF_ACCOUNT_ROLES: tuple[str, ...] = (*_CURRICULUM_ROLES, *SAFEGUARDING_ROLES)


def _staff_rules() -> set[tuple[str, str, str]]:
    """Operators provision and suspend staff; each staff role reads its own account."""
    rules = {("system", "manage", "identity.staff")}
    rules |= {(r, "read", "identity.staff_self") for r in STAFF_ACCOUNT_ROLES}
    return rules


def _safeguarding_rules() -> set[tuple[str, str, str]]:
    """Safeguarding concerns (contexts/safeguarding).

    A child and a guardian may *raise* a concern; which learner a guardian may name, and that a
    guardian lists only concerns they raised, are ownership rules the service settles against the
    token subject. Only ``safeguarding_lead`` triages (reads the queue, free text, notes, audit).
    No teacher, mentor, operator or other staff role is listed: they are denied by default.
    """
    return {
        ("student", "raise", "safeguarding.concern"),
        ("guardian", "raise", "safeguarding.concern"),
        ("guardian", "read", "safeguarding.own_concern"),
        ("safeguarding_lead", "triage", "safeguarding.concern"),
    }


def _curriculum_rules() -> set[tuple[str, str, str]]:
    res = "curriculum.lesson"
    rules: set[tuple[str, str, str]] = {(r, "read", res) for r in _CURRICULUM_ROLES}
    rules.add(("subject_author", "author", res))  # create/submit their own drafts
    rules |= {(r, "review", res) for r in _REVIEWER_ROLES}
    rules.add(("curriculum_architect", "publish", res))
    rules.add(("curriculum_architect", "rollback", res))
    return rules


def _identity_rules() -> set[tuple[str, str, str]]:
    """Guardian self-service over their own family (ownership is re-checked in the service).

    The PDP answers only "may a guardian manage learners at all"; *which* learners is an ownership
    question the identity service settles against the token subject, because a policy table keyed on
    roles cannot express "their own". Operators get read access to the audit trail for safeguarding
    and nothing else — no operator route can grant consent or reset a child's PIN on a guardian's
    behalf, which keeps consent something only the responsible adult can give.
    """
    return {
        ("guardian", "read", "identity.self"),
        ("guardian", "manage", "identity.learner"),
        ("guardian", "manage", "identity.consent"),
        ("guardian", "read", "identity.audit"),
        ("system", "read", "identity.audit"),
    }


def _learning_rules() -> set[tuple[str, str, str]]:
    return {
        ("student", "operate", "learning.session"),
        ("student", "read", "learning.knowledge"),
        ("mentor", "read", "learning.knowledge"),
        ("mentor", "read", "learning.session"),
    }


def _school_rules() -> set[tuple[str, str, str]]:
    """Organization / teacher pilot minimum (contexts/school).

    The PDP answers only "may a teacher manage classes at all". *Which* classes and learners is an
    ownership + consent question the school service settles per request: the teacher's own
    organization and classes, and only learners whose guardian currently shares progress. Operators
    create organizations and teacher accounts and nothing else — no operator rule reads a learner's
    progress. A guardian may enrol their own learner (ownership re-checked against identity).
    """
    return {
        ("system", "manage", "school.organization"),
        ("teacher", "read", "school.self"),
        ("teacher", "manage", "school.class"),
        ("teacher", "manage", "school.assignment"),
        ("teacher", "read", "school.learner_progress"),
        ("guardian", "manage", "school.enrolment"),
    }


# Policy table: (role, action, resource) -> allow. Everything not listed is DENIED (fail closed).
# Note: the Curriculum Studio *workflow* rules (correct stage role, no self-approval) are also
# enforced in the domain service — the PDP is the coarse authZ gate, the domain is defence in depth.
_ALLOW: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("system", "read", "skeleton.protected"),
        ("system", "write", "sync.batch"),
        ("system", "operate", "ops.control"),  # kill switch + ops controls (operator only)
        ("system", "read", "ops.status"),  # ops health/analytics summary (operator/monitoring)
        ("mentor", "read", "ops.status"),  # mentors may read the (pseudonymous) ops summary
        ("guardian", "read", "guardian.self"),  # a guardian may read its own portal (linked kids)
        *_curriculum_rules(),
        *_learning_rules(),
        *_identity_rules(),
        *_school_rules(),
        *_staff_rules(),
        *_safeguarding_rules(),
    }
)


def authorize(role: str, action: str, resource: str) -> Decision:
    if (role, action, resource) in _ALLOW:
        return Decision(True, "explicit-allow")
    # Deny by default (docs/12 §1) — absence of an allow is a deny.
    return Decision(False, "deny-by-default")
