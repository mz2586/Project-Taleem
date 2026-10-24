"""Report cards (REPORT_CARD_CONTRACT.md §1): pure derivation over snapshots, canonical JSON, hash.

``derive_body`` is a pure function. It is given snapshots of what other contexts already hold —
the learner's assessment evidence and mastery events (learning), their marked homework (school),
and the published lesson of each objective with its version (curriculum read model) — and returns
the card body. It reads no clock and no store, so the same snapshots always give the same body.

Derivation rules (the stored body names them by ``derivation``):

* **Period.** ``start`` is inclusive and ``end`` exclusive (``start <= t < end``), so two adjacent
  periods never count the same record twice.
* **Attempts** are auto-scored evidence in the period: every evidence row except diagnostic
  placement answers and the evidence a teacher's homework mark recorded (its ``evidence_id`` is
  the ``submission_id``; that work is counted under homework instead, never twice). ``correct``
  counts outcome ``correct`` only (a ``partial`` is not correct).
* **Issuer.** The primary issuer is Taleem itself (``issued_by: "system"``, name "Taleem"): a
  system card needs no class or teacher (``class_id`` / ``class_name`` / ``organization_id`` are
  null) and carries no comment. A teacher may also issue a card for their own class; only such a
  card may carry the one free-text field, an attributed comment.
* **Homework** is the learner's marked submissions in the period, as ``met`` / ``not_yet``
  counts: in the card's class, or in every class for a system card.
* **Objectives listed** are exactly those with at least one attempt or marked homework in the
  period. A card with none says so (``has_evidence: false``, ``notice: no_evidence_in_period``,
  ``totals: null``, no objectives): it never shows zeros as if they were results.
* **Mastery state as of the period end.** ``mastered`` when an ``ObjectiveMastered`` event for the
  objective happened before ``end``; otherwise ``developing`` when any practice evidence or marked
  homework for it happened before ``end``; otherwise ``not_started``.
* **Version pin (from the evidence).** Each objective cites the lesson versions its counted
  evidence was answered against — the auto-scored attempts in the period plus the evidence of the
  homework marks listed — as each evidence row recorded them (``lesson_id``,
  ``lesson_version``), never the version published when the card is issued:

  - ``lesson_versions``: every distinct recorded version, ascending;
  - ``lesson_version``: that version when it is the only one *and* every counted row recorded it
    (unambiguous), else ``null``;
  - ``lesson_id``: the one lesson id the rows recorded (``null`` when none or several; then
    ``lesson_ids`` lists them, ascending);
  - ``version_source``: ``evidence`` when every counted row carries a version, ``unrecorded``
    when none does (rows written before versions were recorded, an offline attempt whose package
    named none, or no counted row at all), ``mixed`` otherwise; ``unversioned_evidence`` counts
    the rows without one. An unrecorded part is said so, never filled in from the current pin.

  The card keeps that pin forever, whatever is published later. Title and subject still come
  from the lesson published at issue time (display only): an objective whose lesson is no longer
  published has ``title: {}`` and is grouped under subject ``other``.

  Cards derived by ``taleem.reporting.derive/1`` pinned the version published at issue time
  instead; they are stored unchanged and still verify against their stored hash.

The body is serialised as canonical JSON (sorted keys, no insignificant whitespace, UTF-8) and its
``content_hash`` is the SHA-256 of exactly those bytes. A stored card can always be re-verified.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ....platform.ids import uuid7

REPORT_FORMAT = "taleem.report-card/1"
DERIVATION = "taleem.reporting.derive/2"
# Earlier derivations whose stored cards still verify (their bodies are never re-derived).
PREVIOUS_DERIVATIONS: tuple[str, ...] = ("taleem.reporting.derive/1",)
VERSION_FROM_EVIDENCE, VERSION_MIXED, VERSION_UNRECORDED = "evidence", "mixed", "unrecorded"
VERSION_SOURCES: tuple[str, ...] = (VERSION_FROM_EVIDENCE, VERSION_MIXED, VERSION_UNRECORDED)
PERIOD_RULE = "start_inclusive_end_exclusive"
NO_EVIDENCE_NOTICE = "no_evidence_in_period"
CARD_PREFIX = "rpc_"
MAX_COMMENT = 1000
OTHER_SUBJECT = "other"

MASTERED, DEVELOPING, NOT_STARTED = "mastered", "developing", "not_started"
MASTERY_STATES: tuple[str, ...] = (MASTERED, DEVELOPING, NOT_STARTED)
HOMEWORK_OUTCOMES: tuple[str, ...] = ("met", "not_yet")
DIAGNOSTIC_CONTEXT = "diagnostic"

# Why a learner named (or enrolled) was left out of an issue (REPORT_CARD_CONTRACT §2).
NOT_IN_CLASS = "not_in_class"
CONSENT_WITHDRAWN = "consent_withdrawn"  # learning consent or progress_sharing not live
INACTIVE = "inactive"  # the learner's account is suspended (or no longer exists)
ALREADY_ISSUED = "already_issued"  # a current card exists; a correction must name it
SKIP_REASONS: tuple[str, ...] = (NOT_IN_CLASS, CONSENT_WITHDRAWN, INACTIVE, ALREADY_ISSUED)

ISSUED, ACKNOWLEDGED = "report_card.issued", "report_card.acknowledged"
AUDIT_ACTIONS: tuple[str, ...] = (ISSUED, ACKNOWLEDGED)
AUDIT_ROLES: tuple[str, ...] = ("system", "teacher", "guardian")
REPORT_CARD_ISSUED = "ReportCardIssued"
# The primary issuer: Taleem itself (an AI-led school needs no teacher for a card to exist).
SYSTEM_ISSUER = "system"
SYSTEM_ISSUER_NAME = "Taleem"

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # keeps \t \n \r


class InvalidReportError(ValueError):
    """A request violates a report-card rule (HTTP 422)."""


class ReportConflictError(InvalidReportError):
    """The card cannot change this way (HTTP 409)."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


