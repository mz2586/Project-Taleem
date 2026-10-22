"""Privacy application service: guardian export, two-step erasure, retention dry-run.

Authorization model: a guardian may act only on a learner the identity context records as theirs.
Anyone else — another guardian, an unknown ref, an already-erased learner — gets the same 404, so a
response never confirms that a ref names a real child elsewhere (IDOR guard, as in identity).

Erasure order: every non-identity store first, identity last. The learner account (and so the
guardian's ability to name the child) disappears only after the other stores are clean, so a
failure part-way leaves a retryable request rather than unreachable orphans; the identity deletion
and the tombstone commit in one transaction. A verification sweep then re-scans every store.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from ....platform import observability
from ....platform.errors import Problem, not_found
from ..domain import erasure
from ..domain.policy import RETENTION_CLASSES, PrivacyConfig
from .ports import IdentityDataPort, LearnerDataPort, Tombstone

EXPORT_FORMAT = "taleem.learner-export/1"


def _not_configured() -> Problem:
    return Problem(
        503,
        "ERASURE_NOT_CONFIGURED",
        "Erasure is not configured",
        "TALEEM_PRIVACY_CONFIRMATION_KEY is not set; erasure stays disabled in production",
    )


def _blocked(reasons: list[str]) -> Problem:
    return Problem(503, "ERASURE_BLOCKED", "Erasure cannot run safely", "; ".join(reasons))


class ErasureIncompleteError(RuntimeError):
    """The verification sweep found rows still referencing the erased learner."""


class PrivacyService:
    def __init__(
        self,
        identity: IdentityDataPort,
        stores: Sequence[LearnerDataPort],
        config: PrivacyConfig,
        clock: Callable[[], float],
    ) -> None:
        self._identity = identity
        self._stores = list(stores)
        self._config = config
        self._now = clock

    @property
    def ports(self) -> list[LearnerDataPort]:
        return [*self._stores, self._identity]

    def covered_tables(self) -> set[str]:
        return {t for p in self.ports for t in p.covers()}

    # ---------------------------------------------------------------------------------- guards

    def _require_guardian_of(self, guardian_ref: str, student_ref: str) -> None:
        if not student_ref or self._identity.guardian_of(student_ref) != guardian_ref:
            raise not_found("learner not found")

    # ---------------------------------------------------------------------------------- export

    def export(self, *, guardian_ref: str, student_ref: str) -> dict[str, Any]:
        self._require_guardian_of(guardian_ref, student_ref)
        sections = {p.name: p.export(student_ref) for p in self.ports}
        observability.record_event("taleem_privacy_exports_total")
        observability.log_event("learner_data_exported", subject_ref=student_ref)
        return {
            "format": EXPORT_FORMAT,
            "generated_at": self._now(),
            "student_ref": student_ref,
            "requested_by": guardian_ref,
            "stores": sorted(self.covered_tables()),
            "sections": sections,
            "notice": (
                "Everything Taleem holds about this pseudonymous learner, by store. Credential "
                "digests are withheld (listed under each section's `withheld`). Guardian portal "
                "views are derived on read from these records and are not stored separately."
            ),
        }

    # ---------------------------------------------------------------------------------- erasure

    def blockers(self) -> list[str]:
        return [reason for p in self.ports for reason in p.blockers()]

    def _require_erasable(self) -> None:
        if not self._config.erasure_enabled:
            raise _not_configured()
        reasons = self.blockers()
        if reasons:  # fail closed BEFORE anything is erased: never a partial erasure
            raise _blocked(reasons)

    def scope(self) -> dict[str, Any]:
        return {
            "erased": sorted(self.covered_tables()),
            "retained": self._config.retained.describe(),
            "irreversible": True,
        }

    def request_erasure(self, *, guardian_ref: str, student_ref: str) -> dict[str, Any]:
        self._require_guardian_of(guardian_ref, student_ref)
        self._require_erasable()
        req = erasure.new_request(
            student_ref, guardian_ref, self._now(), self._config.confirmation_ttl_s
        )
        observability.log_event("learner_erasure_requested", request_id=req.request_id)
        return {
            "request_id": req.request_id,
            "student_ref": student_ref,
            "confirmation_token": erasure.sign(req, self._config.confirmation_key),
            "expires_at": req.expires_at,
            "scope": self.scope(),
            "warning": "Confirming permanently erases this learner's data. It cannot be undone.",
        }

    def confirm_erasure(
        self, *, guardian_ref: str, student_ref: str, confirmation_token: str
    ) -> dict[str, Any]:
        self._require_guardian_of(guardian_ref, student_ref)
        self._require_erasable()
        try:
            req = erasure.verify(
                confirmation_token,
                self._config.confirmation_key,
                student_ref=student_ref,
                guardian_ref=guardian_ref,
                now=self._now(),
            )
        except erasure.ConfirmationError as exc:
            raise Problem(
                422, "ERASURE_CONFIRMATION_INVALID", "Erasure not confirmed", str(exc)
            ) from exc
        return self.erase(req)

    def erase(self, req: erasure.ErasureRequest) -> dict[str, Any]:
        """Erase every store, identity last; then verify nothing references the learner."""
        retained = self._config.retained
        ref = req.student_ref
        counts: dict[str, dict[str, int]] = {}
        for port in self._stores:
            counts[port.name] = port.erase(ref, retained)
        tombstone_ref = retained.tombstone_ref(ref)
        tombstone = (
            Tombstone(
                tombstone_ref=tombstone_ref,
                guardian_ref=req.guardian_ref,
                requested_at=req.requested_at,
                confirmed_at=self._now(),
                scope=tuple(sorted(self.covered_tables())),
                retained=retained.describe(),
            )
            if retained.keep_erasure_event
            else None
        )
        counts[self._identity.name] = self._identity.erase_with_tombstone(ref, retained, tombstone)
        leftovers = {
            f"{p.name}:{table}": n for p in self.ports for table, n in p.remaining(ref).items() if n
        }
        if leftovers:  # pragma: no cover - a defect, surfaced loudly rather than reported as done
            raise ErasureIncompleteError(f"erasure verification found residue: {leftovers}")
        observability.record_event("taleem_privacy_erasures_total")
        observability.log_event("learner_erased", tombstone_ref=tombstone_ref)
        return {
            "request_id": req.request_id,
            "tombstone_ref": tombstone_ref,
            "erased": counts,
            "verified": True,
            "retained": retained.describe(),
            "irreversible": True,
        }

    # ---------------------------------------------------------------------------------- retention

    def retention_dry_run(self) -> dict[str, Any]:
        now = self._now()
        rows: list[dict[str, Any]] = []
        for data_class, description in RETENTION_CLASSES.items():
            period = self._config.retention.period(data_class)
            if period is None:
                rows.append(
                    {
                        "data_class": data_class,
                        "description": description,
                        "period_seconds": None,
                        "status": "not set; purge disabled",
                        "would_purge": None,
                    }
                )
                continue
            cutoff = now - period
            found = [n for p in self.ports if (n := p.count_older_than(data_class, cutoff))]
            rows.append(
                {
                    "data_class": data_class,
                    "description": description,
                    "period_seconds": period,
                    "cutoff": cutoff,
                    "status": "dry-run only; nothing is deleted",
                    "would_purge": sum(found),
                }
            )
        return {
            "generated_at": now,
            "dry_run": True,
            "approval": self._config.retention.approval,
            "classes": rows,
        }

    def policy(self) -> dict[str, Any]:
        return {
            "retained_after_erasure": self._config.retained.describe(),
            "retention": {
                "approval": self._config.retention.approval,
                "periods_seconds": {c: self._config.retention.period(c) for c in RETENTION_CLASSES},
            },
            "erasure_enabled": self._config.erasure_enabled and not self.blockers(),
            "erasure_blockers": self.blockers(),
            "confirmation_ttl_seconds": self._config.confirmation_ttl_s,
        }
