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


# Walking-skeleton policy table: (role, action, resource) -> allow.
# Deliberately minimal and non-child. Everything not listed is DENIED.
_ALLOW: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("system", "read", "skeleton.protected"),
        ("system", "write", "sync.batch"),
    }
)


def authorize(role: str, action: str, resource: str) -> Decision:
    if (role, action, resource) in _ALLOW:
        return Decision(True, "explicit-allow")
    # Deny by default (docs/12 §1) — absence of an allow is a deny.
    return Decision(False, "deny-by-default")
