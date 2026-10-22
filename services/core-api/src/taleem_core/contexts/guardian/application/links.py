"""The Guardian Portal's port onto "which children may this guardian see".

The portal owns no account or consent state. It asks this port, and the composition root decides
what answers: in every environment the identity context (guardian accounts, enrolled learners, and
their live consent — see ``adapters/identity_links.py``); outside production the static
``TALEEM_GUARDIAN_LINKS`` seed may be layered underneath for dev/demo data. Production never reads
the seed, because a config string cannot carry consent.
"""

from __future__ import annotations

from typing import Protocol

from .directory import GuardianProfile


class GuardianLinks(Protocol):
    """The authority for the portal's IDOR guard. Implementations must not cache consent."""

    def profile(self, guardian_ref: str) -> GuardianProfile | None: ...

    def children(self, guardian_ref: str) -> tuple[str, ...]: ...

    def is_linked(self, guardian_ref: str, student_ref: str) -> bool: ...


class LayeredLinks:
    """A primary source with a dev/demo seed underneath (never constructed in production).

    A guardian known to the primary source is answered by it alone — the seed can add demo families
    but can never add a child to a real account.
    """

    def __init__(self, primary: GuardianLinks, seed: GuardianLinks) -> None:
        self._primary = primary
        self._seed = seed

    def profile(self, guardian_ref: str) -> GuardianProfile | None:
        found = self._primary.profile(guardian_ref)
        return found if found is not None else self._seed.profile(guardian_ref)

    def children(self, guardian_ref: str) -> tuple[str, ...]:
        found = self.profile(guardian_ref)
        return found.children if found is not None else ()

    def is_linked(self, guardian_ref: str, student_ref: str) -> bool:
        return student_ref in self.children(guardian_ref)
