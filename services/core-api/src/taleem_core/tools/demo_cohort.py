"""Seed the in-app DEMO COHORT on the real deployment (DEMO_COHORT_CONTRACT.md — binding).

The owner explores the real application with designated synthetic demo accounts. There is no
separate demo site or database: this seeder writes, into the deployment's own database, **only**

- lessons whose ``metadata.audience`` is ``demo`` (visible to demo-cohort accounts only),
- the two reserved synthetic families (``@example.org``, a reserved domain no real person holds),
  flagged ``cohort = "demo"``, plus a demo-cohort teacher in its own organization, and
- those accounts' learning records (sessions, placement, homework, report cards).

That is why it may run in **every** environment, production included (contract §5): it relaxes no
safeguard and touches nothing real. The generic fixture seeder (``e2e_journey``) still refuses
production. The Vercel build runs this when ``TALEEM_DEMO_SEED=1`` (``scripts/vercel_migrate.py``).

Everything is written through the **application services** over the SQL units of work, composed as
``main.py`` composes them (real workflow gates, real hashing, the real scorer and knowledge model,
real homework marking and system report-card issuance), and the whole run reads as the demo cohort
(``platform.cohort.reading_as``). The cohort flag itself is set through
``IdentityService.assign_family_cohort`` / ``SchoolService.assign_teacher_cohort`` — application
methods that no HTTP route exposes.

What it seeds (all labelled synthetic):

1. **Curriculum.** 12 Grade 4 lessons (2 per subject) built exactly as ``curriculum_ingest`` merges
   the human design-document content with the AI drafts, ``audience = "demo"``, titled
   ``[DEMO · unreviewed AI draft] …`` in both locales and tagged ``demo:unreviewed``. Assets that do
   not exist get ``demo-placeholder/`` refs (accepted on demo-audience lessons only). Every review
   stage is recorded as ``SYNTHETIC DEMO APPROVAL - not a human review``.
2. **Accounts.** It **adopts** the existing ``taleem.demo.guardian@example.org`` (and its learner
   "Demo Learner") by flagging the family ``demo`` — its passphrase and PIN are never changed. Only
   if the guardian or learner is absent is it created, which then needs
   ``TALEEM_DEMO_GUARDIAN_PASSPHRASE`` / ``TALEEM_DEMO_LEARNER_PIN`` (refused if unset). A second
   family, ``taleem.demo.family.b@example.org``, exists for isolation checks. Consent: learning
   data, progress sharing, AI teaching.
3. **Learning history** on 8 lessons, on fixed dates between 2026-09-01 and 2026-10-20: placement,
   then sessions with a fixed mix of right and wrong answers (mastered, developing, a misconception
   detected and remediated, one lesson left in progress).
4. **School.** "Taleem Demo School (synthetic)" with a demo-cohort teacher, one class,
   assignments, written homework marked ``met`` / ``not_yet``, one returned for another try, one
   awaiting marking.
5. **Report cards.** System-issued cards for September and 1-15 October 2026 (one acknowledged).

Deterministic and idempotent: every timestamp comes from a fixed clock on the dates above, every
answer from a fixed script, and every object is looked up before it is created, so a re-run changes
nothing. It prints **counts only** — never a secret, a ref or the database URL.

``--erase`` (contract §6) erases every demo-cohort learner through the privacy erasure path, removes
the demo guardians, suspends the demo teacher and unpublishes (archives) every demo lesson.

    TALEEM_DATABASE_URL=... python -m taleem_core.tools.demo_cohort [--erase]
"""

from __future__ import annotations

import argparse
import copy
import os
import secrets
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import Any

from ..contexts.curriculum_studio.domain.audio import DEMO_PLACEHOLDER_PREFIX
from ..contexts.curriculum_studio.domain.content import Locale, LocalizedText, MediaRef
from ..contexts.curriculum_studio.domain.lesson import Lesson
from ..contexts.curriculum_studio.domain.versioning import VersionHistory
from ..contexts.curriculum_studio.domain.workflow import (
    STATE_ROLE,
    ReviewAction,
    Workflow,
    WorkflowState,
)
from ..contexts.identity.domain.consent import ConsentEvidence, ConsentScope
from ..contexts.identity.domain.credentials import SecretHasher, WeakSecretError, assert_pin_policy
from ..contexts.learning.domain.curriculum_view import CHOOSE, FILL, ORDER, ItemView, LessonView
from ..contexts.learning.domain.decision import Decision, DecisionKind
from ..contexts.learning.domain.scorer import Answer
from ..contexts.learning.domain.session import SessionState
from ..contexts.learning.domain.values import InteractionContext
from ..platform.cohort import DEMO, reading_as
from ..platform.errors import Problem

# --------------------------------------------------------------------------------- constants

DEMO_AUDIENCE = DEMO
DEMO_TITLE_PREFIX = "[DEMO · unreviewed AI draft] "
DEMO_TAG = "demo:unreviewed"
DEMO_PROVENANCE_TAG = "demo:provenance:ai-draft+design-docs"
DEMO_LESSON_PREFIX = "DEMO-"
PLACEHOLDER = DEMO_PLACEHOLDER_PREFIX
SYNTHETIC_APPROVAL = "SYNTHETIC DEMO APPROVAL - not a human review"
PROVENANCE_NOTE = (
    "DEMO provenance: AI-drafted, UNREVIEWED lesson text merged with the human-authored Grade 4 "
    "design-document content exactly as curriculum_ingest merges it; visuals, recorded audio and "
    "the offline package are synthetic demo-placeholder refs; all review stages are synthetic."
)
ATTESTATION = "Synthetic demo account for product exploration. Not a real child."

GUARDIAN_EMAIL = "taleem.demo.guardian@example.org"
GUARDIAN_NAME = "Demo Guardian (synthetic)"
LEARNER_NAME = "Demo Learner"
GUARDIAN_B_EMAIL = "taleem.demo.family.b@example.org"
GUARDIAN_B_NAME = "Demo Family B (synthetic)"
LEARNER_B_NAME = "Demo Learner B"
TEACHER_EMAIL = "taleem.demo.teacher@example.org"
TEACHER_NAME = "Demo Teacher (synthetic)"
ORGANIZATION_NAME = "Taleem Demo School (synthetic)"
CLASS_NAME = "Grade 4 · Demo class (synthetic)"
# Every address the seeder may flag: the reserved ``example.org`` domain only (contract §2).
RESERVED_DOMAIN = "@example.org"

ENV_PASSPHRASE = "TALEEM_DEMO_GUARDIAN_PASSPHRASE"  # noqa: S105 (an env var name)
ENV_PIN = "TALEEM_DEMO_LEARNER_PIN"
# Optional: without them family B and the teacher get random, unrecoverable credentials (the data
# is still seeded; nobody can sign in as them).
ENV_PASSPHRASE_B = "TALEEM_DEMO_GUARDIAN_B_PASSPHRASE"  # noqa: S105
ENV_PIN_B = "TALEEM_DEMO_LEARNER_B_PIN"
ENV_TEACHER_PASSPHRASE = "TALEEM_DEMO_TEACHER_PASSPHRASE"  # noqa: S105

