"""FastAPI router for /v1/school/** (contract: packages/contracts/school.openapi.yaml).

Who may call what (deny-by-default PDP, then ownership in the service):

- ``system`` (operator): create organizations and teacher accounts.
- ``teacher``: their own profile, their own classes, assignments in their own classes, and the
  progress of learners in those classes whose guardians share it. The acting teacher — and so the
  organization — always comes from the verified token, never from the request.
- ``guardian``: join their own learner to a class with a class code (records consent).
- ``teacher``: also the marking queue of their own classes, and mark / return a submission.
- ``student``: their own homework list and submissions — assigned and self-paced
  (``build_school_learner_router``, mounted behind the live learner consent gate like every other
  learner surface).

One route is public: teacher sign-in, which is rate limited and fails uniformly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ....auth.dependencies import authorize, require_owner_or
from ....auth.jwt_verifier import Claims
from ....platform.errors import not_found
from ..application.school_service import SchoolService
from ..domain.model import MAX_FEEDBACK

# Edge bound on a submitted answer (the domain enforces the item's own cap after normalisation).
_MAX_TEXT_EDGE = 8000


class OrganizationIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(min_length=1, max_length=120)
    country: str = Field(min_length=2, max_length=2)
    curriculum_pack_id: str = Field(alias="curriculumPackId", min_length=1, max_length=64)
    default_locale: str = Field(alias="defaultLocale", min_length=2, max_length=8)


class TeacherIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(alias="displayName", min_length=1, max_length=60)
    passphrase: str = Field(min_length=1, max_length=256)


class TeacherSignInIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    email: str = Field(min_length=3, max_length=254)
    passphrase: str = Field(min_length=1, max_length=256)
    device_id: str = Field(default="", alias="deviceId", max_length=64)


class ClassIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class JoinIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    class_code: str = Field(alias="classCode", min_length=4, max_length=16)
    student_ref: str = Field(alias="studentRef", min_length=1, max_length=64)
    attestation: str = Field(min_length=1, max_length=500)


class AssignmentIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    objective_code: str = Field(alias="objectiveCode", min_length=1, max_length=64)
    due_at: float = Field(alias="dueAt", gt=0)


class SubmitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=_MAX_TEXT_EDGE)


class MarkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: str = Field(min_length=1, max_length=16)
    score: int | None = None
    feedback: str = Field(default="", max_length=MAX_FEEDBACK * 2)


class ReturnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback: str = Field(min_length=1, max_length=MAX_FEEDBACK * 2)


class SubmissionConcernIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str = Field(min_length=1, max_length=32)
    text: str | None = Field(default=None, max_length=1000)


def build_school_router(
    service: SchoolService,
    claims_dependency: Callable[..., Claims],
    *,
    sign_in_guard: Callable[[Request], None] = lambda _request: None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/school", tags=["school"])

    # ------------------------------------------------------------------- operator (system)

    @router.post("/organizations", status_code=201)
    def create_organization(
        body: OrganizationIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "school.organization")
        return service.create_organization(
            name=body.name,
            country=body.country,
            curriculum_pack_id=body.curriculum_pack_id,
            default_locale=body.default_locale,
        )

    @router.get("/organizations/{organization_id}")
    def get_organization(
        organization_id: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        if claims.role == "teacher":
            authorize(claims, "read", "school.self")
            org = service.teacher_profile(claims.sub)["organization"]
            if not org or org["organization_id"] != organization_id:
                raise not_found("organization not found")  # never confirm another tenant exists
            return dict(org)
        authorize(claims, "manage", "school.organization")
        return service.get_organization(organization_id)

    @router.post("/organizations/{organization_id}/teachers", status_code=201)
    def create_teacher(
        organization_id: str, body: TeacherIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "school.organization")
        return service.create_teacher(
            organization_id=organization_id,
            email=body.email,
            display_name=body.display_name,
            passphrase=body.passphrase,
        )

    # ------------------------------------------------------------------- public sign-in

    @router.post("/teachers:signin")
    def sign_in_teacher(body: TeacherSignInIn, request: Request) -> dict[str, Any]:
        sign_in_guard(request)
        # The refresh token is continued at /v1/identity/sessions:refresh (and ended at
        # sessions:signout) — identity's rotating chains, registered for the teacher role.
        return service.sign_in_teacher(
            email=body.email, passphrase=body.passphrase, device_id=body.device_id
        )

    # ------------------------------------------------------------------------- teacher

    @router.get("/me")
    def me(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", "school.self")
        return service.teacher_profile(claims.sub)

    @router.post("/classes", status_code=201)
    def create_class(body: ClassIn, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "manage", "school.class")
        return service.create_class(teacher_ref=claims.sub, name=body.name)

    @router.get("/classes")
    def list_classes(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "manage", "school.class")
        return {"classes": service.list_classes(claims.sub)}

    # ------------------------------------------------------------------------ guardian

    @router.post("/classes:join")
    def join_class(
        body: JoinIn, request: Request, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "school.enrolment")
        sign_in_guard(request)  # bounds class-code guessing per client
        return service.join_class(
            guardian_ref=claims.sub,
            student_ref=body.student_ref,
            class_code=body.class_code,
            attestation=body.attestation,
        )

    @router.get("/children/{student_ref}/classes")
    def child_classes(
        student_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        """The guardian's own child's classes (another family's child is a 404)."""
        authorize(claims, "manage", "school.enrolment")
        return {"classes": service.child_classes(guardian_ref=claims.sub, student_ref=student_ref)}

    @router.post("/children/{student_ref}/classes/{class_id}:leave")
    def leave_class(
        student_ref: str, class_id: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        """Leave one class. progress_sharing stays the master switch for all classes."""
        authorize(claims, "manage", "school.enrolment")
        return service.leave_class(
            guardian_ref=claims.sub, student_ref=student_ref, class_id=class_id
        )

    # ------------------------------------------------------------------------- teacher

    @router.get("/lessons")
    def published_lessons(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        """Published lessons of the teacher's curriculum pack (objective code + title only)."""
        authorize(claims, "manage", "school.assignment")
        return {"lessons": service.published_lessons(claims.sub)}

    @router.get("/classes/{class_id}")
    def class_detail(class_id: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", "school.learner_progress")
        return service.class_detail(teacher_ref=claims.sub, class_id=class_id)

    @router.post("/classes/{class_id}/assignments", status_code=201)
    def create_assignment(
        class_id: str, body: AssignmentIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "school.assignment")
        return service.create_assignment(
            teacher_ref=claims.sub,
            class_id=class_id,
            objective_code=body.objective_code,
            due_at=body.due_at,
        )

    @router.get("/classes/{class_id}/assignments")
    def list_assignments(
        class_id: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "school.assignment")
        return {"assignments": service.list_assignments(teacher_ref=claims.sub, class_id=class_id)}

    @router.get("/classes/{class_id}/assignments/{assignment_id}/progress")
    def assignment_progress(
        class_id: str, assignment_id: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "read", "school.learner_progress")
        return service.assignment_progress(
            teacher_ref=claims.sub, class_id=class_id, assignment_id=assignment_id
        )

    @router.get("/classes/{class_id}/learners/{student_ref}")
    def learner_detail(
        class_id: str, student_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        # The "why this recommendation" panel. Visible only while the guardian shares progress —
        # the same live check as every class read; a hidden learner is simply not found.
        authorize(claims, "read", "school.learner_progress")
        return service.learner_detail(
            teacher_ref=claims.sub, class_id=class_id, student_ref=student_ref
        )

    # ----------------------------------------------------------------- marking (teacher)

    @router.get("/classes/{class_id}/submissions")
    def class_submissions(
        class_id: str,
        status: str = Query(default="submitted", max_length=16),
        claims: Claims = Depends(claims_dependency),
    ) -> dict[str, Any]:
        """The marking queue of the teacher's own class, oldest first (other schools: 404)."""
        authorize(claims, "manage", "school.marking")
        return {
            "submissions": service.class_submissions(
                teacher_ref=claims.sub, class_id=class_id, status=status
            )
        }

    @router.post("/submissions/{submission_id}:mark")
    def mark_submission(
        submission_id: str, body: MarkIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "school.marking")
        return service.mark_submission(
            teacher_ref=claims.sub,
            submission_id=submission_id,
            outcome=body.outcome,
            score=body.score,
            feedback=body.feedback,
        )

    @router.post("/submissions/{submission_id}:return")
    def return_submission(
        submission_id: str, body: ReturnIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "school.marking")
        return service.return_submission(
            teacher_ref=claims.sub, submission_id=submission_id, feedback=body.feedback
        )

    @router.post("/submissions/{submission_id}:concern", status_code=201)
    def submission_concern(
        submission_id: str, body: SubmissionConcernIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        """Raise a safeguarding concern about the learner of this submission (source teacher).
        The learner and submission come from the server; the response is a receipt only."""
        authorize(claims, "raise", "safeguarding.concern")
        authorize(claims, "manage", "school.marking")
        return service.raise_concern_about_submission(
            teacher_ref=claims.sub,
            submission_id=submission_id,
            category=body.category,
            text=body.text,
        )

    return router


def build_school_learner_router(
    service: SchoolService, claims_dependency: Callable[..., Claims]
) -> APIRouter:
    """The learner's homework (HOMEWORK_AND_MARKING_CONTRACT §2). Mount it behind the live learner
    permission gate: a withdrawn consent or a suspended account is a 403 on the next request."""
    router = APIRouter(prefix="/v1/school", tags=["school"])

    @router.get("/learners/{student_ref}/homework")
    def learner_homework(
        student_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "operate", "school.homework")
        require_owner_or(claims, student_ref, privileged_roles=())
        return service.learner_homework(student_ref)

    @router.post("/learners/{student_ref}/homework/{assignment_id}/items/{item_ref}:submit")
    def learner_submit(
        student_ref: str,
        assignment_id: str,
        item_ref: str,
        body: SubmitIn,
        claims: Claims = Depends(claims_dependency),
    ) -> dict[str, Any]:
        authorize(claims, "operate", "school.homework")
        require_owner_or(claims, student_ref, privileged_roles=())
        return service.learner_submit(
            student_ref=student_ref, assignment_id=assignment_id, item_ref=item_ref, text=body.text
        )

    @router.post(
        "/learners/{student_ref}/homework/self-paced/{objective_code}/items/{item_ref}:submit"
    )
    def learner_submit_self_paced(
        student_ref: str,
        objective_code: str,
        item_ref: str,
        body: SubmitIn,
        claims: Claims = Depends(claims_dependency),
    ) -> dict[str, Any]:
        """A written answer to a lesson the learner studied (HOMEWORK_AND_MARKING_CONTRACT §6):
        no assignment, no class, no teacher; ``progress_sharing`` does not apply."""
        authorize(claims, "operate", "school.homework")
        require_owner_or(claims, student_ref, privileged_roles=())
        return service.learner_submit_self_paced(
            student_ref=student_ref,
            objective_code=objective_code,
            item_ref=item_ref,
            text=body.text,
        )

    return router
