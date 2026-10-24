"""Reporting use cases (application layer, no framework).

Rules that protect a child live here, so they hold however the service is called:

1. **Derived, never typed in.** A card's figures come only from ``derive_body`` over snapshots
   read through the ports at issue time. The one free text is an attributed teacher comment.
2. **Taleem issues; a teacher is optional.** The primary path is ``issue_for_learner``: a system
   card (``issued_by: "system"``) for any learner with an active account and live learning
   consent, in a class or not — from the scheduler or on their own guardian's request. At most
   one system card exists per learner and identical period (409).
3. **Teacher scope (optional path).** A teacher previews and issues only for their own class
   (school's ``teacher_class``: another class or organization is a 404). Only learners
   currently in that class whom the teacher may see right now (live consent +
   ``progress_sharing`` + an active account) get a card; everyone else is listed in
   ``skipped`` with a stable reason code.
4. **Preview stores nothing.** No card, audit row or outbox event is written for a preview.
5. **Supersede, never edit.** A correction is a new card naming the old one in ``supersedes``;
   naming a card that is already superseded is a 409. Issuing a second card for a learner, class
   and period without it is skipped (``already_issued``). The old card is shown as
   ``superseded``; its stored body never changes.
6. **Relationship-scoped reads.** A guardian reads only their own child's cards and a teacher only
   cards of their own classes' visible learners — anything else is a 404, never a 403, so a probe
   cannot confirm a card exists. A learner reads their own (behind the live consent gate).
7. **Atomic issue.** Cards, their audit rows and their ``ReportCardIssued`` outbox events commit
   in one transaction. Audit rows hold refs only.

A card as returned is its stored, hashed body plus read-time metadata that the hash does not
cover: ``superseded_by``, ``status``, ``acknowledged_at``, ``content_hash`` and ``hash_verified``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ....platform import observability
from ....platform.concurrency import ConcurrencyConflictError
from ....platform.errors import Problem, not_found, validation_error
from ..domain.report_card import (
    ACKNOWLEDGED,
    ALREADY_ISSUED,
    ISSUED,
    NOT_IN_CLASS,
    REPORT_CARD_ISSUED,
    SYSTEM_ISSUER,
    SYSTEM_ISSUER_NAME,
    ClassContext,
    InvalidReportError,
    LearnerRecords,
    Period,
    ReportCard,
    ReportConflictError,
    ReportingAuditEvent,
    canonical_json,
    check_supersedes,
    content_hash,
    current_card,
    derive_body,
    new_card_id,
    newest_first,
)
from .ports import (
    ClassRoster,
    LearnerDirectory,
    LearningRecords,
    PublishedLessons,
    ReportingUnitOfWork,
    SchoolDirectory,
)

UnitOfWorkFactory = Callable[[], ReportingUnitOfWork]
MAX_LEARNERS_PER_ISSUE = 200
# Read-time metadata on a returned card; everything else is the stored, hashed body.
READ_TIME_FIELDS: tuple[str, ...] = (
    "superseded_by",
    "status",
    "acknowledged_at",
    "content_hash",
    "hash_verified",
)


def _card_not_found() -> Problem:
    return not_found("report card not found")


def _problem(exc: InvalidReportError) -> Problem:
    if isinstance(exc, ReportConflictError):
        return Problem(409, exc.code, "Report card cannot change this way", str(exc))
    return validation_error(str(exc))


class _Plan:
    """What an issue (or its preview) would do: who gets a card, who is skipped and why."""

    def __init__(self, roster: ClassRoster, period: Period) -> None:
        self.roster = roster
        self.period = period
        self.included: list[tuple[str, str]] = []  # (student_ref, display name)
        self.skipped: list[dict[str, Any]] = []
        self.supersedes: dict[str, str] = {}

    def skip(self, ref: str, reason: str, name: str | None = None, **extra: Any) -> None:
        self.skipped.append(
            {"student_ref": ref, "learner_display_name": name, "reason": reason, **extra}
        )


class ReportingService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        school: SchoolDirectory,
        learners: LearnerDirectory,
        records: LearningRecords,
        lessons: PublishedLessons,
        clock: Callable[[], float],
    ) -> None:
        self._uow = uow_factory
        self._school = school
        self._learners = learners
        self._records = records
        self._lessons = lessons
        self._now = clock

    # ------------------------------------------------------------------- teacher: issuing

    def preview(
        self,
        *,
        teacher_ref: str,
        class_id: str,
        period_start: int,
        period_end: int,
        student_refs: list[str] | None = None,
        comments: Mapping[str, str] | None = None,
        supersedes: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """The cards that would be issued, with their hashes. Nothing is stored."""
        plan = self._plan(teacher_ref, class_id, period_start, period_end, student_refs, supersedes)
        bodies = self._bodies(plan, teacher_ref, comments or {}, card_ids=False)
        return {
            "class_id": plan.roster.class_id,
            "period_start": plan.period.start,
            "period_end": plan.period.end,
            "stored": False,
            "report_cards": [
                {
                    **body,
                    "superseded_by": None,
                    "status": "preview",
                    "acknowledged_at": None,
                    "content_hash": content_hash(canonical_json(body)),
                    "hash_verified": True,
                }
                for body in bodies
            ],
            "skipped": plan.skipped,
        }

    def issue(
        self,
        *,
        teacher_ref: str,
        class_id: str,
        period_start: int,
        period_end: int,
        student_refs: list[str] | None = None,
        comments: Mapping[str, str] | None = None,
        supersedes: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        plan = self._plan(teacher_ref, class_id, period_start, period_end, student_refs, supersedes)
        bodies = self._bodies(plan, teacher_ref, comments or {}, card_ids=True)
        cards = [ReportCard.issue(body) for body in bodies]
        self._store(cards, actor_ref=teacher_ref, actor_role="teacher")
        if cards:
            observability.record_event("taleem_report_cards_issued_total")
        return {
            "class_id": plan.roster.class_id,
            "period_start": plan.period.start,
            "period_end": plan.period.end,
            "report_cards": [_card_view(c, None) for c in cards],
            "skipped": plan.skipped,
        }

    # ------------------------------------------------------- system issuance (the primary path)

    def issue_for_learner(
        self, student_ref: str, period_start: int, period_end: int
    ) -> dict[str, Any]:
        """Taleem issues a learner's card for a closed period — no class or teacher needed.

        The learner must hold an active account and live learning consent (403
        ``LEARNER_NOT_ELIGIBLE`` otherwise). At most one system card exists per learner per
        identical period: a second is a 409 ``REPORT_CARD_EXISTS``. Used by the scheduler
        (``python -m taleem_core.contexts.reporting.issue_due``) and the guardian's generate."""
        try:
            period = Period.of(period_start, period_end, now=self._now())
        except InvalidReportError as exc:
            raise _problem(exc) from exc
        refusal = self._learners.learning_refusal(student_ref)
        if refusal is not None:
            raise Problem(
                403,
                "LEARNER_NOT_ELIGIBLE",
                "Forbidden",
                f"no report card can be issued for this learner right now ({refusal})",
            )
        with self._uow() as uow:
            existing = current_card(uow.cards.for_slot(student_ref, "", period.start, period.end))
        if existing is not None:
            raise Problem(
                409,
                "REPORT_CARD_EXISTS",
                "Conflict",
                "a report card for this learner and period has already been issued",
            )
        records = LearnerRecords(
            student_ref=student_ref,
            evidence=tuple(self._records.evidence(student_ref)),
            mastery_events=tuple(self._records.mastery_events(student_ref)),
            homework=tuple(self._school.marked_homework(student_ref)),
        )
        body = derive_body(
            records=records,
            lessons=self._lessons.pins(),
            period=period,
            context=None,
            learner_display_name=self._learners.display_name(student_ref) or "",
            issued_by=SYSTEM_ISSUER,
            issued_by_name=SYSTEM_ISSUER_NAME,
            issued_at=self._now(),
            card_id=new_card_id(),
            supersedes=None,
            comment=None,
        )
        card = ReportCard.issue(body)
        try:
            self._store([card], actor_ref=SYSTEM_ISSUER, actor_role="system")
        except ConcurrencyConflictError as exc:  # a concurrent generate won the unique index
            raise Problem(
                409, "REPORT_CARD_EXISTS", "Conflict", "a report card for this period exists"
            ) from exc
        observability.record_event("taleem_report_cards_issued_total", issuer="system")
        return _card_view(card, None)

    def generate_for_child(
        self, *, guardian_ref: str, student_ref: str, period_start: int, period_end: int
    ) -> dict[str, Any]:
        """The guardian asks Taleem for their own child's card (another family's child: 404)."""
        self._require_own_child(guardian_ref, student_ref)
        return self.issue_for_learner(student_ref, period_start, period_end)

    def _store(self, cards: list[ReportCard], *, actor_ref: str, actor_role: str) -> None:
        """Cards + their refs-only audit + their outbox events, in one transaction."""
        now = self._now()
        with self._uow() as uow:
            for card in cards:
                uow.cards.add(card)
                uow.audit.add(
                    ReportingAuditEvent(
                        action=ISSUED,
                        actor_ref=actor_ref,
                        actor_role=actor_role,
                        subject_ref=card.student_ref,
                        organization_id=card.organization_id,
                        class_id=card.class_id,
                        card_id=card.card_id,
                        at=now,
                    )
                )
                uow.outbox.add(
                    event_type=REPORT_CARD_ISSUED,
                    aggregate_id=card.card_id,
                    student_ref=card.student_ref,
                    payload={
                        # Refs only. The guardian's in-app notification is the card itself
                        # (``child_notifications``); the event is for the delivery relay.
                        "card_id": card.card_id,
                        "student_ref": card.student_ref,
                        "guardian_ref": self._learners.guardian_of(card.student_ref),
                        "issued_by": card.issued_by,
                        "organization_id": card.organization_id or None,
                        "class_id": card.class_id or None,
                        "period_start": card.period_start,
                        "period_end": card.period_end,
                        "supersedes": card.supersedes,
                        "content_hash": card.content_hash,
                    },
                )
            uow.commit()

    def _plan(
        self,
        teacher_ref: str,
        class_id: str,
        period_start: int,
        period_end: int,
        student_refs: list[str] | None,
        supersedes: Mapping[str, str] | None,
    ) -> _Plan:
        roster = self._school.teacher_class(teacher_ref=teacher_ref, class_id=class_id)
        try:
            period = Period.of(period_start, period_end, now=self._now())
        except InvalidReportError as exc:
            raise _problem(exc) from exc
        requested = (
            list(dict.fromkeys(student_refs))
            if student_refs is not None
            else list(roster.student_refs)
        )
        if len(requested) > MAX_LEARNERS_PER_ISSUE:
            raise validation_error(f"at most {MAX_LEARNERS_PER_ISSUE} learners per request")
        if set(supersedes or {}) - set(requested):
            raise validation_error("supersedes names a learner who is not in this request")
        plan = _Plan(roster, period)
        members = set(roster.student_refs)
        seen = self._learners.teacher_visibility([r for r in requested if r in members])
        with self._uow() as uow:
            for ref in requested:
                if ref not in members:
                    plan.skip(ref, NOT_IN_CLASS)
                    continue
                visibility = seen.get(ref)
                if visibility is None or not visibility.visible:
                    plan.skip(ref, (visibility.reason if visibility else None) or NOT_IN_CLASS)
                    continue
                name = visibility.display_name or ""
                live = current_card(
                    uow.cards.for_slot(ref, roster.class_id, period.start, period.end)
                )
                wanted = (supersedes or {}).get(ref)
                if wanted is None:
                    if live is not None:
                        plan.skip(ref, ALREADY_ISSUED, name, card_id=live.card_id)
                        continue
                else:
                    old = uow.cards.get(wanted)
                    successor = uow.cards.successors([wanted]).get(wanted) if old else None
                    try:
                        check_supersedes(
                            old,
                            student_ref=ref,
                            class_id=roster.class_id,
                            period=period,
                            successor=successor,
                        )
                    except InvalidReportError as exc:
                        raise _problem(exc) from exc
                    plan.supersedes[ref] = wanted
                plan.included.append((ref, name))
        return plan

    def _bodies(
        self, plan: _Plan, teacher_ref: str, comments: Mapping[str, str], *, card_ids: bool
    ) -> list[dict[str, Any]]:
        named = {r for r, _ in plan.included} | {str(s["student_ref"]) for s in plan.skipped}
        if set(comments) - named:
            raise validation_error("a comment names a learner who is not in this request")
        roster = plan.roster
        context = ClassContext(
            class_id=roster.class_id,
            organization_id=roster.organization_id,
            class_name=roster.class_name,
            organization_name=roster.organization_name,
            curriculum_pack_id=roster.curriculum_pack_id,
            teacher_name=roster.teacher_name,
        )
        lessons = self._lessons.pins() if plan.included else {}
        issued_at = self._now()
        bodies: list[dict[str, Any]] = []
        for ref, name in plan.included:
            records = LearnerRecords(
                student_ref=ref,
                evidence=tuple(self._records.evidence(ref)),
                mastery_events=tuple(self._records.mastery_events(ref)),
                homework=tuple(self._school.marked_homework(ref)),
            )
            try:
                bodies.append(
                    derive_body(
                        records=records,
                        lessons=lessons,
                        period=plan.period,
                        context=context,
                        learner_display_name=name,
                        issued_by=teacher_ref,
                        issued_by_name=roster.teacher_name,
                        issued_at=issued_at,
                        card_id=new_card_id() if card_ids else None,
                        supersedes=plan.supersedes.get(ref),
                        comment=comments.get(ref),
                    )
                )
            except InvalidReportError as exc:
                raise _problem(exc) from exc
        return bodies

    # -------------------------------------------------------------------- teacher: reading

    def class_cards(self, *, teacher_ref: str, class_id: str) -> list[dict[str, Any]]:
        """Cards issued in the teacher's own class, for learners they may see now."""
        roster = self._school.teacher_class(teacher_ref=teacher_ref, class_id=class_id)
        visible = self._visible(list(roster.student_refs))
        with self._uow() as uow:
            cards = [
                c
                for c in uow.cards.for_class(roster.organization_id, roster.class_id)
                if c.student_ref in visible
            ]
            return self._views(uow, cards)

    def learner_cards_for_teacher(
        self, *, teacher_ref: str, student_ref: str
    ) -> list[dict[str, Any]]:
        """A learner's cards from the teacher's own classes the learner is in (and visible)."""
        classes = self._teacher_classes_with(teacher_ref, student_ref)
        if not classes:
            raise not_found("learner not found")
        with self._uow() as uow:
            cards = [
                c
                for c in uow.cards.for_student(student_ref)
                if (c.organization_id, c.class_id) in classes
            ]
            return self._views(uow, cards)

    # ------------------------------------------------------------------- guardian / learner

    def child_cards(self, *, guardian_ref: str, student_ref: str) -> list[dict[str, Any]]:
        self._require_own_child(guardian_ref, student_ref)
        return self.learner_cards(student_ref)

    def learner_cards(self, student_ref: str) -> list[dict[str, Any]]:
        with self._uow() as uow:
            return self._views(uow, uow.cards.for_student(student_ref))

    def child_notifications(self, *, guardian_ref: str, student_ref: str) -> dict[str, Any]:
        """The guardian's in-app notifications for one child: one per issued card that is still
        current (a superseded card's notice is replaced by its correction's). Read state is the
        server-side acknowledgement."""
        self._require_own_child(guardian_ref, student_ref)
        with self._uow() as uow:
            cards = newest_first(uow.cards.for_student(student_ref))
            replaced = uow.cards.successors([c.card_id for c in cards])
        notes = [
            {
                "id": f"report-card-{c.card_id}",
                "kind": "report_card_issued",
                "card_id": c.card_id,
                "student_ref": c.student_ref,
                "class_id": c.class_id or None,
                "period_start": c.period_start,
                "period_end": c.period_end,
                "supersedes": c.supersedes,
                "issued_at": c.issued_at,
                "read": c.acknowledged_at is not None,
            }
            for c in cards
            if c.card_id not in replaced
        ]
        return {"notifications": notes, "unread": sum(1 for n in notes if not n["read"])}

    def get_card(self, *, actor_ref: str, role: str, card_id: str) -> dict[str, Any]:
        with self._uow() as uow:
            card = uow.cards.get(card_id)
            if card is None:
                raise _card_not_found()
            self._require_reader(card, actor_ref=actor_ref, role=role)
            return self._views(uow, [card])[0]

    def acknowledge(self, *, guardian_ref: str, card_id: str) -> dict[str, Any]:
        """Record that the guardian has seen the card — once; a second time is a 409."""
        with self._uow() as uow:
            card = uow.cards.get(card_id)
            if card is None:
                raise _card_not_found()
            self._require_reader(card, actor_ref=guardian_ref, role="guardian")
            now = self._now()
            try:
                card.acknowledged(guardian_ref=guardian_ref, at=now)
            except InvalidReportError as exc:
                raise _problem(exc) from exc
            if not uow.cards.acknowledge(card.card_id, guardian_ref, now):  # lost a race
                raise _problem(
                    ReportConflictError(
                        "this report card has already been acknowledged",
                        code="ALREADY_ACKNOWLEDGED",
                    )
                )
            uow.audit.add(
                ReportingAuditEvent(
                    action=ACKNOWLEDGED,
                    actor_ref=guardian_ref,
                    actor_role="guardian",
                    subject_ref=card.student_ref,
                    organization_id=card.organization_id,
                    class_id=card.class_id,
                    card_id=card.card_id,
                    at=now,
                )
            )
            uow.commit()
        return {"card_id": card.card_id, "acknowledged_at": now}

    # ------------------------------------------------------------------------------ helpers

    def _views(self, uow: ReportingUnitOfWork, cards: list[ReportCard]) -> list[dict[str, Any]]:
        ordered = newest_first(cards)
        successors = uow.cards.successors([c.card_id for c in ordered])
        return [_card_view(c, successors.get(c.card_id)) for c in ordered]

    def _visible(self, refs: list[str]) -> set[str]:
        return {r for r, v in self._learners.teacher_visibility(refs).items() if v.visible}

    def _teacher_classes_with(self, teacher_ref: str, student_ref: str) -> set[tuple[str, str]]:
        """(organization, class) of the teacher's own classes the learner is in — empty when the
        learner is in none of them or the teacher may not see them right now."""
        classes = {
            (r.organization_id, r.class_id)
            for r in self._school.teacher_classes(teacher_ref)
            if student_ref in r.student_refs
        }
        if not classes or student_ref not in self._visible([student_ref]):
            return set()
        return classes

    def _require_own_child(self, guardian_ref: str, student_ref: str) -> None:
        if not student_ref or self._learners.guardian_of(student_ref) != guardian_ref:
            raise not_found("learner not found")  # the same answer as identity's IDOR guard

    def _require_reader(self, card: ReportCard, *, actor_ref: str, role: str) -> None:
        if role == "guardian":
            allowed = self._learners.guardian_of(card.student_ref) == actor_ref
        elif role == "teacher":
            classes = self._teacher_classes_with(actor_ref, card.student_ref)
            allowed = (card.organization_id, card.class_id) in classes
        else:
            allowed = False
        if not allowed:
            raise _card_not_found()


def _card_view(card: ReportCard, superseded_by: str | None) -> dict[str, Any]:
    """The stored body (hash-covered) plus read-time metadata; the hash is re-verified."""
    return {
        **card.body,
        "superseded_by": superseded_by,
        "status": "superseded" if superseded_by else "issued",
        "acknowledged_at": card.acknowledged_at,
        "content_hash": card.content_hash,
        "hash_verified": card.verify(),
    }
