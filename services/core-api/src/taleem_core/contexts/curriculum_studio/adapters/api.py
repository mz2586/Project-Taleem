"""FastAPI adapter for Curriculum Studio (the edge; all logic is in domain/application).

Exposes the authoring lifecycle over REST. Request models are module-scope so FastAPI can
resolve body types via module globals). Governance-safe: no child data.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from ....auth.dependencies import authorize
from ....auth.jwt_verifier import Claims
from ....platform.concurrency import ConcurrencyConflictError
from ....platform.errors import Problem, conflict, not_found
from ..application.service import CurriculumStudioService, StudioError
from ..domain.ai_teaching import AITeachingObject
from ..domain.assessment import AssessmentBlueprint
from ..domain.content import Difficulty, Locale, LocalizedText
from ..domain.hierarchy import Grade
from ..domain.lesson import Lesson, Metadata
from ..domain.packs import DEFAULT_PACK_ID, default_registry
from ..domain.provenance import Derivation, Provenance
from ..domain.workflow import ReviewAction
from .views import (
    LocaleError,
    etag,
    lesson_view,
    localized_map,
    may_see_answer_keys,
    text_of,
    version_view,
)


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


# Localized prose fields a draft PATCH may set, each as a {locale: text} map.
LOCALIZED_FIELDS: tuple[str, ...] = (
    "title",
    "description",
    "teacher_script",
    "student_explanation",
    "revision_notes",
    "summary",
    "parent_notes",
    "mentor_notes",
    "accessibility_notes",
)


class LessonPatchIn(BaseModel):
    """Partial update of a DRAFT lesson. Omitted fields are unchanged.

    Localized fields merge per locale: a provided locale replaces that locale's text, an empty
    string removes it. Every locale must be one of the lesson's curriculum pack.
    """

    model_config = ConfigDict(extra="forbid")

    title: dict[str, str] | None = None
    title_ur: str | None = None  # compatibility aliases for title["ur"/"en"]
    title_en: str | None = None
    description: dict[str, str] | None = None
    teacher_script: dict[str, str] | None = None
    student_explanation: dict[str, str] | None = None
    revision_notes: dict[str, str] | None = None
    summary: dict[str, str] | None = None
    parent_notes: dict[str, str] | None = None
    mentor_notes: dict[str, str] | None = None
    accessibility_notes: dict[str, str] | None = None
    grade: str | None = Field(default=None, min_length=1)
    subject: str | None = Field(default=None, min_length=1)
    curriculum_pack: str | None = Field(default=None, min_length=1, max_length=64)
    instructional_locales: list[str] | None = None
    languages: list[str] | None = None
    learning_outcomes: list[str] | None = None
    prerequisites: list[str] | None = None
    keywords: list[str] | None = None
    tags: list[str] | None = None
    # Placement in the pack's stored hierarchy; "" clears it. Validated against the stored tree.
    chapter_key: str | None = Field(default=None, max_length=128)
    topic_key: str | None = Field(default=None, max_length=128)
    estimated_duration_min: int | None = Field(default=None, ge=1, le=600)
    difficulty: str | None = None
    offline_package: str | None = None


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
    try:
        return localized_map(raw, d.curriculum_pack, "title")
    except LocaleError as exc:
        raise _bad_locale(str(exc)) from exc


def _locales(tags: list[str]) -> list[Locale]:
    try:
        return [Locale(t) for t in tags]
    except ValueError as exc:
        raise _bad_locale(str(exc)) from exc


def _apply_patch(existing: Lesson, p: LessonPatchIn) -> Lesson:
    """A copy of ``existing`` with the patch applied (validation of content is the gates' job)."""
    lesson = copy.deepcopy(existing)
    meta = lesson.metadata
    if p.curriculum_pack is not None:
        meta.curriculum_pack = p.curriculum_pack
    if p.grade is not None:
        meta.grade_key = p.grade
    if p.subject is not None:
        meta.subject_key = p.subject
    if p.instructional_locales is not None:
        meta.instructional_locales = _locales(p.instructional_locales)
    if p.languages is not None:
        meta.languages = _locales(p.languages)
    if p.tags is not None:
        meta.tags = list(p.tags)
    if p.chapter_key is not None:
        meta.chapter_key = p.chapter_key.strip()
    if p.topic_key is not None:
        meta.topic_key = p.topic_key.strip()
    title = dict(p.title or {})
    for tag, alias in (("ur", p.title_ur), ("en", p.title_en)):
        if alias is not None:
            if tag in title and title[tag] != alias:
                raise _bad_locale(f"title[{tag!r}] conflicts with title_{tag}")
            title[tag] = alias
    patches = {name: getattr(p, name) for name in LOCALIZED_FIELDS}
    patches["title"] = title if (p.title is not None or title) else None
    for name, raw in patches.items():
        if raw is None:
            continue
        try:
            changes = localized_map(raw, meta.curriculum_pack, name)
        except LocaleError as exc:
            raise _bad_locale(str(exc)) from exc
        field: LocalizedText = getattr(lesson, name)
        for loc, text in changes.items():
            if text.strip():
                field.text[loc] = text
            else:
                field.text.pop(loc, None)
    if not any(v.strip() for v in lesson.title.text.values()):
        raise _bad_locale("a title is required in at least one locale")
    for name in ("learning_outcomes", "prerequisites", "keywords"):
        value = getattr(p, name)
        if value is not None:
            setattr(lesson, name, list(value))
    if p.estimated_duration_min is not None:
        lesson.estimated_duration_min = p.estimated_duration_min
    if p.difficulty is not None:
        try:
            lesson.difficulty = Difficulty(p.difficulty)
        except ValueError as exc:
            raise Problem(422, "BAD_DIFFICULTY", "Unknown difficulty", str(exc)) from exc
    if p.offline_package is not None:
        lesson.offline_package = p.offline_package
    return lesson


def _draft_to_lesson(d: LessonDraftIn, author_role: str, author_subject: str = "") -> Lesson:
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
            author_subject=author_subject,
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


def _grade_view(grade: Grade) -> dict[str, Any]:
    return {
        "key": grade.key,
        "subjects": [
            {
                "key": subj.key,
                "title": text_of(subj.title),
                "chapters": [
                    {
                        "key": ch.key,
                        "title": text_of(ch.title),
                        "topics": [{"key": t.key, "title": text_of(t.title)} for t in ch.topics],
                    }
                    for ch in subj.chapters
                ],
            }
            for subj in grade.subjects
        ],
    }


def _lesson_view(lesson: Lesson) -> dict[str, Any]:
    # Lists and mutation responses: content without answer keys, whatever the caller's role.
    return lesson_view(lesson, answer_keys=False)


def _etag_matches(header: str | None, current: str) -> bool:
    if header is None:
        raise Problem(
            428, "PRECONDITION_REQUIRED", "Precondition required", "send If-Match: <lesson etag>"
        )
    candidates = [c.strip().removeprefix("W/") for c in header.split(",")]
    return current in candidates


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
        lesson = _draft_to_lesson(body, claims.role, claims.sub)
        return _lesson_view(_guard(lambda: s.create(lesson)))

    @router.get("/lessons/{lesson_id}")
    def get(
        lesson_id: str,
        response: Response,
        claims: Claims = Depends(claims_dependency),
        s: CurriculumStudioService = Depends(service_provider),
    ) -> dict[str, Any]:
        authorize(claims, "read", RESOURCE)
        lesson = s.find(lesson_id)
        if lesson is None:
            raise not_found(f"lesson {lesson_id}")
        response.headers["ETag"] = etag(lesson)
        # Answer keys only here (and on a single version), and only for reviewers/architects.
        return lesson_view(lesson, answer_keys=may_see_answer_keys(claims.role))

    @router.patch("/lessons/{lesson_id}")
    def patch(
        lesson_id: str,
        body: LessonPatchIn,
        response: Response,
        if_match: str | None = Header(default=None, alias="If-Match"),
        claims: Claims = Depends(claims_dependency),
        s: CurriculumStudioService = Depends(service_provider),
    ) -> dict[str, Any]:
        # Draft edit (author role; the service refuses non-draft lessons). Optimistic locking:
        # If-Match must carry the current ETag (412 if stale, 428 if absent); a writer racing past
        # that check still loses at commit (409).
        authorize(claims, "author", RESOURCE)
        existing = s.find(lesson_id)
        if existing is None:
            raise not_found(f"lesson {lesson_id}")
        if not _etag_matches(if_match, etag(existing)):
            raise Problem(
                412,
                "PRECONDITION_FAILED",
                "Precondition failed",
                "the lesson changed since it was read; reload and retry",
            )
        updated = _apply_patch(existing, body)
        placement = s.placement_errors(updated)
        if placement:
            raise Problem(422, "BAD_PLACEMENT", "Invalid placement", "; ".join(placement))
        saved = _guard(lambda: s.update(updated))
        response.headers["ETag"] = etag(saved)
        return _lesson_view(saved)

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
        return _lesson_view(
            _guard(lambda: s.submit(lesson_id, claims.role, body.note, actor_subject=claims.sub))
        )

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
        return _lesson_view(
            _guard(
                lambda: s.review(
                    lesson_id, action, claims.role, body.note, actor_subject=claims.sub
                )
            )
        )

    @router.post("/lessons/{lesson_id}:publish")
    def publish(
        lesson_id: str,
        body: PublishIn,
        claims: Claims = Depends(claims_dependency),
        s: CurriculumStudioService = Depends(service_provider),
    ) -> dict[str, Any]:
        authorize(claims, "publish", RESOURCE)
        return _lesson_view(
            _guard(
                lambda: s.publish(
                    lesson_id, claims.role, body.change_summary, actor_subject=claims.sub
                )
            )
        )

    @router.post("/lessons/{lesson_id}:rollback")
    def rollback(
        lesson_id: str,
        body: RollbackIn,
        claims: Claims = Depends(claims_dependency),
        s: CurriculumStudioService = Depends(service_provider),
    ) -> dict[str, Any]:
        authorize(claims, "rollback", RESOURCE)
        return _lesson_view(
            _guard(
                lambda: s.rollback(
                    lesson_id,
                    body.target_version,
                    claims.role,
                    body.note,
                    actor_subject=claims.sub,
                )
            )
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
        return {"versions": [version_view(v) for v in lesson.version_history.versions]}

    @router.get("/lessons/{lesson_id}/versions/{version_no}")
    def version(
        lesson_id: str,
        version_no: int,
        claims: Claims = Depends(claims_dependency),
        s: CurriculumStudioService = Depends(service_provider),
    ) -> Any:
        # One published version with its lesson body, for diffing. Same answer-key rule as GET.
        authorize(claims, "read", RESOURCE)
        lesson = s.find(lesson_id)
        found = lesson.version_history.get(version_no) if lesson is not None else None
        if found is None:
            raise not_found(f"lesson {lesson_id} version {version_no}")
        return version_view(found, body=True, answer_keys=may_see_answer_keys(claims.role))

    return router