# ----------------------------------------------------------------------------- snapshots


@dataclass(frozen=True)
class Period:
    start: int
    end: int

    @staticmethod
    def of(start: int, end: int, *, now: float) -> Period:
        """Validate a requested period: whole epoch seconds, ``start < end``, end not future."""
        for value in (start, end):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise InvalidReportError("period bounds must be whole epoch seconds (>= 0)")
        if start >= end:
            raise InvalidReportError("period_start must be before period_end")
        if end > now:
            raise InvalidReportError("period_end must not be in the future")
        return Period(start, end)

    def contains(self, at: float) -> bool:
        return self.start <= at < self.end


@dataclass(frozen=True)
class EvidenceRecord:
    """One immutable assessment-evidence row (learning context)."""

    evidence_id: str
    objective_code: str
    outcome: str  # correct | incorrect | partial
    context: str  # diagnostic | practice | spaced_review | ...
    occurred_at: float
    # The published lesson the attempt was answered against, as recorded on the evidence.
    # ``""`` / ``None``: not recorded (never guessed).
    lesson_id: str = ""
    lesson_version: int | None = None


@dataclass(frozen=True)
class MasteryEvent:
    """An ``ObjectiveMastered`` event (learning outbox)."""

    objective_code: str
    at: float


@dataclass(frozen=True)
class HomeworkOutcome:
    """A marked homework submission (school context)."""

    submission_id: str
    class_id: str
    objective_code: str
    outcome: str  # met | not_yet
    marked_at: float


@dataclass(frozen=True)
class LessonPin:
    """The published lesson an objective is taught by, at issue time (curriculum read model).
    Since ``derive/2`` it gives the objective's title and subject only; the version pin comes
    from the evidence (``evidence_pin``)."""

    objective_code: str
    lesson_id: str
    version: int
    curriculum_pack: str
    subject_key: str
    title: Mapping[str, str]
    subject_name: Mapping[str, str] = dataclasses.field(default_factory=dict)


@dataclass(frozen=True)
class LearnerRecords:
    """Everything a card is derived from, for one learner. Homework spans all their classes (so a
    mark is never also counted as an auto-scored attempt); only this class's homework is listed."""

    student_ref: str
    evidence: tuple[EvidenceRecord, ...] = ()
    mastery_events: tuple[MasteryEvent, ...] = ()
    homework: tuple[HomeworkOutcome, ...] = ()