# Two lessons per Grade 4 subject. Between them: fill, order, match and sort activities.
DEMO_OBJECTIVES: tuple[str, ...] = (
    "MATH-G4-NB-01",
    "MATH-G4-GE-01",
    "URD-G4-RD-01",
    "URD-G4-RD-02",
    "ENG-G4-RD-01",
    "ENG-G4-RD-02",
    "SCI-G4-MAT-01",
    "SCI-G4-LIV-01",
    "SOC-G4-GEO-01",
    "SOC-G4-CTY-02",
    "ISL-G4-IBA-01",
    "ETH-G4-HON-01",
)

ANCHOR = datetime(2026, 9, 1, tzinfo=UTC).timestamp()  # day 0 of the demo calendar
DAY = 86_400.0


def at(day: int, hour: int = 9, minute: int = 0) -> float:
    """A fixed demo timestamp: ``day`` days after 2026-09-01, at ``hour:minute`` UTC."""
    return ANCHOR + day * DAY + hour * 3600.0 + minute * 60.0


SEPTEMBER = (int(at(0, 0)), int(at(30, 0)))  # 2026-09-01 .. 2026-10-01 (end exclusive)
EARLY_OCTOBER = (int(at(30, 0)), int(at(45, 0)))  # 2026-10-01 .. 2026-10-16


# --------------------------------------------------------------------------------- the script


@dataclass(frozen=True)
class SessionStep:
    """One learning session. ``answers``: ``C`` right / ``W`` wrong on the next item in lesson
    order; ``M`` the lesson's misconception item answered with its misconception; ``R`` that item
    answered correctly. ``ends=False`` leaves the session open (a lesson in progress)."""

    at: float
    objective: str
    answers: str
    kind: DecisionKind = DecisionKind.CONTINUE
    ends: bool = True


SESSIONS: tuple[SessionStep, ...] = (
    SessionStep(at(1, 16), "MATH-G4-NB-01", "CCWCCCC"),
    SessionStep(at(2, 16), "URD-G4-RD-01", "CCCWCCCC"),
    SessionStep(at(3, 16), "ENG-G4-RD-01", "CCCCCCC"),
    SessionStep(at(8, 16), "MATH-G4-NB-01", "CCCCCCC"),
    SessionStep(at(9, 16), "URD-G4-RD-01", "CCCCCCCC"),
    SessionStep(at(10, 16), "ENG-G4-RD-01", "CCCCCCC"),
    SessionStep(at(14, 16), "SCI-G4-MAT-01", "CWCWCWC"),
    SessionStep(at(16, 16), "SOC-G4-GEO-01", "CMCWC"),  # misconception suspected
    SessionStep(at(21, 16), "MATH-G4-GE-01", "CWWCWC"),
    SessionStep(at(23, 16), "SOC-G4-GEO-01", "MRCRC", DecisionKind.REMEDIATE),  # confirmed, cleared
    SessionStep(at(30, 16), "ISL-G4-IBA-01", "CCCCCCC"),
    SessionStep(at(35, 16), "SCI-G4-MAT-01", "CCWCCW"),
    SessionStep(at(37, 16), "SOC-G4-GEO-01", "CCCCCCC"),
    SessionStep(at(42, 16), "ISL-G4-IBA-01", "CCCCCCC"),
    SessionStep(at(43, 16), "MATH-G4-NB-01", "CCCCCCC", DecisionKind.REVIEW),
    SessionStep(at(48, 16), "URD-G4-RD-02", "CW", ends=False),  # left in progress
)


@dataclass(frozen=True)
class Homework:
    """An assignment and what happens to the learner's written answer.

    ``result``: ``met`` / ``not_yet`` (marked), ``returned`` (sent back), ``submitted`` (awaiting
    marking) or ``""`` (assigned, not started)."""

    objective: str
    assigned: float
    due: float
    submitted: float | None = None
    reviewed: float | None = None
    result: str = ""
    feedback: str = ""


HOMEWORK: tuple[Homework, ...] = (
    Homework(
        "MATH-G4-NB-01",
        at(1, 8),
        at(8, 18),
        at(3, 17),
        at(4, 10),
        "met",
        "[DEMO] Clear and complete - well done. (synthetic teacher feedback)",
    ),
    Homework(
        "SCI-G4-MAT-01",
        at(13, 8),
        at(20, 18),
        at(15, 17),
        at(16, 10),
        "not_yet",
        "[DEMO] A good start; say which material and why. (synthetic teacher feedback)",
    ),
    Homework(
        "MATH-G4-GE-01",
        at(20, 8),
        at(27, 18),
        at(22, 17),
        at(23, 10),
        "returned",
        "[DEMO] Please try again and add one example. (synthetic teacher feedback)",
    ),
    Homework(
        "ISL-G4-IBA-01",
        at(29, 8),
        at(36, 18),
        at(31, 17),
        at(32, 10),
        "met",
        "[DEMO] Thoughtful answer. (synthetic teacher feedback)",
    ),
    Homework("SOC-G4-GEO-01", at(36, 8), at(46, 18), at(45, 17), None, "submitted"),
    Homework("ENG-G4-RD-02", at(44, 8), at(51, 18)),
)
SUBMISSION_TEXT = "[DEMO] Synthetic written answer by a demo learner - not a real child's work."

PLACEMENT_AT = at(0, 18)
PLACEMENT_MAX_ANSWERS = 40


# --------------------------------------------------------------------------------- errors


class DemoSeedRefusedError(RuntimeError):
    """A required secret is missing, or the target is not a demo-cohort account."""


class DemoSeedError(RuntimeError):
    """The seed could not be completed (content or service behaved unexpectedly)."""


# --------------------------------------------------------------------------------- secrets


@dataclass(frozen=True)
class DemoSecrets:
    """Credentials used ONLY when an account has to be created. ``None`` = not supplied: creating
    the demo guardian or learner is then refused; family B and the teacher get random,
    unrecoverable credentials. An adopted account's credentials are never touched."""

    guardian_passphrase: str | None = None
    learner_pin: str | None = None
    guardian_b_passphrase: str | None = None
    learner_b_pin: str | None = None
    teacher_passphrase: str | None = None


def _random_pin() -> str:
    while True:
        pin = f"{secrets.randbelow(10**6):06d}"
        try:
            assert_pin_policy(pin)
        except WeakSecretError:
            continue
        return pin


def secrets_from(env: Mapping[str, str]) -> DemoSecrets:
    def get(name: str) -> str | None:
        value = env.get(name, "")
        return value if value.strip() else None

    pin, pin_b = get(ENV_PIN), get(ENV_PIN_B)
    return DemoSecrets(
        guardian_passphrase=get(ENV_PASSPHRASE),
        learner_pin=pin.strip() if pin else None,
        guardian_b_passphrase=get(ENV_PASSPHRASE_B),
        learner_b_pin=pin_b.strip() if pin_b else None,
        teacher_passphrase=get(ENV_TEACHER_PASSPHRASE),
    )


def _require(value: str | None, env_name: str, what: str) -> str:
    if value is None:
        raise DemoSeedRefusedError(f"{env_name} is unset; it is needed to create {what}")
    return value


