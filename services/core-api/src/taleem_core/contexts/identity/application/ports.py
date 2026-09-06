"""Ports the identity use cases depend on (structural protocols — no adapter imports).

Two properties are encoded here rather than left to the adapter:

- The consent and audit stores expose **append and read only**. There is no ``update`` or ``delete``
  on either protocol, so an implementation that offered one would still be unreachable from the
  service. Immutability is enforced by the shape of the port, not by a convention.
- Lookups that an attacker could use to enumerate accounts (by email, by family code) return
  ``None`` rather than raising, so the service can answer every failed sign-in identically.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol

from ..domain.accounts import GuardianAccount, LearnerAccount
from ..domain.audit import AuditEvent
from ..domain.consent import ConsentRecord


class GuardianRepository(Protocol):
    def add(self, account: GuardianAccount) -> None: ...
    def get(self, guardian_ref: str) -> GuardianAccount | None: ...
    def by_email(self, email: str) -> GuardianAccount | None: ...
    def by_family_code(self, family_code: str) -> GuardianAccount | None: ...
    def save(self, account: GuardianAccount) -> None: ...


class LearnerRepository(Protocol):
    def add(self, account: LearnerAccount) -> None: ...
    def get(self, student_ref: str) -> LearnerAccount | None: ...
    def for_guardian(self, guardian_ref: str) -> list[LearnerAccount]: ...
    def save(self, account: LearnerAccount) -> None: ...


class ConsentRepository(Protocol):
    """Append-only. Deliberately has no update or delete."""

    def append(self, record: ConsentRecord) -> None: ...
    def history(self, student_ref: str) -> list[ConsentRecord]: ...
    def history_for_guardian(self, guardian_ref: str) -> list[ConsentRecord]: ...


class AuditRepository(Protocol):
    """Append-only. Deliberately has no update or delete."""

    def append(self, event: AuditEvent) -> None: ...
    def for_subject(self, subject_ref: str, *, limit: int = 100) -> list[AuditEvent]: ...
    def for_guardian_family(
        self, guardian_ref: str, student_refs: list[str], *, limit: int = 100
    ) -> list[AuditEvent]: ...


class IdentityUnitOfWork(Protocol):
    """One transactional scope over all four stores.

    The four stores are read-only *properties* rather than plain attributes so that a concrete unit
    of work may expose its own repository types: a mutable protocol attribute is invariant, which
    would force every adapter to name the protocol type instead of its own implementation.
    """

    @property
    def guardians(self) -> GuardianRepository: ...
    @property
    def learners(self) -> LearnerRepository: ...
    @property
    def consents(self) -> ConsentRepository: ...
    @property
    def audit(self) -> AuditRepository: ...

    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def __enter__(self) -> IdentityUnitOfWork: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
