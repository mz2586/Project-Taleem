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
3. **A teacher** raises a concern only about a learner in one of their own classes, optionally
   naming the homework submission that prompted it (another school's learner, or one outside the
   teacher's classes, is a 404). Like a child, the teacher gets a receipt only: no id, no list.
   Raising never changes the submission and the child is never told.
4. **A safeguarding lead** (``safeguarding_lead``, an operator-provisioned staff account) is the
   only role that reads the queue, a concern's free text, notes, or audit. Opening a concern's
   detail is itself audited (``concern.viewed``).
5. **Nobody else** — mentors, other staff roles, operators — has any route here (the PDP denies
   them). No teacher surface ever includes a concern.
6. **The system** (the homework disclosure screen) raises a concern only from a phrase-list match
   on a submitted answer, about that answer's learner, naming the submission — at most one per
   submission. It is invisible to every guardian and teacher; only the lead sees it.

7. **The flagged work** behind a concern that names a homework submission (the child's text, the
   item prompt, the lesson title and the phrase-list entries it matches) is read only by a
   ``safeguarding_lead``, on demand, and every read is audited (``concern.context_viewed``: who,
   when, which concern and submission, never the text). It reads through the school context
   regardless of consent or the kill switch: safeguarding must be able to act.

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
from ..domain.disclosure import PhraseList, default_phrase_list, strongest_category
from ..domain.model import (
    OPEN_STATUSES,
    SYSTEM_RAISER_REF,
    Action,
    AuditEntry,
    Concern,
    ConcernEvidence,
    InvalidConcernError,
    Note,
    Priority,
    RaisedBy,
    SlaPolicy,
    Status,
    new_note,
)
from .ports import LearnerDirectory, SafeguardingUnitOfWork, SubmissionReader, TeacherRoster

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
# What a teacher is told. A receipt only; the lead decides what happens next.
TEACHER_RECEIPT_NOTICE = (
    "Your concern has been recorded for the safeguarding lead. Do not tell the child or their "
    "family that a concern was raised, and follow your school's safeguarding procedure."
)
CONTEXT_READ_NOTICE = (
    "This read was recorded in the safeguarding audit trail (who, when, which concern). "
    "'flagged' is the text exactly as it was when the concern was raised; 'current' appears only "
    "when the child's latest answer differs from it."
)
NO_SNAPSHOT_NOTICE = (
    "No snapshot was kept for this concern (it was raised before snapshots existed). The text "
    "shown is what the child last submitted, which may not be what prompted the concern."
)
_EVIDENCE_KEYS = ("text", "attempt", "submitted_at", "item_ref", "objective_code")
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
        teachers: TeacherRoster | None = None,
        phrases: PhraseList | None = None,
        submissions: SubmissionReader | None = None,
    ) -> None:
        self._uow = uow_factory
        self._submissions = submissions
        self._teachers = teachers
        self._learners = learners
        self._now = clock
        self._sla = sla
        self._require_enrolled = require_enrolled
        self._phrases = phrases if phrases is not None else default_phrase_list()

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

    def raise_by_teacher(
        self,
        *,
        teacher_ref: str,
        student_ref: str,
        category: str,
        text: str | None,
        submission_id: str | None,
        screen: str | None,
        lesson_id: str | None,
    ) -> dict[str, Any]:
        """A teacher's concern about a learner in one of their own classes (rule 3)."""
        if (
            self._teachers is None
            or not student_ref
            or not self._teachers.may_raise_about(
                teacher_ref=teacher_ref, student_ref=student_ref, submission_id=submission_id
            )
        ):
            raise not_found("learner not found")  # outside the teacher's classes: no disclosure
        concern = self._create(
            subject_ref=student_ref,
            raised_by_ref=teacher_ref,
            role=RaisedBy.TEACHER,
            category=category,
            text=text,
            screen=screen,
            lesson_id=lesson_id,
            submission_id=submission_id,
            # The answer as the teacher saw it when raising: a later resubmission cannot erase it.
            evidence=self._current(submission_id, student_ref) if submission_id else None,
        )
        return {
            "received": True,
            "raised_at": concern.created_at,
            "notice": TEACHER_RECEIPT_NOTICE,
        }

    def screen_submission(
        self,
        *,
        student_ref: str,
        submission_id: str,
        text: str,
        attempt: int | None = None,
        submitted_at: float | None = None,
        item_ref: str | None = None,
        objective_code: str | None = None,
    ) -> bool:
        """The homework disclosure screen (HOMEWORK_AND_MARKING_CONTRACT §6, rule 6).

        On a phrase-list match, raise ONE concern (``source = system``) about the learner that
        references the submission — idempotent by ``submission_id`` (a resubmission or a retry
        never adds a second). The concern's text is a fixed note naming the matched list entries,
        never the child's words. Returns whether a system concern exists for this submission now.
        Nothing is returned to, or changed for, the child; nothing is logged but counts.

        The screened ``text`` (with its attempt, time, item and objective, as the school context
        passes them) is stored as the concern's immutable evidence in the same transaction, so a
        later resubmission can never replace what the lead reads as flagged. Missing metadata is
        read from the submission; the text is always the one that matched."""
        with self._uow() as uow:
            if uow.concerns.system_concern_for(submission_id) is not None:
                return True
        matched = self._phrases.matches(text)
        if not matched:
            return False
        ids = ", ".join(p.phrase_id for p in matched)[:200]
        note = (
            f"Raised automatically by the homework disclosure screen (starter phrase list, "
            f"pending M-Safe approval). Matched entries: {ids}. Read homework submission "
            f"{submission_id}. The child was not told."
        )
        given: dict[str, Any] = {
            "text": text,
            "attempt": attempt,
            "submitted_at": submitted_at,
            "item_ref": item_ref,
            "objective_code": objective_code,
        }
        if any(v is None for v in given.values()):
            stored = self._current(submission_id, student_ref) or {}
            given = {k: (stored.get(k) if v is None else v) for k, v in given.items()}
        try:
            self._create(
                subject_ref=student_ref,
                raised_by_ref=SYSTEM_RAISER_REF,
                role=RaisedBy.SYSTEM,
                category=strongest_category(matched).value,
                text=note,
                screen="learner/homework",
                lesson_id=None,
                submission_id=submission_id,
                evidence=given,
            )
        except Exception:
            # A concurrent screen of the same submission won the unique index: one concern.
            with self._uow() as uow:
                if uow.concerns.system_concern_for(submission_id) is not None:
                    return True
            raise
        return True

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
        submission_id: str | None = None,
        evidence: dict[str, Any] | None = None,
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
                submission_id=submission_id,
            )
        except InvalidConcernError as exc:
            raise _invalid(exc) from exc
        snapshot = self._snapshot(concern, evidence, now)
        with self._uow() as uow:
            uow.concerns.add(concern)
            if snapshot is not None:
                # Same transaction as the concern: a concern from a submission never exists
                # without the text that prompted it (and the PK keeps it to one per concern).
                uow.evidence.add(snapshot)
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

    @staticmethod
    def _snapshot(
        concern: Concern, evidence: dict[str, Any] | None, now: float
    ) -> ConcernEvidence | None:
        """The evidence row for a concern raised from a submission, or None. An incomplete source
        never blocks the concern itself: raising must always succeed."""
        if concern.context_submission_id is None or not evidence:
            return None
        if any(evidence.get(k) is None for k in _EVIDENCE_KEYS):
            return None
        try:
            return ConcernEvidence.capture(
                concern_id=concern.concern_id,
                submission_id=concern.context_submission_id,
                text=str(evidence["text"]),
                attempt=int(evidence["attempt"]),
                submitted_at=float(evidence["submitted_at"]),
                item_ref=str(evidence["item_ref"]),
                objective_code=str(evidence["objective_code"]),
                now=now,
            )
        except (InvalidConcernError, TypeError, ValueError):
            return None

    def _current(self, submission_id: str, student_ref: str) -> dict[str, Any] | None:
        if self._submissions is None:
            return None
        return self._submissions.submission_for_safeguarding(
            submission_id=submission_id, student_ref=student_ref
        )

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
            "context": {
                "screen": concern.context_screen,
                "lesson_id": concern.context_lesson_id,
                "submission_id": concern.context_submission_id,
            },
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
                # A teacher's concern usually starts from the child's own words, so it carries the
                # same caution as a child's report.
                "household_caution": concern.raised_by_role in (RaisedBy.STUDENT, RaisedBy.TEACHER),
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

    def _phrases_in(self, text: str) -> list[dict[str, Any]]:
        return [
            {
                "phrase_id": p.phrase_id,
                "lang": p.lang,
                "category": p.category.value,
                "phrase": p.phrase,
            }
            for p in self._phrases.matches(text)
        ]

    def context(self, *, actor_ref: str, concern_id: str) -> dict[str, Any]:
        """The flagged homework behind a concern, for the lead (rule 7).

        ``flagged`` is the immutable snapshot captured when the concern was raised (alembic 0018):
        always the text that prompted it, even after a resubmission or after the submission itself
        was erased. ``current`` is the child's latest answer, present only when its text differs.
        A concern that names no submission, or one with no snapshot whose submission is gone (or
        is not its subject's), is a 404 and nothing is audited; every successful read is audited
        before any text is returned, and the audit names the submission, never a word of text."""
        now = self._now()
        with self._uow() as uow:
            concern = self._load(uow, concern_id)
            snapshot = uow.evidence.for_concern(concern.concern_id)
        submission_id = concern.context_submission_id
        if not submission_id:
            raise not_found("this concern has no homework submission to read")
        sub = self._current(submission_id, concern.subject_ref)
        if sub is None and snapshot is None:
            raise not_found("this concern has no homework submission to read")
        with self._uow() as uow:
            self._record(
                uow,
                concern,
                Action.CONTEXT_VIEWED,
                actor_ref,
                now,
                submission_id=str(submission_id),
            )
            uow.commit()
        latest: dict[str, Any] | None = (
            {
                "text": str(sub["text"]),
                "attempt": int(sub["attempt"]),
                "submitted_at": float(sub["submitted_at"]),
            }
            if sub is not None
            else None
        )
        flagged: dict[str, Any] | None = None
        current: dict[str, Any] | None = None
        matched: list[dict[str, Any]] = []
        resubmitted = False
        if snapshot is not None:
            flagged = {
                "text": snapshot.text,
                "attempt": snapshot.attempt,
                "submitted_at": snapshot.submitted_at,
                "item_ref": snapshot.item_ref,
                "objective_code": snapshot.objective_code,
                "text_sha256": snapshot.text_sha256,
                "intact": snapshot.intact,
                "captured_at": snapshot.created_at,
            }
            matched = self._phrases_in(snapshot.text)
            resubmitted = latest is not None and bool(
                latest["attempt"] != snapshot.attempt
                or latest["submitted_at"] != snapshot.submitted_at
                or latest["text"] != snapshot.text
            )
            if latest is not None and latest["text"] != snapshot.text:
                current = {**latest, "matched_phrases": self._phrases_in(latest["text"])}
        elif latest is not None:
            # Raised before snapshots existed: only the latest answer can be shown, and it says so.
            current = {**latest, "matched_phrases": self._phrases_in(latest["text"])}
            matched = current["matched_phrases"]
            resubmitted = bool(latest["submitted_at"] > concern.created_at)
        about: dict[str, Any] = sub if sub is not None else {}
        return {
            "concern_id": concern.concern_id,
            "submission": {
                "submission_id": submission_id,
                "source": about.get("source"),
                "objective_code": (
                    snapshot.objective_code if snapshot else about.get("objective_code")
                ),
                "item_ref": snapshot.item_ref if snapshot else about.get("item_ref"),
                "item_prompt": dict(about.get("item_prompt") or {}),
                "lesson_title": dict(about.get("lesson_title") or {}),
                # False once the submission itself is gone (erased): the snapshot still stands.
                "available": sub is not None,
            },
            "flagged": flagged,
            "current": current,
            "matched_phrases": matched,
            "resubmitted_since_raised": resubmitted,
            "snapshot": snapshot is not None,
            "read_recorded": True,
            "notice": CONTEXT_READ_NOTICE if snapshot is not None else NO_SNAPSHOT_NOTICE,
        }

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