# --------------------------------------------------------------------------------- composition


class DemoClock:
    """The seed's only clock: set to a fixed demo time; each read advances it by one second so
    every record in a step keeps a strict order."""

    def __init__(self, start: float = ANCHOR) -> None:
        self._now = start

    def set(self, t: float) -> None:
        self._now = t

    def peek(self) -> float:
        return self._now

    def __call__(self) -> float:
        now = self._now
        self._now += 1.0
        return now


class _FrozenCurriculum:
    """The real learning read model, memoised. The seed publishes all curriculum first and changes
    none afterwards, so every later lookup can reuse the first answer (the read model otherwise
    re-reads and re-deserialises every published lesson on each call). ``clear`` after publishing.
    """

    _CACHED = frozenset(
        {"lesson_for", "published_graph", "published_catalog", "published_versions"}
    )

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._memo: dict[tuple[str, tuple[Any, ...]], Any] = {}

    def clear(self) -> None:
        self._memo.clear()

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._inner, name)
        if name not in self._CACHED:
            return target

        def cached(*args: Any) -> Any:
            key = (name, args)
            if key not in self._memo:
                self._memo[key] = target(*args)
            return self._memo[key]

        return cached


@dataclass
class _Stack:
    """The application services, composed over the SQL units of work as ``main.py`` does."""

    clock: DemoClock
    production: bool
    studio_sf: Any
    identity_sf: Any
    school_sf: Any
    learning_sf: Any
    reporting_sf: Any
    safeguarding_sf: Any
    identity: Any
    knowledge: Any
    read_model: Any
    sessions: Any
    placement: Any
    school: Any
    reporting: Any
    engines: list[Any] = field(default_factory=list)

    @contextmanager
    def studio(self) -> Iterator[Any]:
        from ..contexts.curriculum_studio.adapters.persistence import (
            studio_audio_resolver,
            unit_of_work,
        )
        from ..contexts.curriculum_studio.application.service import CurriculumStudioService

        with unit_of_work(self.studio_sf) as uow:
            yield CurriculumStudioService(
                uow.lessons,
                uow.publish,
                clock=self.clock,
                on_commit=uow.commit,
                audio_assets=studio_audio_resolver(uow.audio_assets, production=self.production),
                hierarchy=uow.hierarchy,
            )

    def dispose(self) -> None:
        for engine in self.engines:
            engine.dispose()


