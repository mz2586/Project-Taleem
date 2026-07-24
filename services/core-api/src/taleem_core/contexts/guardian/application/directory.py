"""Guardian → student association directory (pure-stdlib).

The *only* new state the Guardian Experience introduces: which pseudonymous learners a guardian is
linked to. Everything else is derived by consuming existing learning services — no duplicated logic.
This is the software association layer, NOT the governance/consent flow (M-Gov): a real deployment
populates links through the consent workflow; here they are seeded from config for the dev/pilot
surface. The directory is the single authority for the guardian IDOR guard: a guardian may read a
child's data only if the pair is linked here.

Seed format (``TALEEM_GUARDIAN_LINKS``): ``guardianRef:childA,childB;guardianRef2:childC`` — an
optional display name may follow the guardian ref as ``guardianRef=Name:childA,childB``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuardianProfile:
    guardian_ref: str
    display_name: str
    children: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "guardian_ref": self.guardian_ref,
            "display_name": self.display_name,
            "children": list(self.children),
            "child_count": len(self.children),
        }


class GuardianDirectory:
    """Immutable guardian→children association. The authority for the guardian link (IDOR) check."""

    def __init__(self, profiles: dict[str, GuardianProfile] | None = None) -> None:
        self._profiles: dict[str, GuardianProfile] = dict(profiles or {})

    @classmethod
    def from_csv(cls, csv: str) -> GuardianDirectory:
        profiles: dict[str, GuardianProfile] = {}
        for entry in csv.split(";"):
            entry = entry.strip()
            if not entry or ":" not in entry:
                continue
            head, kids = entry.split(":", 1)
            head = head.strip()
            name = head
            ref = head
            if "=" in head:  # guardianRef=Display Name
                ref, name = (p.strip() for p in head.split("=", 1))
            children = tuple(k.strip() for k in kids.split(",") if k.strip())
            if ref:
                profiles[ref] = GuardianProfile(ref, name or ref, children)
        return cls(profiles)

    def profile(self, guardian_ref: str) -> GuardianProfile | None:
        return self._profiles.get(guardian_ref)

    def children(self, guardian_ref: str) -> tuple[str, ...]:
        p = self._profiles.get(guardian_ref)
        return p.children if p else ()

    def is_linked(self, guardian_ref: str, student_ref: str) -> bool:
        return student_ref in self.children(guardian_ref)
