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


def _curriculum_rules() -> set[tuple[str, str, str]]:
    res = "curriculum.lesson"
    rules: set[tuple[str, str, str]] = {(r, "read", res) for r in _CURRICULUM_ROLES}
    rules.add(("subject_author", "author", res))  # create/submit their own drafts
    rules |= {(r, "review", res) for r in _REVIEWER_ROLES}
    rules.add(("curriculum_architect", "publish", res))
    rules.add(("curriculum_architect", "rollback", res))
    return rules


def _learning_rules() -> set[tuple[str, str, str]]:
    return {
        ("student", "operate", "learning.session"),
        ("student", "read", "learning.knowledge"),
        ("mentor", "read", "learning.knowledge"),
        ("mentor", "read", "learning.session"),
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
        *_curriculum_rules(),
        *_learning_rules(),
    }
)


def authorize(role: str, action: str, resource: str) -> Decision:
    if (role, action, resource) in _ALLOW:
        return Decision(True, "explicit-allow")
    # Deny by default (docs/12 §1) — absence of an allow is a deny.
    return Decision(False, "deny-by-default")