def build_stack(url: str, *, clock: DemoClock, hasher: SecretHasher, production: bool) -> _Stack:
    from ..contexts.curriculum_studio.adapters.persistence import Base as CurriculumBase
    from ..contexts.curriculum_studio.adapters.persistence import (
        create_db_engine,
        create_session_factory,
    )
    from ..contexts.identity.adapters.persistence.base import (
        IdentityBase,
        create_identity_engine,
        create_identity_session_factory,
    )
    from ..contexts.identity.adapters.persistence.uow import SqlIdentityUnitOfWork
    from ..contexts.identity.application.identity_service import IdentityService
    from ..contexts.identity.application.tokens import TokenIssuer
    from ..contexts.identity.domain.consent import derive_state
    from ..contexts.learning.adapters.curriculum_read_model import CurriculumStudioReadModel
    from ..contexts.learning.adapters.memory import InMemorySessionRepository
    from ..contexts.learning.adapters.persistence.base import (
        LearningBase,
        create_learning_engine,
        create_learning_session_factory,
    )
    from ..contexts.learning.adapters.persistence.uow import LearningUnitOfWork
    from ..contexts.learning.application.knowledge_service import KnowledgeService
    from ..contexts.learning.application.placement_service import PlacementService
    from ..contexts.learning.application.report_records import LearnerRecordsService
    from ..contexts.learning.application.session_service import SessionService
    from ..contexts.learning.application.written_work import WrittenWorkService
    from ..contexts.learning.domain.decision import DecisionConfig
    from ..contexts.learning.domain.estimator import BKTEstimator
    from ..contexts.learning.domain.forgetting import HalfLifeForgettingModel
    from ..contexts.learning.domain.runtime import TemplatedTeachingRuntime
    from ..contexts.reporting.adapters.context_ports import (
        CallableLearnerDirectory,
        CallableLearningRecords,
        CallablePublishedLessons,
        CallableSchoolDirectory,
    )
    from ..contexts.reporting.adapters.persistence.base import (
        ReportingBase,
        create_reporting_session_factory,
        reporting_engine_sharing,
    )
    from ..contexts.reporting.adapters.persistence.uow import SqlReportingUnitOfWork
    from ..contexts.reporting.application.service import ReportingService
    from ..contexts.safeguarding.adapters.persistence.base import (
        SafeguardingBase,
        create_safeguarding_session_factory,
        safeguarding_engine_sharing,
    )
    from ..contexts.school.adapters.audit_log import SqlSchoolAuditLog
    from ..contexts.school.adapters.context_ports import (
        CallablePublishedCurriculum,
        CallableSharingConsent,
        CallableWrittenWork,
        IdentityLearnerDirectory,
        KnowledgeProgressReader,
    )
    from ..contexts.school.adapters.persistence.base import (
        SchoolBase,
        create_school_session_factory,
        school_engine_sharing,
    )
    from ..contexts.school.adapters.persistence.uow import SqlSchoolUnitOfWork
    from ..contexts.school.application.school_service import SchoolService
    from ..platform.config import Settings

    settings = Settings()
    curriculum_engine = create_db_engine(url)
    learning_engine = create_learning_engine(url)
    identity_engine = create_identity_engine(url)
    school_engine = school_engine_sharing(identity_engine)
    safeguarding_engine = safeguarding_engine_sharing(identity_engine)
    reporting_engine = reporting_engine_sharing(identity_engine)
    if curriculum_engine.dialect.name == "sqlite":  # dev/test; PostgreSQL uses the migrations
        CurriculumBase.metadata.create_all(curriculum_engine)
        LearningBase.metadata.create_all(learning_engine)
        IdentityBase.metadata.create_all(identity_engine)
        SchoolBase.metadata.create_all(school_engine)
        SafeguardingBase.metadata.create_all(safeguarding_engine)
        ReportingBase.metadata.create_all(reporting_engine)
    studio_sf = create_session_factory(curriculum_engine)
    learning_sf = create_learning_session_factory(learning_engine)
    identity_sf = create_identity_session_factory(identity_engine)
    school_sf = create_school_session_factory(school_engine)
    safeguarding_sf = create_safeguarding_session_factory(safeguarding_engine)
    reporting_sf = create_reporting_session_factory(reporting_engine)

    # Tokens minted while seeding are discarded: a per-run random HS256 key, never persisted.
    issuer = TokenIssuer(
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        hs256_secret=secrets.token_hex(32),
    )
    identity = IdentityService(lambda: SqlIdentityUnitOfWork(identity_sf), issuer, clock, hasher)

    def learner_lookup(student_ref: str) -> Any:
        with SqlIdentityUnitOfWork(identity_sf) as uow:
            return uow.learners.get(student_ref)

    def learning_refusal(student_ref: str) -> str | None:
        account = learner_lookup(student_ref)
        if account is None or not account.can_sign_in:
            return "inactive"
        state = identity.consent_state_for(student_ref)
        return None if state.allows(ConsentScope.LEARNING_DATA) else "consent_withdrawn"

    def sharing_allowed(student_ref: str) -> bool:
        return bool(identity.consent_state_for(student_ref).allows(ConsentScope.PROGRESS_SHARING))

    def learning_uow() -> LearningUnitOfWork:
        return LearningUnitOfWork(learning_sf)

    knowledge = KnowledgeService(learning_uow, BKTEstimator(), HalfLifeForgettingModel(), clock)
    read_model = _FrozenCurriculum(CurriculumStudioReadModel(studio_sf))
    sessions = SessionService(
        InMemorySessionRepository(),
        knowledge,
        read_model,
        TemplatedTeachingRuntime(),
        read_model.published_graph,
        DecisionConfig(),
        clock,
        learning_uow,
    )
    placement = PlacementService(learning_uow, read_model, read_model.published_graph, clock)
    written = WrittenWorkService(read_model, knowledge)

    def grant_class_sharing(guardian_ref: str, student_ref: str, attestation: str) -> object:
        return identity.grant_consent(
            guardian_ref=guardian_ref,
            student_ref=student_ref,
            scopes={ConsentScope.LEARNING_DATA, ConsentScope.PROGRESS_SHARING},
            evidence=ConsentEvidence(method="class_join", attestation=attestation),
        )

    school = SchoolService(
        lambda: SqlSchoolUnitOfWork(school_sf),
        hasher=hasher,
        issue_token=lambda *, teacher_ref, now: {},  # no teacher session is opened by the seed
        learners=IdentityLearnerDirectory(
            learner_lookup=learner_lookup,
            learner_refusal=learning_refusal,
            sharing_allowed=sharing_allowed,
        ),
        sharing_consent=CallableSharingConsent(grant_class_sharing),
        progress=KnowledgeProgressReader(
            knowledge.snapshot,
            progress_many=lambda refs, code, since: knowledge.objective_progress(
                refs, code, since=since
            ),
        ),
        curriculum=CallablePublishedCurriculum(read_model.lesson_for, read_model.published_catalog),
        audit=SqlSchoolAuditLog(school_sf),
        clock=clock,
        written=CallableWrittenWork(written.written_lesson, written.record_marked),
    )

    def guardian_of(student_ref: str) -> str | None:
        account = learner_lookup(student_ref)
        return str(account.guardian_ref) if account is not None else None

    def teacher_visibility(student_refs: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        with SqlIdentityUnitOfWork(identity_sf) as uow:
            for ref in student_refs:
                account = uow.learners.get(ref)
                if account is None:
                    out[ref] = {"display_name": None, "reason": "inactive"}
                    continue
                state = derive_state(ref, uow.consents.history(ref))
                ok = state.allows(ConsentScope.PROGRESS_SHARING) and state.permits_sign_in
                out[ref] = {
                    "display_name": str(account.display_name),
                    "reason": None if ok else "consent_withdrawn",
                }
        return out

    def learner_status(student_ref: str) -> dict[str, Any] | None:
        account = learner_lookup(student_ref)
        if account is None:
            return None
        return {"display_name": str(account.display_name), "refusal": learning_refusal(student_ref)}

    records = LearnerRecordsService(learning_uow)
    reporting = ReportingService(
        lambda: SqlReportingUnitOfWork(reporting_sf, clock),
        school=CallableSchoolDirectory(
            lambda teacher_ref, class_id: school.reporting_roster(
                teacher_ref=teacher_ref, class_id=class_id
            ),
            school.reporting_rosters,
            school.marked_homework,
        ),
        learners=CallableLearnerDirectory(guardian_of, teacher_visibility, learner_status),
        records=CallableLearningRecords(records.records),
        lessons=CallablePublishedLessons(read_model.published_versions),
        clock=clock,
    )
    return _Stack(
        clock=clock,
        production=production,
        studio_sf=studio_sf,
        identity_sf=identity_sf,
        school_sf=school_sf,
        learning_sf=learning_sf,
        reporting_sf=reporting_sf,
        safeguarding_sf=safeguarding_sf,
        identity=identity,
        knowledge=knowledge,
        read_model=read_model,
        sessions=sessions,
        placement=placement,
        school=school,
        reporting=reporting,
        engines=[curriculum_engine, learning_engine, identity_engine],
    )


# --------------------------------------------------------------------------------- 1. curriculum


def merged_lessons(codes: Sequence[str] = DEMO_OBJECTIVES) -> tuple[Any, dict[str, Lesson]]:
    """(spine, objective code -> the lesson ``curriculum_ingest`` builds for it).

    The ingest's own full run (design documents + FR-01 fixture + AI drafts) against an in-memory
    Studio, so the merge is exactly the ingest's."""
    from .curriculum_ai_drafts import load_drafts
    from .curriculum_ingest import DEFAULT_ROOT, generate_service, load_inputs

    spine, contents = load_inputs(DEFAULT_ROOT)
    drafts = load_drafts(DEFAULT_ROOT, spine)
    service, ids = generate_service(spine, contents, drafts)
    missing = [c for c in codes if c not in ids]
    if missing:
        raise DemoSeedError(f"objectives not in the Grade 4 spine: {missing}")
    return spine, {code: service.get(ids[code]) for code in codes}


def demo_lesson(merged: Lesson, code: str) -> Lesson:
    """The merged lesson, relabelled as an unreviewed demo draft with synthetic placeholders."""
    lesson = copy.deepcopy(merged)
    lesson.lesson_id = DEMO_LESSON_PREFIX + merged.lesson_id
    lesson.title = LocalizedText(
        text={
            loc: DEMO_TITLE_PREFIX + (lesson.title.text.get(loc, "") or code)
            for loc in (Locale.UR, Locale.EN)
        },
        audio_ref=dict(lesson.title.audio_ref),
    )
    lesson.metadata.audience = DEMO_AUDIENCE  # visible to the demo cohort only (contract §3)
    for tag in (DEMO_TAG, DEMO_PROVENANCE_TAG):
        if tag not in lesson.metadata.tags:
            lesson.metadata.tags.append(tag)
    if not lesson.visual_concepts:
        lesson.visual_concepts = [
            MediaRef(
                media_id=f"{PLACEHOLDER}visual/{code}",
                kind="svg",
                alt_text=LocalizedText(
                    text={
                        Locale.UR: "مصنوعی ڈیمو جگہ: ابھی کوئی اصل تصویر موجود نہیں۔",
                        Locale.EN: "Synthetic demo placeholder: no real illustration exists yet.",
                    }
                ),
            )
        ]
    if not lesson.offline_package.strip():
        lesson.offline_package = f"{PLACEHOLDER}offline/{code}"
    for loc in (Locale.UR, Locale.EN):
        if lesson.student_explanation.text.get(
            loc
        ) and not lesson.student_explanation.audio_ref.get(loc):
            lesson.student_explanation.audio_ref[loc] = f"{PLACEHOLDER}audio/{code}/{loc}.mp3"
    lesson.workflow = Workflow()
    lesson.quality_gate_results = []
    lesson.version = 0
    lesson.version_history = VersionHistory()
    return lesson


def _publish_through_workflow(stack: _Stack, lesson: Lesson) -> str:
    """Create (if absent) and walk the lesson to published; resumes a partial earlier run."""
    with stack.studio() as studio:
        existing = studio.find(lesson.lesson_id)
        if existing is not None and existing.workflow.state is WorkflowState.PUBLISHED:
            return "already-present"
        if existing is None:
            # The seeder writes no shared curriculum data (contract §5), so it does not store the
            # hierarchy: a lesson keeps its chapter/topic only if the stored hierarchy has them.
            if studio.placement_errors(lesson):
                lesson.metadata.chapter_key = ""
                lesson.metadata.topic_key = ""
            studio.create(lesson)
    for _ in range(len(STATE_ROLE) + 3):
        with stack.studio() as studio:
            current = studio.get(lesson.lesson_id)
            state = current.workflow.state
            if state is WorkflowState.PUBLISHED:
                return "published"
            if state is WorkflowState.DRAFT:
                studio.submit(
                    lesson.lesson_id, "subject_author", PROVENANCE_NOTE, "demo-seed-author"
                )
            elif state is WorkflowState.APPROVED:
                studio.publish(
                    lesson.lesson_id,
                    "curriculum_architect",
                    f"{SYNTHETIC_APPROVAL}. {PROVENANCE_NOTE}",
                    "demo-seed-publisher",
                )
            elif state in STATE_ROLE:
                role = STATE_ROLE[state]
                studio.review(
                    lesson.lesson_id,
                    ReviewAction.APPROVE,
                    role,
                    SYNTHETIC_APPROVAL,
                    f"demo-seed-{role}",
                )
            else:
                raise DemoSeedError(f"{lesson.lesson_id} is in state {state.value}; not seeding it")
    raise DemoSeedError(f"{lesson.lesson_id} did not reach published")


def seed_curriculum(stack: _Stack, summary: dict[str, int]) -> None:
    stack.clock.set(at(0, 8))
    with stack.studio() as studio:
        present = {
            code
            for code in DEMO_OBJECTIVES
            if (found := studio.find(_demo_lesson_id(code))) is not None
            and found.workflow.state is WorkflowState.PUBLISHED
        }
    if len(present) == len(DEMO_OBJECTIVES):  # a re-run: skip building the merged content
        summary["lessons_already_present"] += len(present)
    else:
        _, merged = merged_lessons()
        for code in DEMO_OBJECTIVES:
            result = _publish_through_workflow(stack, demo_lesson(merged[code], code))
            key = "lessons_published" if result == "published" else "lessons_already_present"
            summary[key] += 1
    stack.read_model.clear()  # nothing is published after this point


_DEMO_IDS: dict[str, str] = {}


def _demo_lesson_id(code: str) -> str:
    """The demo lesson id for an objective: ``DEMO-`` + the id the ingest gives that lesson."""
    if not _DEMO_IDS:
        from .curriculum_ingest import DEFAULT_ROOT, load_inputs

        spine, _ = load_inputs(DEFAULT_ROOT)
        _DEMO_IDS.update({o.code: DEMO_LESSON_PREFIX + o.lesson_id for o in spine.objectives})
    if code not in _DEMO_IDS:
        raise DemoSeedError(f"objective not in the Grade 4 spine: {code}")
    return _DEMO_IDS[code]


# --------------------------------------------------------------------------------- 2. accounts


@dataclass
class _Family:
    guardian_ref: str
    family_code: str
    student_ref: str


def _ensure_family(
    stack: _Stack,
    *,
    email: str,
    guardian_name: str,
    passphrase: Callable[[], str],
    learner_name: str,
    pin: Callable[[], str],
    scopes: set[ConsentScope],
    summary: dict[str, int],
) -> _Family:
    """Adopt (or, only if absent, create) a reserved synthetic family and flag it ``demo``.

    An existing account is adopted as it is: its passphrase, PIN, family code and history are never
    changed. ``passphrase`` / ``pin`` are called only to create a missing account."""
    from ..contexts.identity.adapters.persistence.uow import SqlIdentityUnitOfWork

    if not email.endswith(RESERVED_DOMAIN):  # pragma: no cover - a constant; guards edits
        raise DemoSeedRefusedError("only reserved example.org addresses may be demo accounts")
    with SqlIdentityUnitOfWork(stack.identity_sf) as uow:
        existing = uow.guardians.by_email(email)
    if existing is None:
        view = stack.identity.register_guardian(
            email=email, passphrase=passphrase(), display_name=guardian_name, locale="ur"
        )["guardian"]
        guardian_ref, family_code = str(view["guardian_ref"]), str(view["family_code"])
        summary["guardians_created"] += 1
    else:
        guardian_ref, family_code = existing.guardian_ref, existing.family_code
        summary["guardians_adopted"] += 1
    learners = stack.identity.list_learners(guardian_ref)
    learner = next((v for v in learners if v["display_name"] == learner_name), None)
    if learner is None:
        learner = stack.identity.enrol_learner(
            guardian_ref=guardian_ref, display_name=learner_name, pin=pin(), grade_level=4
        )
        summary["learners_created"] += 1
    student_ref = str(learner["student_ref"])
    # The cohort flag, through the application method no HTTP route exposes (contract §2). It
    # covers the guardian and every learner of theirs; a learner enrolled later inherits it.
    summary["accounts_flagged_demo"] += stack.identity.assign_family_cohort(
        guardian_ref=guardian_ref, cohort=DEMO
    )
    state = stack.identity.consent_state_for(student_ref)
    if not all(state.allows(s) for s in scopes):
        # Recorded after any consent the family already gave, so it is the current record.
        with SqlIdentityUnitOfWork(stack.identity_sf) as uow:
            history = uow.consents.history(student_ref)
        latest = max((r.recorded_at for r in history), default=0.0)
        stack.clock.set(max(stack.clock.peek(), latest + 1.0))
        stack.identity.grant_consent(
            guardian_ref=guardian_ref,
            student_ref=student_ref,
            scopes=scopes,
            evidence=ConsentEvidence(method="demo_seed", attestation=ATTESTATION),
        )
        summary["consents_granted"] += 1
    return _Family(guardian_ref, family_code, student_ref)


# --------------------------------------------------------------------------------- 3. learning


def correct_answer(item: ItemView) -> Answer:
    if item.kind == CHOOSE:
        return Answer(option=item.correct_option)
    if item.kind == FILL:
        return Answer(text=item.accepted_answers[0])
    if item.kind == ORDER:
        return Answer(order=item.correct_order)
    return Answer(pairs=tuple(sorted(item.correct_pairs)))


def wrong_answer(item: ItemView) -> Answer:
    """A deterministic wrong answer for any kind (a choose item's misconception option first)."""
    if item.kind == CHOOSE:
        tagged = sorted(o for o in item.option_misconceptions if o != item.correct_option)
        if tagged:
            return Answer(option=tagged[0])
        return Answer(option=(item.correct_option + 1) % max(2, len(item.options)))
    if item.kind == FILL:
        return Answer(text="demo-wrong-answer")
    if item.kind == ORDER:
        order = tuple(reversed(item.correct_order))
        if order == item.correct_order:
            order = (*item.correct_order, *item.correct_order)
        return Answer(order=order)
    pairs = sorted(item.correct_pairs)
    return Answer(pairs=tuple(pairs[:-1]))


def misconception_item(lesson: LessonView) -> ItemView:
    for item in lesson.practice_items:
        if item.kind == CHOOSE and any(
            o != item.correct_option for o in item.option_misconceptions
        ):
            return item
        if item.misconception:
            return item
    raise DemoSeedError(f"{lesson.objective_code} has no item with an authored misconception")


def _lesson(stack: _Stack, objective: str) -> LessonView:
    lesson: LessonView | None = stack.read_model.lesson_for(objective)
    if lesson is None or not lesson.practice_items:
        raise DemoSeedError(f"no published, playable lesson for {objective}")
    return lesson


def _find_item(lesson: LessonView, item_ref: str) -> ItemView | None:
    for item in (*lesson.assessment_formative, *lesson.practice_items):
        if item.item_ref == item_ref:
            return item
    return None


def seed_placement(stack: _Stack, student_ref: str, summary: dict[str, int]) -> None:
    stack.clock.set(PLACEMENT_AT)
    status = stack.placement.status(student_ref)
    answered = 0
    while status["status"] in ("available", "in_progress") and answered < PLACEMENT_MAX_ANSWERS:
        nxt = status["next_item"]
        item = _find_item(_lesson(stack, nxt["objective_code"]), nxt["item_ref"])
        if item is None:
            raise DemoSeedError(f"placement item {nxt['item_ref']} is not published")
        given = correct_answer(item) if answered % 3 != 2 else wrong_answer(item)
        status = stack.placement.answer(student_ref, item_ref=item.item_ref, answer=given)
        answered += 1
    if status["status"] != "completed":
        raise DemoSeedError(f"placement ended in status {status['status']!r}")
    summary["placement_answers"] += answered


def _session_done(stack: _Stack, student_ref: str, step: SessionStep) -> bool:
    snap = stack.knowledge.snapshot(student_ref, include_evidence=True)
    if snap is None:
        return False
    return any(
        e.objective_code == step.objective
        and e.context is not InteractionContext.DIAGNOSTIC
        and step.at <= e.occurred_at < step.at + 3600
        for e in snap.evidence
    )


def run_session(
    stack: _Stack, student_ref: str, step: SessionStep, summary: dict[str, int]
) -> None:
    if _session_done(stack, student_ref, step):
        return
    stack.clock.set(step.at)
    service = stack.sessions
    lesson = _lesson(stack, step.objective)
    session = service.start(student_ref)
    service.plan_next(session)
    if session.state is SessionState.PLANNING:
        # The planner suggested resting; the learner picked this lesson from their list instead.
        session.transition_to(SessionState.TEACHING)
    if session.state is not SessionState.TEACHING:
        raise DemoSeedError(f"session for {step.objective} is {session.state.value}")
    service.teach(session, Decision(kind=DecisionKind.TEACH, objective_code=step.objective))
    items = lesson.practice_items
    target = misconception_item(lesson) if any(c in "MR" for c in step.answers) else None
    position = 0
    for code in step.answers:
        if code in "MR" and target is not None:
            item = target
            given = wrong_answer(item) if code == "M" else correct_answer(item)
        else:
            item = items[position % len(items)]
            position += 1
            given = correct_answer(item) if code == "C" else wrong_answer(item)
        turn = service.submit_answer(
            session,
            lesson,
            item,
            answer=given,
            decision_kind=step.kind,
            hints_used=0,
            self_confidence=None,
        )
        summary["answers"] += 1
        summary["misconceptions_confirmed"] += len(turn.result.confirmed_misconceptions)
        summary["misconceptions_cleared"] += len(turn.result.cleared_misconceptions)
    if step.ends:
        service.complete_objective(session)
        service.end(session)
        summary["sessions_completed"] += 1
    else:
        summary["sessions_in_progress"] += 1


# --------------------------------------------------------------------------------- 4. school


@dataclass
class _School:
    teacher_ref: str
    class_id: str
    join_code: str


def seed_school(
    stack: _Stack, family: _Family, teacher_passphrase: Callable[[], str], summary: dict[str, int]
) -> _School:
    from ..contexts.school.adapters.persistence.uow import SqlSchoolUnitOfWork

    stack.clock.set(at(0, 11))
    with SqlSchoolUnitOfWork(stack.school_sf) as uow:  # read-only lookup (no service query)
        teacher = uow.teachers.by_email(TEACHER_EMAIL)
    if teacher is None:
        org = stack.school.create_organization(
            name=ORGANIZATION_NAME,
            country="PK",
            curriculum_pack_id="PK-NCP",
            default_locale="ur",
        )
        teacher_ref = str(
            stack.school.create_teacher(
                organization_id=org["organization_id"],
                email=TEACHER_EMAIL,
                display_name=TEACHER_NAME,
                passphrase=teacher_passphrase(),
            )["teacher_ref"]
        )
        summary["organizations_created"] += 1
        summary["teachers_created"] += 1
    else:
        teacher_ref = teacher.teacher_ref
    # The teacher is demo cohort too (joins are refused across cohorts; contract §1).
    if stack.school.assign_teacher_cohort(teacher_ref=teacher_ref, cohort=DEMO):
        summary["accounts_flagged_demo"] += 1
    classroom = next(
        (c for c in stack.school.list_classes(teacher_ref) if c["name"] == CLASS_NAME), None
    )
    if classroom is None:
        classroom = stack.school.create_class(teacher_ref=teacher_ref, name=CLASS_NAME)
        summary["classes_created"] += 1
    class_id, join_code = str(classroom["class_id"]), str(classroom["join_code"])
    joined = stack.school.child_classes(
        guardian_ref=family.guardian_ref, student_ref=family.student_ref
    )
    if not any(c.get("class_id") == class_id for c in joined):
        stack.clock.set(at(0, 12))
        stack.school.join_class(
            guardian_ref=family.guardian_ref,
            student_ref=family.student_ref,
            class_code=join_code,
            attestation=ATTESTATION,
        )
        summary["class_joins"] += 1
    return _School(teacher_ref, class_id, join_code)


def _assignment_id(stack: _Stack, school: _School, objective: str) -> str | None:
    for a in stack.school.list_assignments(
        teacher_ref=school.teacher_ref, class_id=school.class_id
    ):
        if a["objective_code"] == objective:
            return str(a["assignment_id"])
    return None


def assign(stack: _Stack, school: _School, hw: Homework, summary: dict[str, int]) -> None:
    if _assignment_id(stack, school, hw.objective) is not None:
        return
    stack.clock.set(hw.assigned)
    stack.school.create_assignment(
        teacher_ref=school.teacher_ref,
        class_id=school.class_id,
        objective_code=hw.objective,
        due_at=hw.due,
    )
    summary["assignments_created"] += 1


def _homework_item(stack: _Stack, student_ref: str, assignment_id: str) -> dict[str, Any]:
    for a in stack.school.learner_homework(student_ref)["assignments"]:
        if a["assignment_id"] == assignment_id:
            if not a["items"]:
                raise DemoSeedError(f"{a['objective_code']} has no written homework item")
            return dict(a["items"][0])
    raise DemoSeedError(f"assignment {assignment_id} is not visible to the learner")


def submit(
    stack: _Stack, school: _School, family: _Family, hw: Homework, summary: dict[str, int]
) -> None:
    assignment_id = _assignment_id(stack, school, hw.objective)
    if assignment_id is None or hw.submitted is None:
        return
    item = _homework_item(stack, family.student_ref, assignment_id)
    if item["state"] != "not_started":
        return
    stack.clock.set(hw.submitted)
    stack.school.learner_submit(
        student_ref=family.student_ref,
        assignment_id=assignment_id,
        item_ref=item["item_ref"],
        text=SUBMISSION_TEXT,
    )
    summary["submissions"] += 1


def review(
    stack: _Stack, school: _School, family: _Family, hw: Homework, summary: dict[str, int]
) -> None:
    assignment_id = _assignment_id(stack, school, hw.objective)
    if assignment_id is None or hw.reviewed is None:
        return
    queue = stack.school.class_submissions(
        teacher_ref=school.teacher_ref, class_id=school.class_id, status="submitted"
    )
    row = next(
        (
            r
            for r in queue
            if r["assignment_id"] == assignment_id and r["student_ref"] == family.student_ref
        ),
        None,
    )
    if row is None:  # already marked or returned
        return
    stack.clock.set(hw.reviewed)
    if hw.result == "returned":
        stack.school.return_submission(
            teacher_ref=school.teacher_ref, submission_id=row["submission_id"], feedback=hw.feedback
        )
        summary["submissions_returned"] += 1
        return
    rubric = row.get("rubric")
    raw = rubric.get("max_score") if isinstance(rubric, dict) else None
    max_score = raw if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0 else None
    score = None if max_score is None else (max_score if hw.result == "met" else max_score // 2)
    stack.school.mark_submission(
        teacher_ref=school.teacher_ref,
        submission_id=row["submission_id"],
        outcome=hw.result,
        score=score,
        feedback=hw.feedback,
    )
    summary["submissions_marked"] += 1


# --------------------------------------------------------------------------------- 5. reporting


def issue_card(
    stack: _Stack, student_ref: str, period: tuple[int, int], when: float, summary: dict[str, int]
) -> str:
    for card in stack.reporting.learner_cards(student_ref):
        if (card.get("period_start"), card.get("period_end")) == period and card.get(
            "issued_by"
        ) == "system":
            return str(card["card_id"])
    stack.clock.set(when)
    card = stack.reporting.issue_for_learner(student_ref, period[0], period[1])
    summary["report_cards_issued"] += 1
    return str(card["card_id"])


def acknowledge(
    stack: _Stack, guardian_ref: str, card_id: str, when: float, summary: dict[str, int]
) -> None:
    card = stack.reporting.get_card(actor_ref=guardian_ref, role="guardian", card_id=card_id)
    if card.get("acknowledged_at") is not None:
        return
    stack.clock.set(when)
    stack.reporting.acknowledge(guardian_ref=guardian_ref, card_id=card_id)
    summary["report_cards_acknowledged"] += 1


# --------------------------------------------------------------------------------- orchestration


class _Counts(dict[str, int]):
    def __missing__(self, key: str) -> int:
        return 0


def _stack_for(url: str, env: Mapping[str, str], hasher: SecretHasher | None) -> _Stack:
    from ..platform.config import Settings

    return build_stack(
        url,
        clock=DemoClock(),
        hasher=hasher or SecretHasher(iterations=Settings().kdf_iterations),
        production=env.get("TALEEM_ENV", "").strip().lower() == "production",
    )


def seed_demo(
    url: str,
    demo_secrets: DemoSecrets,
    *,
    env: Mapping[str, str] | None = None,
    hasher: SecretHasher | None = None,
) -> dict[str, int]:
    """Seed the demo cohort into ``url`` (idempotent). Returns counts (creations are 0 on a
    re-run). Runs in any environment: it writes only demo-cohort accounts, ``audience = "demo"``
    lessons and their records (contract §5)."""
    env = os.environ if env is None else env
    if not url.strip():
        raise DemoSeedRefusedError("TALEEM_DATABASE_URL is unset")
    stack = _stack_for(url, env, hasher)
    summary: dict[str, int] = _Counts()
    s = demo_secrets
    try:
        with reading_as(DEMO):  # every read below is a demo reader's
            seed_curriculum(stack, summary)
            stack.clock.set(at(0, 10))
            family_a = _ensure_family(
                stack,
                email=GUARDIAN_EMAIL,
                guardian_name=GUARDIAN_NAME,
                passphrase=lambda: _require(s.guardian_passphrase, ENV_PASSPHRASE, "the guardian"),
                learner_name=LEARNER_NAME,
                pin=lambda: _require(s.learner_pin, ENV_PIN, "the demo learner"),
                scopes={
                    ConsentScope.LEARNING_DATA,
                    ConsentScope.PROGRESS_SHARING,
                    ConsentScope.AI_TEACHING,
                },
                summary=summary,
            )
            stack.clock.set(at(0, 10, 30))
            family_b = _ensure_family(
                stack,
                email=GUARDIAN_B_EMAIL,
                guardian_name=GUARDIAN_B_NAME,
                passphrase=lambda: s.guardian_b_passphrase or secrets.token_urlsafe(24),
                learner_name=LEARNER_B_NAME,
                pin=lambda: s.learner_b_pin or _random_pin(),
                scopes={
                    ConsentScope.LEARNING_DATA,
                    ConsentScope.PROGRESS_SHARING,
                    ConsentScope.AI_TEACHING,
                },
                summary=summary,
            )
            school = seed_school(
                stack,
                family_a,
                lambda: s.teacher_passphrase or secrets.token_urlsafe(24),
                summary,
            )
            if stack.placement.status(family_a.student_ref)["status"] in (
                "available",
                "in_progress",
            ):
                seed_placement(stack, family_a.student_ref, summary)
            _run_calendar(stack, family_a, family_b, school, summary)
        summary["lessons_total"] = len(DEMO_OBJECTIVES)
        summary["learning_sessions_scripted"] = len(SESSIONS)
        summary["lessons_with_history"] = len({step.objective for step in SESSIONS})
    finally:
        stack.dispose()
    return dict(summary)


def _run_calendar(
    stack: _Stack, family_a: _Family, family_b: _Family, school: _School, summary: dict[str, int]
) -> None:
    """Sessions, homework and report cards, in date order on the fixed demo calendar."""
    timeline: list[tuple[float, int, Callable[[], None]]] = []
    for step in SESSIONS:
        timeline.append(
            (step.at, 0, partial(run_session, stack, family_a.student_ref, step, summary))
        )
    for hw in HOMEWORK:
        timeline.append((hw.assigned, 1, partial(assign, stack, school, hw, summary)))
        if hw.submitted is not None:
            timeline.append(
                (hw.submitted, 2, partial(submit, stack, school, family_a, hw, summary))
            )
        if hw.reviewed is not None:
            timeline.append((hw.reviewed, 3, partial(review, stack, school, family_a, hw, summary)))
    cards: dict[str, str] = {}

    def september() -> None:
        cards["a_sept"] = issue_card(stack, family_a.student_ref, SEPTEMBER, at(30, 6), summary)
        issue_card(stack, family_b.student_ref, SEPTEMBER, at(30, 6, 5), summary)

    def ack_september() -> None:
        acknowledge(stack, family_a.guardian_ref, cards["a_sept"], at(31, 20), summary)

    def october() -> None:
        issue_card(stack, family_a.student_ref, EARLY_OCTOBER, at(45, 6), summary)

    timeline += [(at(30, 6), 4, september), (at(31, 20), 4, ack_september)]
    timeline.append((at(45, 6), 4, october))
    for _when, _order, run in sorted(timeline, key=lambda t: (t[0], t[1])):
        run()


# --------------------------------------------------------------------------------- 6. removal


def erase_demo(
    url: str, *, env: Mapping[str, str] | None = None, hasher: SecretHasher | None = None
) -> dict[str, int]:
    """Contract §6: erase every demo-cohort account and unpublish every demo lesson.

    Each demo-cohort learner goes through the privacy erasure path (every store, identity last,
    then a verification sweep); then the demo guardians are removed, the demo teacher suspended
    (their sessions revoked) and every published ``audience = "demo"`` lesson archived. Real
    accounts and real lessons are never touched: only accounts whose stored cohort is ``demo``
    and lessons whose audience is ``demo`` are selected. Idempotent."""
    import time

    from ..contexts.identity.adapters.persistence.uow import SqlIdentityUnitOfWork
    from ..contexts.learning.adapters.memory import InMemorySessionRepository
    from ..contexts.privacy.adapters.wiring import build_privacy_service
    from ..contexts.privacy.domain import erasure
    from ..contexts.school.adapters.persistence.uow import SqlSchoolUnitOfWork
    from ..contexts.school.domain.model import TeacherStatus
    from ..contexts.sync.domain import SyncStore
    from ..ports.llm import InMemoryCostLedger

    env = os.environ if env is None else env
    if not url.strip():
        raise DemoSeedRefusedError("TALEEM_DATABASE_URL is unset")
    stack = _stack_for(url, env, hasher)
    summary: dict[str, int] = _Counts()
    try:
        privacy = build_privacy_service(
            identity_sf=stack.identity_sf,
            learning_sf=stack.learning_sf,
            school_sf=stack.school_sf,
            safeguarding_sf=stack.safeguarding_sf,
            reporting_sf=stack.reporting_sf,
            session_store=InMemorySessionRepository(),
            sync_store=SyncStore(),
            ai_ledger=InMemoryCostLedger(),
            env=env,
            production=stack.production,
            clock=time.time,
        )
        blockers = privacy.blockers()
        if blockers:
            raise DemoSeedRefusedError("erasure is blocked: " + "; ".join(blockers))
        with SqlIdentityUnitOfWork(stack.identity_sf) as uow:
            guardians = uow.guardians.in_cohort(DEMO)
            families = [
                (g.guardian_ref, [x.student_ref for x in uow.learners.for_guardian(g.guardian_ref)])
                for g in guardians
            ]
        for guardian_ref, learners in families:
            for student_ref in learners:
                with SqlIdentityUnitOfWork(stack.identity_sf) as uow:
                    learner = uow.learners.get(student_ref)
                if learner is None or learner.cohort != DEMO:
                    continue  # never anything but a demo-cohort learner
                request = erasure.new_request(student_ref, guardian_ref, time.time(), 900.0)
                privacy.erase(request)
                summary["learners_erased"] += 1
            with SqlIdentityUnitOfWork(stack.identity_sf) as uow:
                uow.refresh_tokens.revoke_all_for(guardian_ref, now=time.time())
                if uow.guardians.delete(guardian_ref):
                    summary["guardians_removed"] += 1
                uow.commit()
        with SqlSchoolUnitOfWork(stack.school_sf) as school_uow:
            teacher = school_uow.teachers.by_email(TEACHER_EMAIL)
            if (
                teacher is not None
                and teacher.cohort == DEMO
                and teacher.status is not TeacherStatus.SUSPENDED
            ):
                teacher.status = TeacherStatus.SUSPENDED
                school_uow.teachers.save(teacher)
                school_uow.commit()
                summary["teachers_suspended"] += 1
        if teacher is not None and teacher.cohort == DEMO:
            with SqlIdentityUnitOfWork(stack.identity_sf) as uow:
                summary["teacher_sessions_revoked"] += uow.refresh_tokens.revoke_all_for(
                    teacher.teacher_ref, now=time.time()
                )
                uow.commit()
        with stack.studio() as studio:
            demo_lessons = [
                x.lesson_id
                for x in studio.list()
                if x.metadata.audience == DEMO and x.workflow.state is WorkflowState.PUBLISHED
            ]
        for lesson_id in demo_lessons:
            with stack.studio() as studio:
                studio.archive(
                    lesson_id,
                    "curriculum_architect",
                    "demo cohort erased (DEMO_COHORT_CONTRACT §6)",
                    "demo-seed-erase",
                )
            summary["lessons_unpublished"] += 1
    finally:
        stack.dispose()
    return dict(summary)


# --------------------------------------------------------------------------------- entrypoints


def _print_counts(title: str, summary: Mapping[str, int]) -> None:
    print(f"[demo-cohort] {title}")
    if not summary:
        print("[demo-cohort]   (nothing to do)")
        return
    width = max(len(k) for k in summary)
    for key in sorted(summary):
        print(f"[demo-cohort]   {key.ljust(width)}  {summary[key]}")


def seed_from_environment(env: Mapping[str, str] | None = None, *, erase: bool = False) -> int:
    """Build-step / CLI entrypoint over ``TALEEM_DATABASE_URL``: 0 on success, 1 on any refusal
    or error. Prints counts only — never a secret, a ref or the database URL."""
    env = os.environ if env is None else env
    url = env.get("TALEEM_DATABASE_URL", "").strip()
    try:
        summary = erase_demo(url, env=env) if erase else seed_demo(url, secrets_from(env), env=env)
    except DemoSeedRefusedError as exc:
        print(f"refusing to seed the demo cohort: {exc}", file=sys.stderr)
        return 1
    except (DemoSeedError, Problem) as exc:
        detail = exc.detail if isinstance(exc, Problem) else str(exc)
        print(f"demo cohort seed failed: {detail}", file=sys.stderr)
        return 1
    if erase:
        _print_counts("demo cohort erased (counts):", summary)
    else:
        _print_counts("demo cohort seeded (counts; creations are 0 when already present):", summary)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="demo_cohort", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--erase",
        action="store_true",
        help="erase every demo-cohort account and unpublish every demo lesson (contract §6)",
    )
    args = parser.parse_args(argv)
    return seed_from_environment(erase=args.erase)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
