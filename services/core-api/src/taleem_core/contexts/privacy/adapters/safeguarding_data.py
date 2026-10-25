"""Safeguarding store: concerns about (or raised by) a learner, their triage notes, the immutable
evidence snapshots (``concern_evidence``, alembic 0018), and their audit.

**Export** is requested by the guardian, so it follows the safeguarding visibility rule rather than
"everything about the learner": it contains the concerns *that guardian raised* about the learner
(their own words and a coarse status). Concerns the learner or a teacher raised are **withheld** —
the concern may be about the guardian — and so are triage notes, the audit trail and **every
evidence snapshot** (the flagged homework text exists only behind system or teacher concerns, so
exporting it would reveal that a child's words were flagged). The withheld
notice is the same text whether or not any such record exists, so the export never reveals that a
child spoke up (doc 52 §4, "guardian data-export is safeguarding-checked"). Whether a child may
obtain their own safeguarding records some other way is an M-Gov question.

**Erasure** follows the retained set's explicit ``safeguarding_concerns`` entry (PENDING M-Gov):

- ``retain_pseudonymised`` (default): every row is kept, and every occurrence of the learner's ref —
  ``subject_ref``, ``raised_by_ref``, an audit ``actor_ref``, or the ref as a word inside free text
  or a note — is replaced by the one-way tombstone ref. Nothing names the learner afterwards.
  Evidence snapshots are **retained with their concern**, consistent with the concern's own free
  text: the row carries no learner ref (it is keyed by the concern, which is re-keyed). Should the
  flagged text itself contain the ref as a word, that word is replaced and ``text_sha256`` is
  recomputed for the stored text — the one UPDATE the immutability trigger admits, inside this
  erasure's transaction (``SET LOCAL taleem.privacy_erasure = 'on'``).
- ``erase``: the concerns, their evidence snapshots, their notes, and their audit rows are deleted
  (evidence first and explicitly: it has no cascade, and its trigger admits the DELETE only inside
  this erasure's transaction).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from ...safeguarding.adapters.persistence.models import (
    ConcernAuditRow,
    ConcernEvidenceRow,
    ConcernNoteRow,
    ConcernRow,
)
from ...safeguarding.domain.model import text_digest
from ..domain.policy import RetainedSet
from ._rows import affected, mentions, text_contains

WITHHELD_NOTICE = (
    "Safeguarding records raised by the learner, by a teacher or by the homework screen, and every "
    "triage note, evidence snapshot and audit entry, are withheld from a guardian's export "
    "(safeguarding exemption; PENDING M-Gov)."
)
# The flag the 0018 immutability trigger (and the 0009 evidence trigger) admits, set only inside
# an erasure transaction.
ERASURE_GUC = "taleem.privacy_erasure"

_GUARDIAN_STATUS = {
    "open": "received",
    "acknowledged": "in_review",
    "escalated": "in_review",
    "resolved": "closed",
}


def _replace(text: str | None, ref: str, replacement: str) -> str | None:
    if text is None:
        return None
    return re.sub(rf"(?<![A-Za-z0-9_\-]){re.escape(ref)}(?![A-Za-z0-9_\-])", replacement, text)


def flagged_submission_ids(session_factory: sessionmaker[Session]) -> Callable[[], set[str]]:
    """Ids of homework submissions any safeguarding concern references (for export withholding)."""

    def read() -> set[str]:
        with session_factory() as s:
            return {
                ref
                for ref in s.scalars(
                    select(ConcernRow.context_submission_id).where(
                        ConcernRow.context_submission_id.is_not(None)
                    )
                ).all()
                if ref
            }

    return read


class SafeguardingLearnerData:
    name = "safeguarding"

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def covers(self) -> tuple[str, ...]:
        return (
            "safeguarding.concern",
            "safeguarding.concern_note",
            "safeguarding.concern_evidence",
            "safeguarding.concern_audit",
        )

    # ---------------------------------------------------------------------------------- export

    def export(self, student_ref: str) -> dict[str, Any]:
        with self._sf() as s:
            rows = s.scalars(
                select(ConcernRow)
                .where(ConcernRow.subject_ref == student_ref)
                .where(ConcernRow.raised_by_role == "guardian")
                .order_by(ConcernRow.created_at, ConcernRow.concern_id)
            ).all()
            return {
                "concerns_raised_by_guardian": [
                    {
                        "concern_id": r.concern_id,
                        "category": r.category,
                        "text": r.free_text,
                        "raised_at": r.created_at,
                        "status": _GUARDIAN_STATUS.get(r.status, "received"),
                    }
                    for r in rows
                ],
                "withheld": [WITHHELD_NOTICE],
            }

    # ---------------------------------------------------------------------------------- erasure

    def _concern_ids(self, s: Session, ref: str) -> list[str]:
        return list(
            s.scalars(
                select(ConcernRow.concern_id).where(
                    or_(ConcernRow.subject_ref == ref, ConcernRow.raised_by_ref == ref)
                )
            )
        )

    @staticmethod
    def _admit_erasure(s: Session) -> None:
        if s.get_bind().dialect.name == "postgresql":
            s.execute(text(f"SET LOCAL {ERASURE_GUC} = 'on'"))

    def erase(self, student_ref: str, retained: RetainedSet) -> dict[str, int]:
        if retained.retain_safeguarding:
            return self._pseudonymise(student_ref, retained.tombstone_ref(student_ref))
        with self._sf() as s, s.begin():
            self._admit_erasure(s)
            ids = self._concern_ids(s, student_ref)
            evidence = s.execute(
                delete(ConcernEvidenceRow).where(ConcernEvidenceRow.concern_id.in_(ids))
            )
            audit = s.execute(
                delete(ConcernAuditRow).where(
                    or_(
                        ConcernAuditRow.concern_id.in_(ids),
                        ConcernAuditRow.actor_ref == student_ref,
                    )
                )
            )
            notes = s.execute(delete(ConcernNoteRow).where(ConcernNoteRow.concern_id.in_(ids)))
            concerns = s.execute(delete(ConcernRow).where(ConcernRow.concern_id.in_(ids)))
        return {
            "concern": affected(concerns),
            "concern_note": affected(notes),
            "concern_evidence": affected(evidence),
            "concern_audit": affected(audit),
        }

    def _pseudonymise(self, ref: str, tomb: str) -> dict[str, int]:
        with self._sf() as s, s.begin():
            self._admit_erasure(s)
            subject = s.execute(
                update(ConcernRow)
                .where(ConcernRow.subject_ref == ref)
                .values(subject_ref=tomb)
                .execution_options(synchronize_session=False)
            )
            raiser = s.execute(
                update(ConcernRow)
                .where(ConcernRow.raised_by_ref == ref)
                .values(raised_by_ref=tomb)
                .execution_options(synchronize_session=False)
            )
            actor = s.execute(
                update(ConcernAuditRow)
                .where(ConcernAuditRow.actor_ref == ref)
                .values(actor_ref=tomb)
                .execution_options(synchronize_session=False)
            )
            texts = 0
            for concern in s.scalars(
                select(ConcernRow).where(text_contains(ConcernRow.free_text, ref))
            ):
                if mentions(concern.free_text, ref):
                    concern.free_text = _replace(concern.free_text, ref, tomb)
                    texts += 1
            notes = 0
            for note in s.scalars(
                select(ConcernNoteRow).where(text_contains(ConcernNoteRow.body, ref))
            ):
                if mentions(note.body, ref):
                    note.body = _replace(note.body, ref, tomb) or ""
                    notes += 1
            evidence = 0
            for snap in s.scalars(
                select(ConcernEvidenceRow).where(text_contains(ConcernEvidenceRow.text, ref))
            ):
                if mentions(snap.text, ref):
                    snap.text = _replace(snap.text, ref, tomb) or ""
                    snap.text_sha256 = text_digest(snap.text)
                    evidence += 1
        return {
            "concern": affected(subject) + affected(raiser) + texts,
            "concern_note": notes,
            "concern_evidence": evidence,
            "concern_audit": affected(actor),
        }

    def remaining(self, student_ref: str) -> dict[str, int]:
        with self._sf() as s:
            concerns = s.scalar(
                select(func.count())
                .select_from(ConcernRow)
                .where(
                    or_(
                        ConcernRow.subject_ref == student_ref,
                        ConcernRow.raised_by_ref == student_ref,
                    )
                )
            )
            text_hits = sum(
                1
                for t in s.scalars(
                    select(ConcernRow.free_text).where(
                        text_contains(ConcernRow.free_text, student_ref)
                    )
                )
                if mentions(t, student_ref)
            )
            note_hits = sum(
                1
                for b in s.scalars(
                    select(ConcernNoteRow.body).where(
                        text_contains(ConcernNoteRow.body, student_ref)
                    )
                )
                if mentions(b, student_ref)
            )
            evidence_hits = sum(
                1
                for t in s.scalars(
                    select(ConcernEvidenceRow.text).where(
                        text_contains(ConcernEvidenceRow.text, student_ref)
                    )
                )
                if mentions(t, student_ref)
            )
            audit = s.scalar(
                select(func.count())
                .select_from(ConcernAuditRow)
                .where(ConcernAuditRow.actor_ref == student_ref)
            )
            return {
                "concern": int(concerns or 0) + text_hits,
                "concern_note": note_hits,
                "concern_evidence": evidence_hits,
                "concern_audit": int(audit or 0),
            }

    def count_older_than(self, data_class: str, cutoff: float) -> int | None:
        return None  # no retention class is defined for safeguarding records yet (M-Gov)

    def blockers(self) -> list[str]:
        return []
