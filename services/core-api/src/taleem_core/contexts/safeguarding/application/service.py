"""Safeguarding application service: raise a concern, and triage it.

Visibility rules (each is enforced here, against the token subject, and pinned by a test):

1. **A child** raises a concern about themselves and gets back a receipt — no id, no list, no
   history. A family device is often shared, so nothing a child raised is ever shown back on it.
2. **A guardian** raises a concern only about a learner identity records as theirs (another family's
   learner is a 404), and lists **only the concerns they raised themselves** — matched on
   ``raised_by_ref`` and ``raised_by_role``, never on the learner. A concern a child raised is
   therefore invisible to every guardian, *including* a guardian the concern may be about, without
   the system having to know who the concern is about. The guardian sees a coarse status
   (received / being looked at / closed): never triage notes, escalation, or outcome.
3. **A safeguarding lead** (``safeguarding_lead``, an operator-provisioned staff account) is the
   only role that reads the queue, a concern's free text, notes, or audit. Opening a concern's
   detail is itself audited (``concern.viewed``).
4. **Nobody else** — teachers, mentors, other staff roles, operators — has any route here (the PDP
   denies them). No teacher surface ever includes a concern.

Every action is audited in the same transaction as the change, naming the actor's token subject.
Nothing in this service contacts anyone: an escalation records "external referral needed" for a
human to act on under a policy that does not exist yet (FD-04). Logs and metrics carry priority and
role only — never a ref, a category chosen by a child, or a word of free text.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ....platform import observability
from ....platform.errors import Problem, forbidden, not_found, validation_error
from ..domain.model import (
    OPEN_STATUSES,
    Action,
    AuditEntry,
    Concern,
    InvalidConcernError,
    Note,
    Priority,
    RaisedBy,
    SlaPolicy,
    Status,
    new_note,
)
from .ports import LearnerDirectory, SafeguardingUnitOfWork

LEAD_ROLE = "safeguarding_lead"
QUEUE_LIMIT = 500
GUARDIAN_LIST_LIMIT = 100

# What a guardian is told about the state of a concern they raised (rule 2).
_GUARDIAN_STATUS: dict[Status, str] = {
    Status.OPEN: "received",
    Status.ACKNOWLEDGED: "in_review",
    Status.ESCALATED: "in_review",
    Status.RESOLVED: "closed",
}

# What the child is told. Honest: a person will read it; no response time is promised (FD-06).
CHILD_RECEIPT_NOTICE = (
    "A trained grown-up at Taleem will read this. If you are in danger right now, tell a "
    "grown-up near you that you trust straight away."
)
NOBODY_CONTACTED = "Recorded only. This software contacts nobody; a person must act (FD-04)."


def _invalid(exc: InvalidConcernError) -> Problem:
    if exc.code in ("CONCERN_CLOSED", "CONCERN_NOT_ESCALATED"):
        return Problem(409, exc.code, "Concern cannot change this way", str(exc))
    entry = {"code": exc.code, "message": str(exc)}
    if exc.field:
        entry["field"] = exc.field
    return validation_error(str(exc), errors=[entry])


def _note_view(note: Note) -> dict[str, Any]:
    return {
        "note_id": note.note_id,
        "author_ref": note.author_ref,
        "body": note.body,
        "created_at": note.created_at,
    }


def _audit_view(entry: AuditEntry) -> dict[str, Any]:
    return {
        "action": entry.action,
        "actor_ref": entry.actor_ref,
        "actor_role": entry.actor_role,
        "at": entry.at,
        "detail": dict(entry.detail),
    }


def guardian_view(concern: Concern) -> dict[str, Any]:
    return {
        "concern_id": concern.concern_id,
        "student_ref": concern.subject_ref,
        "category": concern.category.value,
        "text": concern.free_text,
        "raised_at": concern.created_at,
        "status": _GUARDIAN_STATUS[concern.status],
    }


class SafeguardingService:
    def __init__(
        self,
        uow_factory: Callable[[], SafeguardingUnitOfWork],
        learners: LearnerDirectory,
        clock: Callable[[], float],
        sla: SlaPolicy,
        *,
        require_enrolled: bool,
    ) -> None:
        self._uow = uow_factory
        self._learners = learners
        self._now = clock
        self._sla = sla
        self._require_enrolled = require_enrolled

    @property
    def sla(self) -> SlaPolicy:
        return self._sla

    # ----------------------------------------------------------------------------- raising

    def raise_by_student(
        self,
        *,
        student_ref: str,
        category: str,
        text: str | None,
        screen: str | None,
        lesson_id: str | None,
    ) -> dict[str, Any]:
        """A child's concern about themselves. Deliberately NOT behind the learner consent gate or
        the kill switch: this is a safety channel, and it must stay open when learning is closed."""
        if self._require_enrolled and self._learners.guardian_of(student_ref) is None:
            # Production: every learner token comes from identity, so an unknown subject is forged.
            raise forbidden("this learner is not known")
        concern = self._create(
            subject_ref=student_ref,
            raised_by_ref=student_ref,
            role=RaisedBy.STUDENT,
            category=category,
            text=text,
            screen=screen,
            lesson_id=lesson_id,
        )
        # A receipt only: no id and no way to list it later (rule 1).
        return {"received": True, "raised_at": concern.created_at, "notice": CHILD_RECEIPT_NOTICE}

    def raise_by_guardian(
        self,
        *,
        guardian_ref: str,
        student_ref: str,
        category: str,
        text: str | None,
        screen: str | None,
        lesson_id: str | None,
    ) -> dict[str, Any]:
        if not student_ref or self._learners.guardian_of(student_ref) != guardian_ref:
            raise not_found("learner not found")  # another family's learner: no disclosure
        concern = self._create(
            subject_ref=student_ref,
            raised_by_ref=guardian_ref,
            role=RaisedBy.GUARDIAN,
            category=category,
            text=text,
            screen=screen,
            lesson_id=lesson_id,
        )
        return guardian_view(concern)

    def _create(
        self,
        *,
        subject_ref: str,
        raised_by_ref: str,
        role: RaisedBy,
        category: str,
        text: str | None,
        screen: str | None,
        lesson_id: str | None,
    ) -> Concern:
        now = self._now()
        try:
            concern = Concern.raise_new(
                subject_ref=subject_ref,
                raised_by_ref=raised_by_ref,
                raised_by_role=role,
                category=category,
                free_text=text,
                screen=screen,
                lesson_id=lesson_id,
                now=now,
            )
        except InvalidConcernError as exc:
            raise _invalid(exc) from exc
        with self._uow() as uow:
            uow.concerns.add(concern)
            uow.audit.append(
                AuditEntry.record(
                    concern_id=concern.concern_id,
                    action=Action.RAISED,
                    actor_ref=raised_by_ref,
                    actor_role=role.value,
                    at=now,
                    category=concern.category.value,
                    priority=concern.priority.value,
                )
            )
            uow.commit()
        observability.record_event(
            "taleem_safeguarding_concerns_raised_total",
            priority=concern.priority.value,
            raised_by=role.value,
        )
        observability.log_event(
            "safeguarding_concern_raised", priority=concern.priority.value, raised_by=role.value
        )
        return concern

    def guardian_concerns(self, guardian_ref: str) -> list[dict[str, Any]]:
        with self._uow() as uow:
            raised = uow.concerns.raised_by(guardian_ref, GUARDIAN_LIST_LIMIT)
        return [guardian_view(c) for c in raised if c.raised_by_role is RaisedBy.GUARDIAN]

    # ------------------------------------------------------------------------------ triage

    def _summary(self, concern: Concern, now: float) -> dict[str, Any]:
        return {
            "concern_id": concern.concern_id,
            "subject_ref": concern.subject_ref,
            "raised_by_role": concern.raised_by_role.value,
            "category": concern.category.value,
            "priority": concern.priority.value,
            "status": concern.status.value,
            "created_at": concern.created_at,
            "age_seconds": round(concern.age(now), 3),
            "overdue": concern.overdue(self._sla, now),
            "has_text": concern.free_text is not None,
            "context": {"screen": concern.context_screen, "lesson_id": concern.context_lesson_id},
        }

    def queue(self, *, include_resolved: bool = False) -> dict[str, Any]:
        now = self._now()
        statuses = OPEN_STATUSES | {Status.RESOLVED} if include_resolved else OPEN_STATUSES
        with self._uow() as uow:
            concerns = uow.concerns.queue(frozenset(statuses), QUEUE_LIMIT)
        return {
            "generated_at": now,
            "sla": self._sla.describe(),
            "concerns": [self._summary(c, now) for c in concerns],
        }

    def _detail(self, uow: SafeguardingUnitOfWork, concern: Concern, now: float) -> dict[str, Any]:
        view = self._summary(concern, now)
        view.update(
            {
                "text": concern.free_text,
                "raised_by_ref": concern.raised_by_ref,
                "outcome": concern.outcome.value if concern.outcome else None,
                "acknowledged_at": concern.acknowledged_at,
                "acknowledged_by": concern.acknowledged_by,
                "escalated_at": concern.escalated_at,
                "escalated_by": concern.escalated_by,
                "resolved_at": concern.resolved_at,
                "resolved_by": concern.resolved_by,
                "external_referral_needed": concern.escalated_at is not None,
                # Doc 52 §4: a child's concern may be about their own household. The guardian was
                # not told and cannot see it; do not contact them until they are ruled out.
                "guardian_informed": False,
                "household_caution": concern.raised_by_role is RaisedBy.STUDENT,
                "notes": [_note_view(n) for n in uow.notes.for_concern(concern.concern_id)],
                "audit": [_audit_view(a) for a in uow.audit.for_concern(concern.concern_id)],
                "contacted": [],
                "contact_notice": NOBODY_CONTACTED,
            }
        )
        return view

    def _load(self, uow: SafeguardingUnitOfWork, concern_id: str) -> Concern:
        concern = uow.concerns.get(concern_id)
        if concern is None:
            raise not_found("concern not found")
        return concern

    def _record(
        self,
        uow: SafeguardingUnitOfWork,
        concern: Concern,
        action: Action,
        actor_ref: str,
        now: float,
        **detail: str,
    ) -> None:
        uow.audit.append(
            AuditEntry.record(
                concern_id=concern.concern_id,
                action=action,
                actor_ref=actor_ref,
                actor_role=LEAD_ROLE,
                at=now,
                **detail,
            )
        )

    def detail(self, *, actor_ref: str, concern_id: str) -> dict[str, Any]:
        now = self._now()
        with self._uow() as uow:
            concern = self._load(uow, concern_id)
            self._record(uow, concern, Action.VIEWED, actor_ref, now)
            uow.commit()
            return self._detail(uow, concern, now)

    def acknowledge(self, *, actor_ref: str, concern_id: str) -> dict[str, Any]:
        now = self._now()
        with self._uow() as uow:
            concern = self._load(uow, concern_id)
            before = concern.status.value
            try:
                changed = concern.acknowledge(actor_ref=actor_ref, now=now)
            except InvalidConcernError as exc:
                raise _invalid(exc) from exc
            if changed:
                uow.concerns.save(concern)
                self._record(uow, concern, Action.ACKNOWLEDGED, actor_ref, now, **{"from": before})
                uow.commit()
            return self._detail(uow, concern, now)

    def add_note(self, *, actor_ref: str, concern_id: str, body: str) -> dict[str, Any]:
        now = self._now()
        with self._uow() as uow:
            concern = self._load(uow, concern_id)
            try:
                note = new_note(concern_id=concern_id, author_ref=actor_ref, body=body, now=now)
            except InvalidConcernError as exc:
                raise _invalid(exc) from exc
            uow.notes.add(note)
            self._record(uow, concern, Action.NOTE_ADDED, actor_ref, now, note_id=note.note_id)
            uow.commit()
            return self._detail(uow, concern, now)

    def escalate(self, *, actor_ref: str, concern_id: str, reason: str) -> dict[str, Any]:
        """Record "external referral needed". The reason is a required note. Contacts nobody."""
        now = self._now()
        with self._uow() as uow:
            concern = self._load(uow, concern_id)
            before = concern.status.value
            try:
                note = new_note(concern_id=concern_id, author_ref=actor_ref, body=reason, now=now)
                changed = concern.escalate(actor_ref=actor_ref, now=now)
            except InvalidConcernError as exc:
                raise _invalid(exc) from exc
            uow.notes.add(note)
            if changed:
                uow.concerns.save(concern)
            self._record(
                uow,
                concern,
                Action.ESCALATED,
                actor_ref,
                now,
                note_id=note.note_id,
                **{"from": before, "to": concern.status.value},
            )
            uow.commit()
            return self._detail(uow, concern, now)

    def resolve(
        self, *, actor_ref: str, concern_id: str, outcome: str, note: str | None
    ) -> dict[str, Any]:
        now = self._now()
        with self._uow() as uow:
            concern = self._load(uow, concern_id)
            before = concern.status.value
            try:
                written = (
                    new_note(concern_id=concern_id, author_ref=actor_ref, body=note, now=now)
                    if note and note.strip()
                    else None
                )
                concern.resolve(actor_ref=actor_ref, outcome=outcome, now=now)
            except InvalidConcernError as exc:
                raise _invalid(exc) from exc
            if written is not None:
                uow.notes.add(written)
            uow.concerns.save(concern)
            self._record(
                uow,
                concern,
                Action.RESOLVED,
                actor_ref,
                now,
                outcome=concern.outcome.value if concern.outcome else "",
                **{"from": before},
            )
            uow.commit()
            return self._detail(uow, concern, now)

    # ----------------------------------------------------------------------------- metrics

    def gauges(self) -> dict[str, dict[str, float]]:
        """Per-priority counts for the scrape: unacknowledged, and overdue when an SLA is set.

        Read from the database, so every instance reports the same numbers (alerts take ``max``).
        """
        now = self._now()
        with self._uow() as uow:
            open_by_priority = uow.concerns.open_counts()
        unacknowledged: dict[str, float] = {}
        overdue: dict[str, float] = {}
        for priority in Priority:
            created = open_by_priority.get(priority, [])
            unacknowledged[priority.value] = float(len(created))
            threshold = self._sla.acknowledge_within(priority)
            overdue[priority.value] = (
                float(sum(1 for c in created if now - c > threshold))
                if threshold is not None
                else 0.0
            )
        return {"unacknowledged": unacknowledged, "overdue": overdue}