@dataclass(frozen=True)
class ClassContext:
    class_id: str
    organization_id: str
    class_name: str
    organization_name: str
    curriculum_pack_id: str
    teacher_name: str = ""


# ----------------------------------------------------------------------------- derivation


def clean_comment(raw: str | None) -> str | None:
    """The one free-text field: NFC, control characters removed, trimmed, at most 1000 chars."""
    text = _CONTROL.sub("", unicodedata.normalize("NFC", raw or "")).strip()
    if len(text) > MAX_COMMENT:
        raise InvalidReportError(f"a teacher comment must be at most {MAX_COMMENT} characters")
    return text or None


def auto_scored_attempts(records: LearnerRecords, period: Period) -> list[EvidenceRecord]:
    marked = {h.submission_id for h in records.homework}
    return [
        e
        for e in records.evidence
        if e.context != DIAGNOSTIC_CONTEXT
        # A homework mark's evidence: the submission id, or ``{submission_id}:{attempt}`` for an
        # automatic retry (HOMEWORK_AND_MARKING_CONTRACT §6). Counted as homework, not here.
        and e.evidence_id.split(":", 1)[0] not in marked and period.contains(e.occurred_at)
    ]


def class_homework(
    records: LearnerRecords, period: Period, class_id: str | None
) -> list[HomeworkOutcome]:
    """Marked homework in the period: of one class, or (``None``, a system card) of all."""
    return [
        h
        for h in records.homework
        if (class_id is None or h.class_id == class_id)
        and h.outcome in HOMEWORK_OUTCOMES
        and period.contains(h.marked_at)
    ]


def mastery_state_at(records: LearnerRecords, objective_code: str, end: float) -> str:
    """The objective's state as of ``end`` (exclusive), from events and evidence only."""
    if any(m.objective_code == objective_code and m.at < end for m in records.mastery_events):
        return MASTERED
    practised = any(
        e.objective_code == objective_code
        and e.context != DIAGNOSTIC_CONTEXT
        and e.occurred_at < end
        for e in records.evidence
    ) or any(
        h.objective_code == objective_code and h.outcome in HOMEWORK_OUTCOMES and h.marked_at < end
        for h in records.homework
    )
    return DEVELOPING if practised else NOT_STARTED


def evidence_pin(rows: Iterable[EvidenceRecord]) -> dict[str, Any]:
    """The version pin of one objective from the evidence rows the card counts for it (see the
    module docstring). Pure; an unrecorded row is reported, never replaced."""
    rows = list(rows)
    versions = sorted({e.lesson_version for e in rows if e.lesson_version is not None})
    lesson_ids = sorted({e.lesson_id for e in rows if e.lesson_id})
    unversioned = sum(1 for e in rows if e.lesson_version is None)
    if rows and not unversioned:
        source = VERSION_FROM_EVIDENCE
    elif unversioned == len(rows):
        source = VERSION_UNRECORDED
    else:
        source = VERSION_MIXED
    single_id = lesson_ids[0] if len(lesson_ids) == 1 else None
    unambiguous = source == VERSION_FROM_EVIDENCE and len(versions) == 1 and single_id is not None
    return {
        "lesson_id": single_id,
        "lesson_ids": lesson_ids,
        "lesson_version": versions[0] if unambiguous else None,
        "lesson_versions": versions,
        "version_source": source,
        "unversioned_evidence": unversioned,
    }


def _objective(
    code: str,
    *,
    attempts: list[EvidenceRecord],
    homework: list[HomeworkOutcome],
    marked_evidence: list[EvidenceRecord],
    pin: LessonPin | None,
    state: str,
) -> dict[str, Any]:
    mine = [e for e in attempts if e.objective_code == code]
    marks = [h for h in homework if h.objective_code == code]
    marked = [e for e in marked_evidence if e.objective_code == code]
    return {
        "objective_code": code,
        "title": dict(pin.title) if pin else {},
        "mastery": state,
        "attempts": len(mine),
        "correct": sum(1 for e in mine if e.outcome == "correct"),
        "homework_met": sum(1 for h in marks if h.outcome == "met"),
        "homework_not_yet": sum(1 for h in marks if h.outcome == "not_yet"),
        **evidence_pin([*mine, *marked]),
    }


