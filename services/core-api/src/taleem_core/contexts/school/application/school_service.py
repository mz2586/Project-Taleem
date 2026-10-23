"""School use cases (application layer, no framework).

Rules that protect a child live here, so they hold however the service is called:

1. **Tenant isolation.** A teacher's organization is read from the teacher's own record, never from
   a request. Every class / enrolment / assignment lookup is scoped by that organization AND by the
   teacher who owns the class. Anything outside that scope is reported as *not found*, not
   *forbidden*, so a teacher cannot probe which ids exist in another school.
2. **Guardian-approved enrolment.** A learner joins a class only when their guardian enters the
   class code; that act records ``progress_sharing`` consent through the identity context.
3. **Live visibility.** A teacher sees an enrolled learner only while the guardian's consent covers
   ``progress_sharing`` and the learner may still learn — checked on every request, no cache. A
   withdrawal hides the learner on the very next call; the enrolment is kept so a re-grant restores
   it without re-joining.
4. **Uniform sign-in failure.** Unknown email, wrong passphrase, locked account: one error.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ....platform.errors import Problem, not_found, unauthorized, validation_error
from ..domain.model import (
    Assignment,
    Classroom,
    Enrolment,
    InvalidSchoolDataError,
    Organization,
    SchoolAuditEvent,
    Teacher,
    TeacherStatus,
    assert_passphrase_policy,
    new_join_code,
    normalise_email,
    normalise_join_code,
)
from .ports import (
    GuardianSharingConsent,
    LearnerDirectory,
    LearnerProgressReader,
    PublishedCurriculum,
    SchoolAuditLog,
    SchoolUnitOfWork,
    SecretHasher,
    TeacherSessions,
    TeacherTokenIssuer,
)

UnitOfWorkFactory = Callable[[], SchoolUnitOfWork]


def _sign_in_failed() -> Problem:
    return unauthorized("Sign-in details are not correct")


def _class_not_found() -> Problem:
    return not_found("class not found")


class SchoolService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        hasher: SecretHasher,
        issue_token: TeacherTokenIssuer,
        learners: LearnerDirectory,
        sharing_consent: GuardianSharingConsent,
        progress: LearnerProgressReader,
        curriculum: PublishedCurriculum,
        audit: SchoolAuditLog,
        clock: Callable[[], float],
        sessions: TeacherSessions | None = None,
    ) -> None:
        self._uow = uow_factory
        self._hasher = hasher
        self._issue = issue_token
        self._learners = learners
        self._consent = sharing_consent
        self._progress = progress
        self._curriculum = curriculum
        self._audit = audit
        self._now = clock
        self._sessions = sessions
        self._equalising_hash = hasher.equalising_hash()

    # ------------------------------------------------------------------ operator (system role)

    def create_organization(
        self, *, name: str, country: str, curriculum_pack_id: str, default_locale: str
    ) -> dict[str, Any]:
        try:
            org = Organization.create(
                name=name,
                country=country,
                curriculum_pack_id=curriculum_pack_id,
                default_locale=default_locale,
                now=self._now(),
            )
        except InvalidSchoolDataError as exc:
            raise validation_error(str(exc)) from exc
        with self._uow() as uow:
            uow.organizations.add(org)
            uow.commit()
        return _org_view(org)

    def get_organization(self, organization_id: str) -> dict[str, Any]:
        with self._uow() as uow:
            org = uow.organizations.get(organization_id)
        if org is None:
            raise not_found("organization not found")
        return _org_view(org)

    def create_teacher(
        self, *, organization_id: str, email: str, display_name: str, passphrase: str
    ) -> dict[str, Any]:
        try:
            assert_passphrase_policy(passphrase)
            normalised = normalise_email(email)
        except InvalidSchoolDataError as exc:
            raise validation_error(str(exc)) from exc
        with self._uow() as uow:
            if uow.organizations.get(organization_id) is None:
                raise not_found("organization not found")
            if uow.teachers.by_email(normalised) is not None:
                raise Problem(409, "EMAIL_IN_USE", "Conflict", "a teacher with this email exists")
            try:
                teacher = Teacher.create(
                    organization_id=organization_id,
                    email=normalised,
                    display_name=display_name,
                    passphrase_hash=self._hasher.hash(passphrase),
                    now=self._now(),
                )
            except InvalidSchoolDataError as exc:
                raise validation_error(str(exc)) from exc
            uow.teachers.add(teacher)
            uow.commit()
        return _teacher_view(teacher)

    # ----------------------------------------------------------------------- teacher sign-in

    def sign_in_teacher(
        self, *, email: str, passphrase: str, device_id: str = ""
    ) -> dict[str, Any]:
        try:
            normalised = normalise_email(email)
        except InvalidSchoolDataError:
            self._hasher.verify(passphrase, self._equalising_hash)
            raise _sign_in_failed() from None
        with self._uow() as uow:
            teacher = uow.teachers.by_email(normalised)
            if teacher is None:
                self._hasher.verify(passphrase, self._equalising_hash)
                raise _sign_in_failed()
            if not teacher.can_sign_in or not self._hasher.verify(
                passphrase, teacher.passphrase_hash
            ):
                teacher.record_failure()
                uow.teachers.save(teacher)
                uow.commit()
                raise _sign_in_failed()
            teacher.failed_attempts = 0
            uow.teachers.save(teacher)
            uow.commit()
        session = self._issue(teacher_ref=teacher.teacher_ref, now=self._now())
        body: dict[str, Any] = {"teacher": _teacher_view(teacher), "session": session}
        if self._sessions is not None:
            # A rotating, device-bound refresh chain, continued through identity's refresh route.
            body["refresh_token"] = self._sessions.open(
                teacher_ref=teacher.teacher_ref, device_id=device_id
            )
        return body

    def teacher_may_continue(self, teacher_ref: str) -> bool:
        """The live check identity runs on every teacher refresh: the account exists and is ACTIVE
        (a locked or suspended teacher's refresh fails like any other)."""
        with self._uow() as uow:
            teacher = uow.teachers.get(teacher_ref)
        return teacher is not None and teacher.can_sign_in

    def teacher_session_profile(self, teacher_ref: str) -> dict[str, Any]:
        """What a teacher refresh response carries besides the tokens."""
        with self._uow() as uow:
            teacher = uow.teachers.get(teacher_ref)
        return {"teacher": _teacher_view(teacher)} if teacher is not None else {}

    def teacher_profile(self, teacher_ref: str) -> dict[str, Any]:
        with self._uow() as uow:
            teacher = self._require_teacher(uow, teacher_ref)
            org = uow.organizations.get(teacher.organization_id)
        return {"teacher": _teacher_view(teacher), "organization": _org_view(org) if org else None}

    # ----------------------------------------------------------------------------- classes

    def create_class(self, *, teacher_ref: str, name: str) -> dict[str, Any]:
        with self._uow() as uow:
            teacher = self._require_teacher(uow, teacher_ref)
            code = new_join_code()
            while uow.classrooms.by_join_code(code) is not None:  # astronomically rare
                code = new_join_code()
            try:
                classroom = Classroom.create(
                    organization_id=teacher.organization_id,
                    teacher_ref=teacher.teacher_ref,
                    name=name,
                    join_code=code,
                    now=self._now(),
                )
            except InvalidSchoolDataError as exc:
                raise validation_error(str(exc)) from exc
            uow.classrooms.add(classroom)
            uow.commit()
        return _class_view(classroom, include_code=True)

    def list_classes(self, teacher_ref: str) -> list[dict[str, Any]]:
        with self._uow() as uow:
            teacher = self._require_teacher(uow, teacher_ref)
            classes = uow.classrooms.for_teacher(teacher.organization_id, teacher.teacher_ref)
            enrolled = {
                c.class_id: uow.enrolments.for_class(teacher.organization_id, c.class_id)
                for c in classes
            }
        # Counts only learners the teacher may currently see (live consent), so the number never
        # reveals that a hidden learner exists. One live identity read covers every class.
        visible = self._visible_names([e for c in classes for e in enrolled[c.class_id]])
        return [
            {
                **_class_view(c, include_code=True),
                "learner_count": sum(1 for e in enrolled[c.class_id] if e.student_ref in visible),
            }
            for c in classes
        ]

    def class_detail(self, *, teacher_ref: str, class_id: str) -> dict[str, Any]:
        with self._uow() as uow:
            teacher = self._require_teacher(uow, teacher_ref)
            classroom = self._require_own_class(uow, teacher, class_id)
            enrolments = uow.enrolments.for_class(teacher.organization_id, class_id)
        return {
            **_class_view(classroom, include_code=True),
            "learners": [
                {
                    "student_ref": e.student_ref,
                    "display_name": name,
                    "joined_at": e.joined_at,
                }
                for e, name in self._visible(enrolments)
            ],
        }

    # ------------------------------------------------------------------ guardian-approved join

    def join_class(
        self, *, guardian_ref: str, student_ref: str, class_code: str, attestation: str
    ) -> dict[str, Any]:
        """A guardian enrols their own learner with a class code; this records consent.

        Joining never (re)grants the learner's *learning* consent: if that has been withdrawn, the
        join is refused rather than silently restoring it.
        """
        try:
            code = normalise_join_code(class_code)
        except InvalidSchoolDataError:
            raise _class_not_found() from None
        if not attestation.strip():
            raise validation_error("an attestation is required to share progress with a teacher")
        self._require_own_child(guardian_ref, student_ref)
        if not self._learners.may_learn(student_ref):
            raise Problem(
                409,
                "CONSENT_REQUIRED",
                "Learning consent required",
                "give learning consent for this learner before joining a class",
            )
        with self._uow() as uow:
            classroom = uow.classrooms.by_join_code(code)
            if classroom is None:
                raise _class_not_found()
            existing = uow.enrolments.get(
                classroom.organization_id, classroom.class_id, student_ref
            )
        # Consent first (identity's own transaction): an enrolment never exists without it.
        self._consent.grant(
            guardian_ref=guardian_ref, student_ref=student_ref, attestation=attestation
        )
        if existing is None:
            with self._uow() as uow:
                uow.enrolments.add(
                    Enrolment(
                        class_id=classroom.class_id,
                        organization_id=classroom.organization_id,
                        student_ref=student_ref,
                        approved_by=guardian_ref,
                        joined_at=self._now(),
                    )
                )
                uow.commit()
            self._record("enrolment.joined", guardian_ref, student_ref, classroom)
        # The guardian learns the class name (they hold the code) — nothing about other learners.
        return {"class_id": classroom.class_id, "class_name": classroom.name, "joined": True}

    def child_classes(self, *, guardian_ref: str, student_ref: str) -> list[dict[str, Any]]:
        """The classes one learner is in, for that learner's guardian only (404 otherwise)."""
        self._require_own_child(guardian_ref, student_ref)
        sharing = self._learners.shares_with_teacher(student_ref)
        out: list[dict[str, Any]] = []
        with self._uow() as uow:
            for e in uow.enrolments.for_student(student_ref):
                classroom = uow.classrooms.get(e.organization_id, e.class_id)
                if classroom is None:
                    continue
                org = uow.organizations.get(e.organization_id)
                teacher = uow.teachers.get(classroom.teacher_ref)
                out.append(
                    {
                        "class_id": classroom.class_id,
                        "class_name": classroom.name,
                        "organization_name": org.name if org else "",
                        "teacher_display_name": teacher.display_name if teacher else "",
                        "joined_at": e.joined_at,
                        # The master switch: progress_sharing (plus live learning consent).
                        "teacher_can_see_progress": sharing,
                    }
                )
        return out

    def leave_class(self, *, guardian_ref: str, student_ref: str, class_id: str) -> dict[str, Any]:
        """Remove one class enrolment. That teacher stops seeing the learner on their next request;
        other classes are untouched, and ``progress_sharing`` stays the master switch."""
        self._require_own_child(guardian_ref, student_ref)
        with self._uow() as uow:
            mine = next(
                (e for e in uow.enrolments.for_student(student_ref) if e.class_id == class_id), None
            )
            classroom = uow.classrooms.get(mine.organization_id, class_id) if mine else None
            if mine is None or classroom is None:
                raise _class_not_found()
            uow.enrolments.remove(mine.organization_id, class_id, student_ref)
            uow.commit()
        self._record("enrolment.left", guardian_ref, student_ref, classroom)
        return {"class_id": class_id, "left": True}

    # ------------------------------------------------------------------ lesson catalog (teacher)

    def published_lessons(self, teacher_ref: str) -> list[dict[str, Any]]:
        """Published lessons of the teacher's organization's curriculum pack: objective code and
        localized title only — the assignment picker needs nothing else."""
        with self._uow() as uow:
            teacher = self._require_teacher(uow, teacher_ref)
            org = uow.organizations.get(teacher.organization_id)
        pack = (org.curriculum_pack_id if org else "").casefold()
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for lesson in self._curriculum.catalog():
            if lesson.curriculum_pack.casefold() != pack or lesson.objective_code in seen:
                continue
            seen.add(lesson.objective_code)
            out.append({"objective_code": lesson.objective_code, "title": dict(lesson.title)})
        return sorted(out, key=lambda x: str(x["objective_code"]))

    # ------------------------------------------------------------------------- assignments

    def create_assignment(
        self, *, teacher_ref: str, class_id: str, objective_code: str, due_at: float
    ) -> dict[str, Any]:
        if not self._curriculum.is_published(objective_code):
            raise Problem(
                422,
                "LESSON_NOT_PUBLISHED",
                "Validation failed",
                "only a published lesson can be assigned",
            )
        with self._uow() as uow:
            teacher = self._require_teacher(uow, teacher_ref)
            classroom = self._require_own_class(uow, teacher, class_id)
            try:
                assignment = Assignment.create(
                    classroom=classroom,
                    objective_code=objective_code,
                    due_at=due_at,
                    assigned_by=teacher.teacher_ref,
                    now=self._now(),
                )
            except InvalidSchoolDataError as exc:
                raise validation_error(str(exc)) from exc
            uow.assignments.add(assignment)
            uow.commit()
        return _assignment_view(assignment)

    def list_assignments(self, *, teacher_ref: str, class_id: str) -> list[dict[str, Any]]:
        with self._uow() as uow:
            teacher = self._require_teacher(uow, teacher_ref)
            self._require_own_class(uow, teacher, class_id)
            items = uow.assignments.for_class(teacher.organization_id, class_id)
        return [_assignment_view(a) for a in items]

    def assignment_progress(
        self, *, teacher_ref: str, class_id: str, assignment_id: str
    ) -> dict[str, Any]:
        with self._uow() as uow:
            teacher = self._require_teacher(uow, teacher_ref)
            self._require_own_class(uow, teacher, class_id)
            assignment = uow.assignments.get(teacher.organization_id, assignment_id)
            if assignment is None or assignment.class_id != class_id:
                raise not_found("assignment not found")
            enrolments = uow.enrolments.for_class(teacher.organization_id, class_id)
        now = self._now()
        visible = self._visible(enrolments)
        # One batched knowledge read for the visible learners only (hidden learners are never read).
        progress = self._progress.objective_progress_many(
            [e.student_ref for e, _ in visible],
            assignment.objective_code,
            since=assignment.created_at,
        )
        rows: list[dict[str, Any]] = []
        for e, name in visible:
            p = progress[e.student_ref]
            rows.append(
                {
                    "student_ref": e.student_ref,
                    "display_name": name,
                    # Completed = practised this objective since it was assigned.
                    "completed": p.attempts_since > 0,
                    "attempts_since_assigned": p.attempts_since,
                    "mastery": p.mastery,
                    "mastery_state": p.state,
                    "mastered": p.state == "mastered",
                }
            )
        return {
            **_assignment_view(assignment),
            "overdue": now > assignment.due_at,
            "learners": rows,
        }

    # ------------------------------------------------------------------------------ helpers

    def _visible_names(self, enrolments: list[Enrolment]) -> dict[str, str]:
        # LIVE, per request: a withdrawn progress_sharing consent hides the learner immediately.
        # One batched identity read per request, never cached across requests.
        return self._learners.visible_to_teacher([e.student_ref for e in enrolments])

    def _visible(self, enrolments: list[Enrolment]) -> list[tuple[Enrolment, str]]:
        """The enrolments the teacher may see right now, in order, with display names."""
        names = self._visible_names(enrolments)
        return [(e, names[e.student_ref]) for e in enrolments if e.student_ref in names]

    def _require_teacher(self, uow: SchoolUnitOfWork, teacher_ref: str) -> Teacher:
        teacher = uow.teachers.get(teacher_ref)
        # Only reached with a verified teacher token, so naming the reason is not an enumeration
        # oracle (sign-in failures stay uniform). Access ends on the next request, not at expiry.
        if teacher is not None and teacher.status is TeacherStatus.LOCKED:
            raise Problem(
                403,
                "TEACHER_LOCKED",
                "Forbidden",
                "too many failed sign-ins; ask your school administrator to unlock the account",
            )
        if teacher is None or not teacher.can_sign_in:
            raise Problem(403, "TEACHER_INACTIVE", "Forbidden", "teacher account is not active")
        return teacher

    def _require_own_child(self, guardian_ref: str, student_ref: str) -> None:
        if self._learners.guardian_of(student_ref) != guardian_ref:
            raise not_found("learner not found")  # same answer as identity's IDOR guard

    def _record(self, action: str, guardian_ref: str, student_ref: str, c: Classroom) -> None:
        self._audit.record(
            SchoolAuditEvent(
                action=action,
                actor_ref=guardian_ref,
                actor_role="guardian",
                subject_ref=student_ref,
                organization_id=c.organization_id,
                class_id=c.class_id,
                at=self._now(),
            )
        )

    def _require_own_class(
        self, uow: SchoolUnitOfWork, teacher: Teacher, class_id: str
    ) -> Classroom:
        classroom = uow.classrooms.get(teacher.organization_id, class_id)
        if classroom is None or classroom.teacher_ref != teacher.teacher_ref:
            raise _class_not_found()
        return classroom


def _org_view(org: Organization) -> dict[str, Any]:
    return {
        "organization_id": org.organization_id,
        "name": org.name,
        "country": org.country,
        "curriculum_pack_id": org.curriculum_pack_id,
        "default_locale": org.default_locale,
        "created_at": org.created_at,
    }


def _teacher_view(t: Teacher) -> dict[str, Any]:
    return {
        "teacher_ref": t.teacher_ref,
        "organization_id": t.organization_id,
        "email": t.email,
        "display_name": t.display_name,
        "status": t.status.value,
        "created_at": t.created_at,
    }


def _class_view(c: Classroom, *, include_code: bool) -> dict[str, Any]:
    view: dict[str, Any] = {
        "class_id": c.class_id,
        "organization_id": c.organization_id,
        "teacher_ref": c.teacher_ref,
        "name": c.name,
        "created_at": c.created_at,
    }
    if include_code:
        view["join_code"] = c.join_code
    return view


def _assignment_view(a: Assignment) -> dict[str, Any]:
    return {
        "assignment_id": a.assignment_id,
        "class_id": a.class_id,
        "objective_code": a.objective_code,
        "due_at": a.due_at,
        "assigned_by": a.assigned_by,
        "created_at": a.created_at,
    }
