"""FastAPI adapter for Curriculum Studio (the edge; all logic is in domain/application).

Exposes the authoring lifecycle over REST. Request models are module-scope so FastAPI can
resolve body types via module globals). Governance-safe: no child data.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ....auth.dependencies import authorize
from ....auth.jwt_verifier import Claims
from ....platform.concurrency import ConcurrencyConflictError
from ....platform.errors import Problem, conflict, not_found
from ..application.service import CurriculumStudioService, StudioError
from ..domain.ai_teaching import AITeachingObject
from ..domain.assessment import AssessmentBlueprint
from ..domain.content import Locale, LocalizedText
from ..domain.hierarchy import Grade
from ..domain.lesson import Lesson, Metadata
from ..domain.packs import DEFAULT_PACK_ID, default_registry
from ..domain.provenance import Derivation, Provenance
from ..domain.workflow import ReviewAction


class ProvenanceIn(BaseModel):
    derivation: str = "authored-original"
    source: str = "authored"
    license: str = "authored-original"
    aligned_slo_codes: list[str] = Field(default_factory=list)
    permission_ref: str | None = None


class AITeachingIn(BaseModel):
    learning_goals: list[str] = Field(default_factory=list)
    teaching_strategy: str = ""
    questioning_strategy: str = ""
    hint_policy: str = ""
    escalation_rules: list[str] = Field(default_factory=list)
    forbidden_behaviours: list[str] = Field(default_factory=list)
    misconception_detectors: list[str] = Field(default_factory=list)


class LessonDraftIn(BaseModel):
    lesson_id: str = Field(min_length=1, max_length=128)
    # Localized title keyed by locale tag; every key must be a locale of the lesson's curriculum
    # pack. ``title_ur`` / ``title_en`` remain as compatibility aliases for ``title["ur"/"en"]``.
    title: dict[str, str] = Field(default_factory=dict)
    title_ur: str | None = Field(default=None, min_length=1)
    title_en: str | None = Field(default=None, min_length=1)
    grade: str
    subject: str
    # The curriculum pack and instructional locale(s) the lesson is authored against; validated by
    # the gates (an unknown pack/locale is a BLOCKER finding, not a silent pass).
    curriculum_pack: str = Field(default=DEFAULT_PACK_ID, min_length=1, max_length=64)
    instructional_locales: list[str] = Field(default_factory=list)
    learning_outcomes: list[str] = Field(default_factory=list)
    provenance: ProvenanceIn = Field(default_factory=ProvenanceIn)
    ai_teaching: AITeachingIn = Field(default_factory=AITeachingIn)


class SubmitIn(BaseModel):
    note: str = ""


class ReviewIn(BaseModel):
    action: str  # approve | request_changes
    note: str = ""


class PublishIn(BaseModel):
    change_summary: str = ""


class RollbackIn(BaseModel):
    target_version: int
    note: str = ""


def _bad_locale(detail: str) -> Problem:
    return Problem(422, "BAD_LOCALE", "Invalid locale", detail)


def _draft_title(d: LessonDraftIn) -> dict[Locale, str]:
    """The draft's title: the locale-keyed ``title`` map merged with the ``title_ur``/``title_en``
    aliases, every key checked against the lesson's curriculum pack (an unknown pack is left to
    the gates, which block it)."""
    raw: dict[str, str] = {k: v for k, v in d.title.items() if v.strip()}
    for tag, alias in (("ur", d.title_ur), ("en", d.title_en)):
        if alias is None:
            continue
        if tag in raw and raw[tag] != alias:
            raise _bad_locale(f"title[{tag!r}] conflicts with title_{tag}")
        raw[tag] = alias
    if not raw:
        raise _bad_locale("a title is required in at least one locale")
    pack = default_registry().get(d.curriculum_pack)
    title: dict[Locale, str] = {}
    for tag, text in raw.items():
        try:
            loc = Locale(tag)
        except ValueError as exc:
            raise _bad_locale(str(exc)) from exc
        if pack is not None and not pack.supports_locale(loc):
            raise _bad_locale(f"title locale {tag!r} is not a locale of pack {pack.pack_id}")
        title[loc] = text
    return title


def _draft_to_lesson(d: LessonDraftIn, author_role: str) -> Lesson:
    try:
        instructional = [Locale(t) for t in d.instructional_locales]
    except ValueError as exc:
        raise _bad_locale(str(exc)) from exc
    return Lesson(
        lesson_id=d.lesson_id,
        title=LocalizedText(text=_draft_title(d)),
        metadata=Metadata(
            grade_key=d.grade,
            subject_key=d.subject,
            author_role=author_role,
            curriculum_pack=d.curriculum_pack,
            instructional_locales=instructional,
        ),
        provenance=Provenance(
            derivation=Derivation(d.provenance.derivation),
            source=d.provenance.source,
            license=d.provenance.license,
            aligned_slo_codes=d.provenance.aligned_slo_codes,
            permission_ref=d.provenance.permission_ref,
        ),
        ai_teaching_object=AITeachingObject(
            learning_goals=d.ai_teaching.learning_goals,
            teaching_strategy=d.ai_teaching.teaching_strategy,
            questioning_strategy=d.ai_teaching.questioning_strategy,
            hint_policy=d.ai_teaching.hint_policy,
            escalation_rules=d.ai_teaching.escalation_rules,
            forbidden_behaviours=d.ai_teaching.forbidden_behaviours,
            misconception_detectors=d.ai_teaching.misconception_detectors,
        ),
        assessment=AssessmentBlueprint(),
        learning_outcomes=d.learning_outcomes,
    )


def _text(title: LocalizedText) -> dict[str, str]:
    return {str.__str__(k): v for k, v in title.text.items()}


def _grade_view(grade: Grade) -> dict[str, Any]:
    return {
        "key": grade.key,
        "subjects": [
            {
                "key": subj.key,
                "title": _text(subj.title),
                "chapters": [
                    {
                        "key": ch.key,
                        "title": _text(ch.title),
                        "topics": [{"key": t.key, "title": _text(t.title)} for t in ch.topics],
                    }
                    for ch in subj.chapters
                ],
            }
            for subj in grade.subjects
        ],
    }


def _lesson_view(lesson: Lesson) -> dict[str, Any]:
    return {
        "lesson_id": lesson.lesson_id,
        "title": _text(lesson.title),
        "grade": lesson.metadata.grade_key,
        "subject": lesson.metadata.subject_key,
        "curriculum_pack": lesson.metadata.curriculum_pack,
        "instructional_locales": [str.__str__(t) for t in lesson.metadata.instructional_locales],
        "state": lesson.workflow.state.value,
        "version": lesson.version,
        "learning_outcomes": lesson.learning_outcomes,
        "gates": [
            {"gate": g.gate.value, "passed": g.passed, "mode": g.mode}
            for g in lesson.quality_gate_results
        ],
    }


RESOURCE = "curriculum.lesson"


def build_studio_router(
    service_provider: Callable[..., Any],  # FastAPI dependency (may be a generator) → service
    claims_dependency: Callable[..., Claims],
) -> APIRouter:
    """Build the Curriculum Studio router.

    ``service_provider`` is a FastAPI dependency yielding a request-scoped service (the composition
    root binds it to a Unit of Work over the SQL persistence). ``claims_dependency`` verifies the
    bearer token; the actor's role comes from the token (CTO B1), never the request body.
    """
    router = APIRouter(prefix="/v1/studio", tags=["curriculum-studio"])

    def _guard(fn: Any) -> Any:
        try:
            return fn()
        except StudioError as exc:
            raise Problem(
                422, "STUDIO_RULE_VIOLATION", "Curriculum Studio rule violation", str(exc)
            ) from exc
        except ConcurrencyConflictError as exc:
            # Two writers raced the same lesson (e.g. a double-submitted review). Optimistic-lock
            # loser -> a retryable 409, never a 500. The client re-reads and retries.
            raise conflict("this lesson was modified concurrently; reload and retry") from exc

    @router.get("/hierarchy")
    def hierarchy(
        pack: str = Query(default=DEFAULT_PACK_ID, min_length=1, max_length=64),
        claims: Claims = Depends(claims_dependency),
        s: CurriculumStudioService = Depends(service_provider),
    ) -> dict[str, Any]:
        # The stored hierarchy when one has been persisted for the pack; otherwise the pack's
        # registry roster (grades x subjects, no chapters/topics).
        authorize(claims, "read", RESOURCE)
        found = default_registry().get(pack)
        if found is None:
            raise not_found(f"curriculum pack {pack}")
        stored = s.get_hierarchy(found.pack_id)
        if stored is not None:
            return {
                "system": found.pack_id,
                "version": found.version,
                "source": "persisted",
                "grades": [g.key for g in stored.grades],
                "subjects_by_grade": {g.key: [x.key for x in g.subjects] for g in stored.grades},
                "tree": [_grade_view(g) for g in stored.grades],
            }
        return {
            "system": found.pack_id,
            "version": found.version,
            "source": "pack",
            "grades": list(found.grade_keys),
            "subjects_by_grade": {g: list(x) for g, x in found.subject_roster.items()},
            "tree": [],
        }

    @router.get("/curriculum-packs")
    def curriculum_packs(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        # Read-only: the packs the studio can author against. Listing a pack is not a claim that
        # its curriculum is supported for learners.
        authorize(claims, "read", RESOURCE)
        return {"packs": [p.summary() for p in default_registry().packs()]}

    @router.get("/lessons")
    def list_lessons(
        claims: Claims = Depends(claims_dependency),
        s: CurriculumStudioService = Depends(service_provider),
    ) -> dict[str, Any]:
        authorize(claims, "read", RESOURCE)
        return {"lessons": [_lesson_view(x) for x in s.list()]}

    @router.post("/lessons", status_code=201)
    def create(
        body: LessonDraftIn,
        claims: Claims = Depends(claims_dependency),
        s: CurriculumStudioService = Depends(service_provider),
    ) -> dict[str, Any]:
        authorize(claims, "author", RESOURCE)
        return _lesson_view(_guard(lambda: s.create(_draft_to_lesson(body, claims.role))))

    @router.get("/lessons/{lesson_id}")
    def get(
        lesson_id: str,
        claims: Claims = Depends(claims_dependency),
        s: CurriculumStudioService = Depends(service_provider),
    ) -> dict[str, Any]:
        authorize(claims, "read", RESOURCE)
        lesson = s.find(lesson_id)
        if lesson is None:
            raise not_found(f"lesson {lesson_id}")
        return _lesson_view(lesson)

    @router.post("/lessons/{lesson_id}:validate")
    def validate(
        lesson_id: str,
        claims: Claims = Depends(claims_dependency),
        s: CurriculumStudioService = Depends(service_provider),
    ) -> dict[str, Any]:
        authorize(claims, "read", RESOURCE)
        result = _guard(lambda: s.validate(lesson_id))
        return {
            "ok": result.ok,
            "structural": [
                {"severity": f.severity.value, "message": f.message, "field": f.field}
                for f in result.structural
            ],
            "gates": [
                {
                    "gate": g.gate.value,
                    "passed": g.passed,
                    "findings": [f.message for f in g.findings],
                }
                for g in result.gate_results
            ],
        }

    @router.post("/lessons/{lesson_id}:submit")
    def submit(
        lesson_id: str,
        body: SubmitIn,
        claims: Claims = Depends(claims_dependency),
        s: CurriculumStudioService = Depends(service_provider),
    ) -> dict[str, Any]:
        authorize(claims, "author", RESOURCE)
        return _lesson_view(_guard(lambda: s.submit(lesson_id, claims.role, body.note)))

    @router.post("/lessons/{lesson_id}:review")
    def review(
        lesson_id: str,
        body: ReviewIn,
        claims: Claims = Depends(claims_dependency),
        s: CurriculumStudioService = Depends(service_provider),
    ) -> dict[str, Any]:
        authorize(claims, "review", RESOURCE)
        try:
            action = ReviewAction(body.action)
        except ValueError as exc:
            raise Problem(422, "BAD_ACTION", "Unknown review action", str(exc)) from exc
        return _lesson_view(_guard(lambda: s.review(lesson_id, action, claims.role, body.note)))

    @router.post("/lessons/{lesson_id}:publish")
    def publish(
        lesson_id: str,
        body: PublishIn,
        claims: Claims = Depends(claims_dependency),
        s: CurriculumStudioService = Depends(service_provider),
    ) -> dict[str, Any]:
        authorize(claims, "publish", RESOURCE)
        return _lesson_view(_guard(lambda: s.publish(lesson_id, claims.role, body.change_summary)))

    @router.post("/lessons/{lesson_id}:rollback")
    def rollback(
        lesson_id: str,
        body: RollbackIn,
        claims: Claims = Depends(claims_dependency),
        s: CurriculumStudioService = Depends(service_provider),
    ) -> dict[str, Any]:
        authorize(claims, "rollback", RESOURCE)
        return _lesson_view(
            _guard(lambda: s.rollback(lesson_id, body.target_version, claims.role, body.note))
        )

    @router.get("/lessons/{lesson_id}/versions")
    def versions(
        lesson_id: str,
        claims: Claims = Depends(claims_dependency),
        s: CurriculumStudioService = Depends(service_provider),
    ) -> dict[str, Any]:
        authorize(claims, "read", RESOURCE)
        lesson = s.find(lesson_id)
        if lesson is None:
            raise not_found(f"lesson {lesson_id}")
        return {
            "versions": [
                {
                    "version": v.version,
                    "content_hash": v.content_hash,
                    "change_summary": v.change_summary,
                    "author_role": v.author_role,
                }
                for v in lesson.version_history.versions
            ]
        }

    return router