def derive_body(
    *,
    records: LearnerRecords,
    lessons: Mapping[str, LessonPin],
    period: Period,
    context: ClassContext | None,
    learner_display_name: str,
    issued_by: str,
    issued_by_name: str,
    issued_at: float,
    card_id: str | None,
    supersedes: str | None,
    comment: str | None,
) -> dict[str, Any]:
    """The card body for one learner (pure; see the module docstring for every rule). Every key
    of the returned dict is covered by the content hash."""
    attempts = auto_scored_attempts(records, period)
    homework = class_homework(records, period, context.class_id if context else None)
    listed_marks = {h.submission_id for h in homework}
    # The evidence a listed homework mark recorded (its evidence_id is the submission_id).
    marked_evidence = [e for e in records.evidence if e.evidence_id in listed_marks]
    codes = sorted({e.objective_code for e in attempts} | {h.objective_code for h in homework})
    objectives = [
        _objective(
            code,
            attempts=attempts,
            homework=homework,
            marked_evidence=marked_evidence,
            pin=lessons.get(code),
            state=mastery_state_at(records, code, period.end),
        )
        for code in codes
    ]
    by_subject: dict[str, list[dict[str, Any]]] = {}
    names: dict[str, dict[str, str]] = {}
    for obj in objectives:
        pin = lessons.get(obj["objective_code"])
        subject = (pin.subject_key if pin and pin.subject_key else "") or OTHER_SUBJECT
        by_subject.setdefault(subject, []).append(obj)
        if pin is not None and subject not in names and pin.subject_name:
            names[subject] = dict(pin.subject_name)
    has_evidence = bool(objectives)
    if context is not None:
        pack: str | None = context.curriculum_pack_id or None
    else:  # a system card has no class: cite the pack of the lessons it lists
        packs = sorted(
            {p.curriculum_pack for c in codes if (p := lessons.get(c)) and p.curriculum_pack}
        )
        pack = packs[0] if len(packs) == 1 else (",".join(packs) or None)
    if issued_by == SYSTEM_ISSUER and comment:
        raise InvalidReportError("only a teacher-issued card carries a comment")
    return {
        "format": REPORT_FORMAT,
        "derivation": DERIVATION,
        "card_id": card_id,
        "student_ref": records.student_ref,
        "learner_display_name": learner_display_name,
        "class_id": context.class_id if context else None,
        "class_name": context.class_name if context else None,
        "organization_id": context.organization_id if context else None,
        "organization_name": context.organization_name if context else None,
        "curriculum_pack": pack,
        "period_start": period.start,
        "period_end": period.end,
        "period_rule": PERIOD_RULE,
        "issued_by": issued_by,
        "issued_by_name": issued_by_name,
        "issued_at": round(float(issued_at), 3),
        "supersedes": supersedes,
        "comment": clean_comment(comment),
        "has_evidence": has_evidence,
        "notice": None if has_evidence else NO_EVIDENCE_NOTICE,
        "totals": (
            {
                "objectives": len(objectives),
                "objectives_mastered": sum(1 for o in objectives if o["mastery"] == MASTERED),
                "attempts": len(attempts),
                "correct": sum(1 for e in attempts if e.outcome == "correct"),
                "homework_met": sum(1 for h in homework if h.outcome == "met"),
                "homework_not_yet": sum(1 for h in homework if h.outcome == "not_yet"),
            }
            if has_evidence
            else None
        ),
        "subjects": [
            {
                "subject_key": key,
                "subject_name": names.get(key) or {"ur": key, "en": key},
                "objectives": by_subject[key],
            }
            for key in sorted(by_subject)
        ],
    }


# ------------------------------------------------------------------------------- hashing


