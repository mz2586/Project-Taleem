"""Guardian→children links read from the identity context — the production source of truth.

The integration seam between the two bounded contexts, in the same pattern as
``learning/adapters/curriculum_read_model.py``: the guardian application knows only the
``GuardianLinks`` port, and this adapter is the one place that knows the identity context exists. It
calls the identity service's public read ``portal_links``, which applies ownership and live consent
on every call, so a withdrawal takes the child out of the portal on the next request.
"""

from __future__ import annotations

import logging
from typing import Protocol

from ..application.directory import GuardianDirectory, GuardianProfile
from ..application.links import GuardianLinks, LayeredLinks

logger = logging.getLogger("taleem.guardian")


class IdentityPortalReads(Protocol):
    def portal_links(self, guardian_ref: str) -> tuple[str, list[str]] | None: ...


class IdentityGuardianLinks:
    """Implements ``GuardianLinks`` over the identity service."""

    def __init__(self, identity: IdentityPortalReads) -> None:
        self._identity = identity

    def profile(self, guardian_ref: str) -> GuardianProfile | None:
        found = self._identity.portal_links(guardian_ref)
        if found is None:
            return None
        display_name, refs = found
        return GuardianProfile(guardian_ref, display_name, tuple(refs))

    def children(self, guardian_ref: str) -> tuple[str, ...]:
        found = self.profile(guardian_ref)
        return found.children if found is not None else ()

    def is_linked(self, guardian_ref: str, student_ref: str) -> bool:
        return student_ref in self.children(guardian_ref)


def build_guardian_links(
    identity: IdentityPortalReads, *, seed_csv: str, production: bool
) -> GuardianLinks:
    """Identity everywhere; the static seed only outside production, never over a real account."""
    primary = IdentityGuardianLinks(identity)
    if not seed_csv.strip():
        return primary
    if production:
        logger.warning("TALEEM_GUARDIAN_LINKS is set in production and is ignored")
        return primary
    return LayeredLinks(primary, GuardianDirectory.from_csv(seed_csv))
