"""Safeguarding concern aggregate and its rules (pure stdlib).

A concern is raised by a child (``student``) about themselves, or by a guardian about one of their
own learners. It holds pseudonymous refs only — never a name copied from identity. It then moves
through a small, closed lifecycle that a safeguarding lead drives:

    open ──acknowledge──▶ acknowledged ──escalate──▶ escalated ──resolve──▶ resolved
      └────────────escalate──────────────▲   └─────────────resolve─────────────▲
      └────────────────────────────resolve────────────────────────────────────┘

``escalated`` means **"external referral needed"** — a human decision recorded for a human to act
on. Nothing in this software contacts anyone: the referral channels are FD-04 (counsel +
safeguarding) and do not exist yet.

Priority tiers follow doc 52 §2 (T0–T3). The category decides the tier; no category maps to T0,
because a T0 ("imminent harm") promise needs a live human within minutes, 24/7, which is not staffed
(FD-06). Every child-facing confirmation instead tells the child to find a grown-up near them now.

SLA thresholds are configuration with **no default value**: an unset SLA means "not decided"
(FD-06), never a number this code invented. Only when a threshold is configured can a concern be
overdue.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from ....platform.ids import uuid7

CONCERN_REF_PREFIX = "sgc_"
MAX_FREE_TEXT = 500  # a short message; the child flow works with none at all
MAX_NOTE = 2000
MAX_SCREEN = 64
MAX_LESSON_ID = 128


class InvalidConcernError(ValueError):
    """A proposed concern or triage action breaks a domain rule."""

    def __init__(
        self, message: str, *, code: str = "SAFEGUARDING_INVALID", field: str = ""
    ) -> None:
        super().__init__(message)
        self.code = code
        self.field = field


class Category(StrEnum):
    """The fixed, tap-to-choose list (doc 15 §2 harm model, worded for a child in the web app)."""

    FELT_UNSAFE = "felt_unsafe"  # "Someone made me feel unsafe"
    VERY_SAD = "very_sad"  # "I feel very sad or scared"
    BULLYING = "bullying"  # "Someone is bullying me"
    UPSETTING_LESSON = "upsetting_lesson"  # "Something in a lesson upset me"
    OTHER = "other"  # "Something else"


class Priority(StrEnum):
    """Doc 52 §2 tiers. T0 is reserved and never assigned by a category (see module docstring)."""

    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


PRIORITY_ORDER: dict[Priority, int] = {Priority.T1: 1, Priority.T2: 2, Priority.T3: 3}

CATEGORY_PRIORITY: dict[Category, Priority] = {
    Category.FELT_UNSAFE: Priority.T1,  # possible abuse / grooming disclosure
    Category.VERY_SAD: Priority.T1,  # possible distress
    Category.BULLYING: Priority.T2,
    Category.UPSETTING_LESSON: Priority.T2,
    Category.OTHER: Priority.T3,
}


class RaisedBy(StrEnum):
    STUDENT = "student"
    GUARDIAN = "guardian"


class Status(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    ESCALATED = "escalated"  # external referral needed (a human decision; nobody is contacted)
    RESOLVED = "resolved"


OPEN_STATUSES: frozenset[Status] = frozenset({Status.OPEN, Status.ACKNOWLEDGED, Status.ESCALATED})


class Outcome(StrEnum):
    NO_FURTHER_ACTION = "no_further_action"
    SUPPORT_GIVEN = "support_given"
    REFERRED_EXTERNALLY = "referred_externally"  # a human made the referral, outside this system
    DUPLICATE = "duplicate"


class Action(StrEnum):
    """Audited actions. Every one names its actor (the token subject)."""

    RAISED = "concern.raised"
    VIEWED = "concern.viewed"
    ACKNOWLEDGED = "concern.acknowledged"
    NOTE_ADDED = "concern.note_added"
    ESCALATED = "concern.escalated"
    RESOLVED = "concern.resolved"


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SCREEN = re.compile(r"^[a-z0-9][a-z0-9/_\-]{0,63}$")
_LESSON = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,127}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")


def _enum(kind: type[StrEnum], raw: str, *, field_name: str) -> StrEnum:
    try:
        return kind(raw)
    except ValueError:
        allowed = ", ".join(v.value for v in kind)
        raise InvalidConcernError(
            f"{field_name} must be one of: {allowed}", field=field_name
        ) from None


def parse_category(raw: str) -> Category:
    return Category(_enum(Category, raw, field_name="category"))


def parse_outcome(raw: str) -> Outcome:
    return Outcome(_enum(Outcome, raw, field_name="outcome"))


def clean_text(raw: str | None, *, limit: int, field_name: str) -> str | None:
    """Normalise free text: NFC, control characters removed, trimmed, bounded. Empty -> None."""
    if raw is None:
        return None
    text = _CONTROL.sub("", unicodedata.normalize("NFC", raw)).strip()
    if not text:
        return None
    if len(text) > limit:
        raise InvalidConcernError(
            f"{field_name} must be at most {limit} characters", field=field_name
        )
    return text


def clean_screen(raw: str | None) -> str:
    """The screen the concern came from, as a route-like token (``student/today``). Anything that
    does not look like one — including a path carrying ids — is dropped, never stored verbatim."""
    if not raw:
        return ""
    token = raw.strip().strip("/").lower()[:MAX_SCREEN]
    return token if _SCREEN.match(token) else ""


def clean_lesson_id(raw: str | None) -> str | None:
    if not raw:
        return None
    lesson = raw.strip()
    if not _LESSON.match(lesson):
        raise InvalidConcernError("lessonId is not a lesson id", field="lessonId")
    return lesson


def assert_ref(raw: str, *, field_name: str) -> str:
    if not _REF.match(raw or ""):
        raise InvalidConcernError(f"{field_name} is not a valid reference", field=field_name)
    return raw


@dataclass
class Note:
    note_id: str
    concern_id: str
    author_ref: str
    body: str
    created_at: float


@dataclass(frozen=True)
class AuditEntry:
    event_id: str
    concern_id: str
    action: str
    actor_ref: str
    actor_role: str
    at: float
    detail: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def record(
        *,
        concern_id: str,
        action: Action,
        actor_ref: str,
        actor_role: str,
        at: float,
        **detail: str,
    ) -> AuditEntry:
        # Detail carries statuses and enum values only — never free text or a note body.
        return AuditEntry(
            event_id=f"sga_{uuid7()}",
            concern_id=concern_id,
            action=action.value,
            actor_ref=actor_ref,
            actor_role=actor_role,
            at=at,
            detail=dict(detail),
        )


@dataclass
class Concern:
    concern_id: str
    subject_ref: str  # the learner the concern is about (pseudonymous student_ref)
    raised_by_ref: str
    raised_by_role: RaisedBy
    category: Category
    priority: Priority
    free_text: str | None
    context_screen: str
    context_lesson_id: str | None
    status: Status
    created_at: float
    acknowledged_at: float | None = None
    acknowledged_by: str | None = None
    escalated_at: float | None = None
    escalated_by: str | None = None
    resolved_at: float | None = None
    resolved_by: str | None = None
    outcome: Outcome | None = None
    version: int = 1

    @staticmethod
    def raise_new(
        *,
        subject_ref: str,
        raised_by_ref: str,
        raised_by_role: RaisedBy,
        category: str,
        free_text: str | None,
        screen: str | None,
        lesson_id: str | None,
        now: float,
    ) -> Concern:
        cat = parse_category(category)
        if raised_by_role is RaisedBy.STUDENT and subject_ref != raised_by_ref:
            # A child raises a concern about themselves; they cannot name another learner.
            raise InvalidConcernError("a learner raises a concern about themselves")
        return Concern(
            concern_id=f"{CONCERN_REF_PREFIX}{uuid7()}",
            subject_ref=assert_ref(subject_ref, field_name="studentRef"),
            raised_by_ref=assert_ref(raised_by_ref, field_name="raisedBy"),
            raised_by_role=raised_by_role,
            category=cat,
            priority=CATEGORY_PRIORITY[cat],
            free_text=clean_text(free_text, limit=MAX_FREE_TEXT, field_name="text"),
            context_screen=clean_screen(screen),
            context_lesson_id=clean_lesson_id(lesson_id),
            status=Status.OPEN,
            created_at=now,
        )

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    # --------------------------------------------------------------------------- transitions

    def acknowledge(self, *, actor_ref: str, now: float) -> bool:
        """Open -> acknowledged. Returns False (no change) if already past ``open``."""
        if self.status is Status.RESOLVED:
            raise InvalidConcernError("a resolved concern cannot change", code="CONCERN_CLOSED")
        if self.status is not Status.OPEN:
            return False
        self.status = Status.ACKNOWLEDGED
        self.acknowledged_at = now
        self.acknowledged_by = actor_ref
        return True

    def escalate(self, *, actor_ref: str, now: float) -> bool:
        """Mark "external referral needed". Implies acknowledgement. Contacts nobody."""
        if self.status is Status.RESOLVED:
            raise InvalidConcernError("a resolved concern cannot change", code="CONCERN_CLOSED")
        if self.status is Status.ESCALATED:
            return False
        if self.acknowledged_at is None:
            self.acknowledged_at = now
            self.acknowledged_by = actor_ref
        self.status = Status.ESCALATED
        self.escalated_at = now
        self.escalated_by = actor_ref
        return True

    def resolve(self, *, actor_ref: str, outcome: str, now: float) -> None:
        if self.status is Status.RESOLVED:
            raise InvalidConcernError("this concern is already resolved", code="CONCERN_CLOSED")
        result = parse_outcome(outcome)
        if result is Outcome.REFERRED_EXTERNALLY and self.status is not Status.ESCALATED:
            raise InvalidConcernError(
                "record an escalation (external referral needed) before resolving as referred",
                code="CONCERN_NOT_ESCALATED",
                field="outcome",
            )
        if self.acknowledged_at is None:
            self.acknowledged_at = now
            self.acknowledged_by = actor_ref
        self.status = Status.RESOLVED
        self.resolved_at = now
        self.resolved_by = actor_ref
        self.outcome = result

    # --------------------------------------------------------------------------------- SLA

    def age(self, now: float) -> float:
        return max(0.0, now - self.created_at)

    def overdue(self, sla: SlaPolicy, now: float) -> bool | None:
        """``None`` when no threshold is configured for this tier (nothing can be overdue)."""
        threshold = sla.acknowledge_within(self.priority)
        if threshold is None:
            return None
        return self.status is Status.OPEN and self.age(now) > threshold


def new_note(*, concern_id: str, author_ref: str, body: str, now: float) -> Note:
    text = clean_text(body, limit=MAX_NOTE, field_name="body")
    if text is None:
        raise InvalidConcernError("a note needs some text", field="body")
    return Note(
        note_id=f"sgn_{uuid7()}",
        concern_id=concern_id,
        author_ref=author_ref,
        body=text,
        created_at=now,
    )


SLA_DECISION = "SLA not set — owner decision FD-06"


@dataclass(frozen=True)
class SlaPolicy:
    """Per-tier "acknowledge within N seconds". Every tier starts UNSET (``None``).

    Configured by ``TALEEM_SAFEGUARDING_ACK_SLA_SECONDS`` as a JSON object, e.g.
    ``{"T1": 1800}``. A tier that is not listed stays unset. No value is ever defaulted here: the
    numbers in doc 52 §2 are planning assumptions awaiting clinical sign-off (FD-06).
    """

    thresholds: Mapping[Priority, float | None] = field(
        default_factory=lambda: dict.fromkeys(Priority)
    )

    def acknowledge_within(self, priority: Priority) -> float | None:
        return self.thresholds.get(priority)

    @property
    def configured(self) -> bool:
        return any(v is not None for v in self.thresholds.values())

    @property
    def fully_configured(self) -> bool:
        return all(self.thresholds.get(p) is not None for p in Priority)

    def describe(self) -> dict[str, object]:
        return {
            "configured": self.configured,
            "acknowledge_within_seconds": {p.value: self.thresholds.get(p) for p in Priority},
            "notice": None if self.fully_configured else SLA_DECISION,
        }

    @classmethod
    def from_json(cls, raw: str) -> SlaPolicy:
        if not raw.strip():
            return cls()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InvalidConcernError(f"safeguarding SLA is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise InvalidConcernError("safeguarding SLA must be a JSON object of tier -> seconds")
        thresholds: dict[Priority, float | None] = dict.fromkeys(Priority)
        for key, value in data.items():
            try:
                tier = Priority(str(key))
            except ValueError:
                raise InvalidConcernError(f"unknown safeguarding SLA tier: {key}") from None
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise InvalidConcernError(f"SLA for {key} must be a positive number of seconds")
            thresholds[tier] = float(value)
        return cls(thresholds=thresholds)