def canonical_json(body: Mapping[str, Any]) -> str:
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def content_hash(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def new_card_id() -> str:
    return f"{CARD_PREFIX}{uuid7()}"


# ------------------------------------------------------------------------------ the card


@dataclass(frozen=True)
class ReportCard:
    """An issued card. Everything but the acknowledgement is fixed when it is issued."""

    card_id: str
    student_ref: str
    organization_id: str
    class_id: str
    period_start: int
    period_end: int
    body_json: str  # canonical JSON, exactly the bytes the hash covers
    content_hash: str
    supersedes: str | None
    issued_by: str
    issued_at: float
    acknowledged_at: float | None = None
    acknowledged_by: str | None = None

    @staticmethod
    def issue(body: Mapping[str, Any]) -> ReportCard:
        card_id = body.get("card_id")
        if not isinstance(card_id, str) or not card_id.startswith(CARD_PREFIX):
            raise InvalidReportError("an issued card needs its card_id in the body")
        canonical = canonical_json(body)
        return ReportCard(
            card_id=card_id,
            student_ref=str(body["student_ref"]),
            organization_id=str(body.get("organization_id") or ""),
            class_id=str(body.get("class_id") or ""),
            period_start=int(body["period_start"]),
            period_end=int(body["period_end"]),
            body_json=canonical,
            content_hash=content_hash(canonical),
            supersedes=body.get("supersedes"),
            issued_by=str(body["issued_by"]),
            issued_at=float(body["issued_at"]),
        )

    @property
    def body(self) -> dict[str, Any]:
        """The stored body (an unreadable one reads as ``{}``; ``verify`` reports it)."""
        try:
            loaded = json.loads(self.body_json)
        except ValueError:
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def verify(self) -> bool:
        """Re-verify the stored card: the hash covers exactly the stored bytes, those bytes are
        canonical, and the body names the same card, learner, class, period and supersedes as the
        row it is stored in."""
        if content_hash(self.body_json) != self.content_hash:
            return False
        try:
            body = json.loads(self.body_json)
        except ValueError:
            return False
        if not isinstance(body, dict) or canonical_json(body) != self.body_json:
            return False
        return (
            body.get("card_id") == self.card_id
            and body.get("student_ref") == self.student_ref
            and (body.get("organization_id") or "") == self.organization_id
            and (body.get("class_id") or "") == self.class_id
            and body.get("supersedes") == self.supersedes
            and body.get("issued_by") == self.issued_by
            and body.get("period_start") == self.period_start
            and body.get("period_end") == self.period_end
        )

    def same_slot(self, *, student_ref: str, class_id: str, period: Period) -> bool:
        return (
            self.student_ref == student_ref
            and self.class_id == class_id
            and (self.period_start, self.period_end) == (period.start, period.end)
        )

    def acknowledged(self, *, guardian_ref: str, at: float) -> ReportCard:
        """Once: a second acknowledgement is a conflict (the client reads it as "already seen")."""
        if self.acknowledged_at is not None:
            raise ReportConflictError(
                "this report card has already been acknowledged", code="ALREADY_ACKNOWLEDGED"
            )
        return dataclasses.replace(self, acknowledged_at=at, acknowledged_by=guardian_ref)


def current_card(cards: Iterable[ReportCard]) -> ReportCard | None:
    """The live card of one learner/class/period chain: the one nothing supersedes."""
    chain = list(cards)
    replaced = {c.supersedes for c in chain if c.supersedes}
    live = [c for c in chain if c.card_id not in replaced]
    return max(live, key=lambda c: (c.issued_at, c.card_id)) if live else None


def check_supersedes(
    old: ReportCard | None,
    *,
    student_ref: str,
    class_id: str,
    period: Period,
    successor: str | None,
) -> ReportCard:
    """A correction names this learner's card for this class and period, not yet superseded."""
    if old is None or not old.same_slot(student_ref=student_ref, class_id=class_id, period=period):
        raise InvalidReportError(
            "supersedes must name this learner's report card for this class and period"
        )
    if successor is not None:
        raise ReportConflictError(
            "that report card has already been superseded", code="ALREADY_SUPERSEDED"
        )
    return old


def newest_first(cards: Iterable[ReportCard]) -> list[ReportCard]:
    return sorted(cards, key=lambda c: (c.issued_at, c.card_id), reverse=True)


@dataclass(frozen=True)
class ReportingAuditEvent:
    """Who issued or acknowledged which card, when. Refs only: never the comment or a figure."""

    action: str
    actor_ref: str
    actor_role: str
    subject_ref: str
    organization_id: str
    class_id: str
    card_id: str
    at: float
