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
5. **Homework is the child's own words** (HOMEWORK_AND_MARKING_CONTRACT). A learner sees only
   their own submissions and never a marking aid (rubric, sample answer, guidance). A teacher sees
   submissions only of learners in their own class whom they may currently see (rule 3). Every
   submit, mark and return is audited with refs only — never the text or the feedback.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ....platform import observability
from ....platform.cohort import COHORTS
from ....platform.concurrency import ConcurrencyConflictError
from ....platform.errors import Problem, conflict, not_found, unauthorized, validation_error
from ..domain.model import (
    AUTO_REVIEWER,
    Assignment,
    Classroom,
    Enrolment,
    InvalidSchoolDataError,
    MarkOutcome,
    Organization,
    SchoolAuditEvent,
    Submission,
    SubmissionConflictError,
    SubmissionSource,
    SubmissionStatus,
    Teacher,
    TeacherStatus,
    assert_passphrase_policy,
    new_join_code,
    normalise_email,
    normalise_join_code,
)
from .ports import (
    ConcernChannel,
    DisclosureScreen,
    GuardianSharingConsent,
    LearnerDirectory,
    LearnerExplanationReader,
    LearnerProgressReader,
    PublishedCurriculum,
    SchoolAuditLog,
    SchoolUnitOfWork,
    SecretHasher,
    TeacherSessions,
    TeacherTokenIssuer,
    WrittenItem,
    WrittenLesson,
    WrittenWork,
)

UnitOfWorkFactory = Callable[[], SchoolUnitOfWork]


def _sign_in_failed() -> Problem:
    return unauthorized("Sign-in details are not correct")


def _class_not_found() -> Problem:
    return not_found("class not found")


def _submission_not_found() -> Problem:
    return not_found("submission not found")


def _submission_problem(exc: InvalidSchoolDataError) -> Problem:
    if isinstance(exc, SubmissionConflictError):
        return Problem(409, exc.code, "Submission cannot change this way", str(exc))
    return validation_error(str(exc))


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
        explanations: LearnerExplanationReader | None = None,
        written: WrittenWork | None = None,
        concerns: ConcernChannel | None = None,
        disclosures: DisclosureScreen | None = None,
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
        self._explanations = explanations
        self._written = written
        self._concerns = concerns
        self._disclosures = disclosures
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

    # ------------------------------------------------------------- demo cohort (no HTTP route)

    def assign_teacher_cohort(self, *, teacher_ref: str, cohort: str) -> bool:
        """Set a teacher's cohort (DEMO_COHORT_CONTRACT). **Not exposed by any HTTP route**: the
        only caller is the demo seeder (``tools/demo_cohort.py``). True if it changed."""
        if cohort not in COHORTS:
            raise ValueError(f"unknown cohort {cohort!r}")
        with self._uow() as uow:
            if uow.teachers.get(teacher_ref) is None:
                raise not_found("teacher not found")
            changed = uow.teachers.set_cohort(teacher_ref, cohort)
            uow.commit()
        return changed

    def teacher_cohort(self, teacher_ref: str) -> str:
        """The teacher account's cohort ("" when there is no such account)."""
        with self._uow() as uow:
            teacher = uow.teachers.get(teacher_ref)
        return teacher.cohort if teacher is not None else ""

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

    def learner_detail(
        self, *, teacher_ref: str, class_id: str, student_ref: str
    ) -> dict[str, Any]:
        """One learner of the teacher's own class, with the explained recommendations.

        Visibility is exactly that of ``class_detail``: enrolled in this class AND, live on this
        request, the guardian's progress_sharing consent plus the learner gate. Anything else is
        *not found*, so the route never reveals that a hidden learner exists. The learning context
        is read only after the visibility check passes.
        """
        with self._uow() as uow:
            teacher = self._require_teacher(uow, teacher_ref)
            self._require_own_class(uow, teacher, class_id)
            enrolment = uow.enrolments.get(teacher.organization_id, class_id, student_ref)
        if enrolment is None:
            raise not_found("learner not found")
        visible = self._visible([enrolment])
        if not visible:
            raise not_found("learner not found")
        _, name = visible[0]
        explained: dict[str, object] = (
            self._explanations.explain(student_ref) if self._explanations is not None else {}
        )
        return {
            "student_ref": student_ref,
            "display_name": name,
            "class_id": class_id,
            "joined_at": enrolment.joined_at,
            "confidence": explained.get("confidence", "low"),
            "next_action": explained.get("next_action"),
            "recommendations": explained.get("recommendations", []),
            "placement": explained.get("placement"),
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
            # Two-way cohort isolation (DEMO_COHORT_CONTRACT §1): a demo learner never joins a real
            # class and a real learner never joins a demo one. Answered exactly like a wrong code.
            teacher = uow.teachers.get(classroom.teacher_ref)
            if teacher is None or teacher.cohort != self._learner_cohort(student_ref):
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

    # ------------------------------------------------------------------- homework (learner)

    def learner_homework(self, student_ref: str) -> dict[str, Any]:
        """The learner's Homework screen (HOMEWORK_AND_MARKING_CONTRACT §2 + §6).

        Two sources, each entry and item tagged ``source``:

        - ``assignment``: every assignment of every class the learner is in (with its due date);
        - ``self_paced``: every lesson the learner has studied (a live session or a synced offline
          attempt on its objective) that no class of theirs has assigned. No due date. When the
          same lesson is also assigned, the assignment wins (it keeps the due date).

        Each item carries its marking mode and the learner's latest submission state. Never the
        rubric or an answer key; the sample answer / guidance only after an open answer was
        submitted, as ``compare``. Lessons are read through the cohort-filtered read model."""
        with self._uow() as uow:
            assignments: list[tuple[Assignment, Classroom]] = []
            for e in uow.enrolments.for_student(student_ref):
                classroom = uow.classrooms.get(e.organization_id, e.class_id)
                if classroom is None:
                    continue
                for a in uow.assignments.for_class(e.organization_id, e.class_id):
                    assignments.append((a, classroom))
            subs = uow.submissions.for_student(student_ref)
        mine = {(s.assignment_id, s.item_ref): s for s in subs if not s.self_paced}
        mine_self = {(s.objective_code, s.item_ref): s for s in subs if s.self_paced}
        assigned = {a.objective_code for a, _ in assignments}
        self_paced = [
            code
            for code in dict.fromkeys(
                [*self._studied(student_ref), *(s.objective_code for s in subs if s.self_paced)]
            )
            if code not in assigned
        ]
        lessons = self._lessons(assigned | set(self_paced))
        now = self._now()
        out: list[dict[str, Any]] = []
        for a, classroom in sorted(assignments, key=lambda x: (x[0].due_at, x[0].assignment_id)):
            lesson = lessons.get(a.objective_code)
            items = [
                _learner_homework_item(
                    item, SubmissionSource.ASSIGNMENT, mine.get((a.assignment_id, item.item_ref))
                )
                for item in (lesson.items if lesson else ())
            ]
            out.append(
                {
                    "source": SubmissionSource.ASSIGNMENT.value,
                    "assignment_id": a.assignment_id,
                    "class_id": classroom.class_id,
                    "class_name": classroom.name,
                    "objective_code": a.objective_code,
                    "lesson_title": dict(lesson.title) if lesson else {},
                    "due_at": a.due_at,
                    "overdue": now > a.due_at,
                    "items": items,
                }
            )
        for code in self_paced:
            lesson = lessons.get(code)
            if lesson is None or not lesson.items:
                continue  # unpublished, another cohort's, or no written items: nothing to do
            out.append(
                {
                    "source": SubmissionSource.SELF_PACED.value,
                    "assignment_id": None,
                    "class_id": None,
                    "class_name": None,
                    "objective_code": code,
                    "lesson_title": dict(lesson.title),
                    "due_at": None,
                    "overdue": False,
                    "items": [
                        _learner_homework_item(
                            item,
                            SubmissionSource.SELF_PACED,
                            mine_self.get((code, item.item_ref)),
                        )
                        for item in lesson.items
                    ],
                }
            )
        return {"assignments": out}

    def learner_submit(
        self, *, student_ref: str, assignment_id: str, item_ref: str, text: str
    ) -> dict[str, Any]:
        """Submit (or resubmit, while ``submitted`` / ``returned``) a written answer to an item
        of an assignment. The class teacher may read it, so ``progress_sharing`` is required."""
        with self._uow() as uow:
            assignment = self._learner_assignment(uow, student_ref, assignment_id)
        lesson = self._lessons({assignment.objective_code}).get(assignment.objective_code)
        item = lesson.item(item_ref) if lesson else None
        if item is None:
            raise not_found("item not found")  # not a written item of this assignment's lesson
        if not self._learners.shares_with_teacher(student_ref):
            # The answer goes to the class teacher; without progress_sharing nobody may read it.
            raise Problem(
                403,
                "SHARING_REQUIRED",
                "Forbidden",
                "a grown-up must allow sharing work with the teacher first",
            )

        def find(uow: SchoolUnitOfWork) -> Submission | None:
            return uow.submissions.find(assignment_id, item_ref, student_ref)

        def start(now: float) -> Submission:
            return Submission.start(
                assignment=assignment,
                item_ref=item_ref,
                student_ref=student_ref,
                text=text,
                max_chars=item.max_chars,
                max_score=item.max_score,
                now=now,
            )

        sub = self._store_answer(item, text, find=find, start=start)
        return _learner_submit_view(sub, item)

    def learner_submit_self_paced(
        self, *, student_ref: str, objective_code: str, item_ref: str, text: str
    ) -> dict[str, Any]:
        """Submit (or resubmit) a written answer to an item of a lesson the learner studied, with
        no assignment and no teacher (contract §6). Nobody else reads it, so ``progress_sharing``
        does not apply. A lesson the learner has not studied — or one a class of theirs has
        assigned (answer it there) — is refused."""
        with self._uow() as uow:
            assigned = any(
                a.objective_code == objective_code
                for e in uow.enrolments.for_student(student_ref)
                for a in uow.assignments.for_class(e.organization_id, e.class_id)
            )
            existing = uow.submissions.find_self_paced(objective_code, item_ref, student_ref)
        if existing is None and objective_code not in self._studied(student_ref):
            raise not_found("lesson not found")  # not studied yet: nothing to answer
        if assigned and existing is None:
            raise Problem(
                409,
                "LESSON_ASSIGNED",
                "Lesson is assigned",
                "this lesson is assigned to your class; answer it in the assignment",
            )
        lesson = self._lessons({objective_code}).get(objective_code)
        item = lesson.item(item_ref) if lesson else None
        if item is None:
            raise not_found("item not found")  # unpublished, another cohort's, or not written

        def find(uow: SchoolUnitOfWork) -> Submission | None:
            return uow.submissions.find_self_paced(objective_code, item_ref, student_ref)

        def start(now: float) -> Submission:
            return Submission.start_self_paced(
                objective_code=objective_code,
                item_ref=item_ref,
                student_ref=student_ref,
                text=text,
                max_chars=item.max_chars,
                max_score=item.max_score,
                now=now,
            )

        sub = self._store_answer(item, text, find=find, start=start)
        return _learner_submit_view(sub, item)

    def _store_answer(
        self,
        item: WrittenItem,
        text: str,
        *,
        find: Callable[[SchoolUnitOfWork], Submission | None],
        start: Callable[[float], Submission],
    ) -> Submission:
        """Create or resubmit the answer, auto-mark it when its key is exact, then record the
        evidence (idempotent), the audit (refs only) and the disclosure screen (never blocks)."""
        now = self._now()
        existing: Submission | None = None
        try:
            with self._uow() as uow:
                existing = find(uow)
                if existing is None:
                    sub = start(now)
                else:
                    sub = existing
                    sub.resubmit(
                        text=text, max_chars=item.max_chars, max_score=item.max_score, now=now
                    )
                verdict = (
                    self._written.check_answer(sub.objective_code, sub.item_ref, sub.text)
                    if self._written is not None and item.auto_markable
                    else None
                )
                if verdict is not None:
                    sub.auto_mark(met=verdict, now=now)
                if existing is None:
                    uow.submissions.add(sub)
                else:
                    uow.submissions.save(sub)
                uow.commit()
        except InvalidSchoolDataError as exc:
            if existing is not None and existing.auto_marked:
                # A final automatic mark: re-ensure its evidence (heals a failed evidence write).
                self._ensure_evidence(existing)
            raise _submission_problem(exc) from exc
        except ConcurrencyConflictError as exc:  # two submissions raced: one wins
            raise conflict("this answer was submitted at the same time; try again") from exc
        self._record_submission("submission.submitted", sub.student_ref, "student", sub)
        if sub.status is SubmissionStatus.MARKED:
            self._ensure_evidence(sub)
            self._record_submission("submission.marked", AUTO_REVIEWER, "system", sub)
        self._screen(sub)
        return sub

    def _screen(self, sub: Submission) -> None:
        """The disclosure screen (contract §6). It only escalates to a human: a failure here is
        logged (refs only) and never changes or blocks the child's submission."""
        if self._disclosures is None:
            return
        try:
            self._disclosures.screen_submission(
                student_ref=sub.student_ref, submission_id=sub.submission_id, text=sub.text
            )
        except Exception:  # noqa: BLE001 - the child's answer is saved; the screen must not fail it
            observability.log_event("disclosure_screen_failed", submission_id=sub.submission_id)
            observability.record_event("taleem_disclosure_screen_failures_total")

    def _studied(self, student_ref: str) -> list[str]:
        if self._written is None:
            return []
        return list(self._written.studied_objectives(student_ref))

    # -------------------------------------------------------------------- marking (teacher)

    def class_submissions(
        self, *, teacher_ref: str, class_id: str, status: str
    ) -> list[dict[str, Any]]:
        """The marking queue of the teacher's own class, oldest first. Only learners the teacher
        may see right now (enrolled + live progress_sharing) appear."""
        try:
            wanted = SubmissionStatus(status)
        except ValueError:
            raise validation_error("status must be one of: submitted, returned, marked") from None
        with self._uow() as uow:
            teacher = self._require_teacher(uow, teacher_ref)
            self._require_own_class(uow, teacher, class_id)
            enrolled = {
                e.student_ref for e in uow.enrolments.for_class(teacher.organization_id, class_id)
            }
            subs = [
                s
                for s in uow.submissions.for_class(teacher.organization_id, class_id, wanted)
                if s.student_ref in enrolled
            ]
        names = self._learners.visible_to_teacher([s.student_ref for s in subs])
        lessons = self._lessons({s.objective_code for s in subs if s.student_ref in names})
        return [
            _teacher_submission_view(s, names[s.student_ref], lessons.get(s.objective_code))
            for s in subs
            if s.student_ref in names
        ]

    def mark_submission(
        self,
        *,
        teacher_ref: str,
        submission_id: str,
        outcome: str,
        score: int | None,
        feedback: str | None,
    ) -> dict[str, Any]:
        """Mark once (final), then record ONE mastery evidence for it (idempotent by
        ``submission_id``). A mark attempt on an already-marked submission re-ensures that
        evidence before answering 409, so a mark whose evidence write failed heals on retry."""
        with self._uow() as uow:
            teacher, sub, name = self._teacher_submission(uow, teacher_ref, submission_id)
            if sub.status is SubmissionStatus.MARKED:
                self._ensure_evidence(sub)
            try:
                sub.mark(
                    outcome=outcome,
                    score=score,
                    feedback=feedback,
                    teacher_ref=teacher.teacher_ref,
                    now=self._now(),
                )
            except InvalidSchoolDataError as exc:
                raise _submission_problem(exc) from exc
            uow.submissions.save(sub)
            uow.commit()
        self._ensure_evidence(sub)
        self._record_submission("submission.marked", teacher.teacher_ref, "teacher", sub)
        lesson = self._lessons({sub.objective_code}).get(sub.objective_code)
        return _teacher_submission_view(sub, name, lesson)

    def return_submission(
        self, *, teacher_ref: str, submission_id: str, feedback: str
    ) -> dict[str, Any]:
        """Ask the child to try again (feedback required). Records no evidence."""
        with self._uow() as uow:
            teacher, sub, name = self._teacher_submission(uow, teacher_ref, submission_id)
            try:
                sub.return_for_rework(
                    feedback=feedback, teacher_ref=teacher.teacher_ref, now=self._now()
                )
            except InvalidSchoolDataError as exc:
                raise _submission_problem(exc) from exc
            uow.submissions.save(sub)
            uow.commit()
        self._record_submission("submission.returned", teacher.teacher_ref, "teacher", sub)
        lesson = self._lessons({sub.objective_code}).get(sub.objective_code)
        return _teacher_submission_view(sub, name, lesson)

    def raise_concern_about_submission(
        self, *, teacher_ref: str, submission_id: str, category: str, text: str | None
    ) -> dict[str, Any]:
        """ "Raise a safeguarding concern" from a queue row (HOMEWORK_AND_MARKING_CONTRACT §4).

        The learner and the submission come from the stored submission, never from the client.
        The scope is the teacher's own class and an enrolled learner — deliberately NOT the live
        progress_sharing check, so the safety channel stays open. The submission is not changed
        and nothing is shown to the child. Not audited here: safeguarding audits the raise."""
        if self._concerns is None:
            raise Problem(503, "CONCERNS_UNAVAILABLE", "Unavailable", "concerns are not wired")
        with self._uow() as uow:
            teacher = self._require_teacher(uow, teacher_ref)
            sub = uow.submissions.get(teacher.organization_id, submission_id)
            classroom = (
                uow.classrooms.get(teacher.organization_id, sub.class_id)
                if sub is not None and sub.class_id is not None
                else None
            )
            if (
                sub is None
                or sub.class_id is None
                or classroom is None
                or classroom.teacher_ref != teacher.teacher_ref
                or uow.enrolments.get(teacher.organization_id, sub.class_id, sub.student_ref)
                is None
            ):
                raise _submission_not_found()
        return self._concerns.raise_teacher_concern(
            teacher_ref=teacher.teacher_ref,
            student_ref=sub.student_ref,
            submission_id=sub.submission_id,
            category=category,
            text=text,
        )

    def teacher_may_raise_concern(
        self, *, teacher_ref: str, student_ref: str, submission_id: str | None
    ) -> bool:
        """Safeguarding's scope check: an ACTIVE teacher, a learner enrolled in one of that
        teacher's own classes, and (when given) a submission of that learner in one of them.

        Deliberately independent of progress_sharing: a safety channel stays open even when the
        guardian has stopped sharing progress."""
        with self._uow() as uow:
            teacher = uow.teachers.get(teacher_ref)
            if teacher is None or not teacher.can_sign_in:
                return False
            own = {
                c.class_id
                for c in uow.classrooms.for_teacher(teacher.organization_id, teacher.teacher_ref)
            }
            if not any(
                uow.enrolments.get(teacher.organization_id, class_id, student_ref)
                for class_id in own
            ):
                return False
            if submission_id is None:
                return True
            sub = uow.submissions.get(teacher.organization_id, submission_id)
            return sub is not None and sub.student_ref == student_ref and sub.class_id in own

    # ------------------------------------------------------------- reporting (read port)

    def reporting_roster(self, *, teacher_ref: str, class_id: str) -> dict[str, Any]:
        """The reporting context's view of a teacher's own class: its organization, its teacher's
        name and its current members (REPORT_CARD_CONTRACT §2). Another teacher's class, another
        organization's or an unknown one is a 404; a locked or suspended teacher a 403. Each
        member's visibility is decided live by the caller, as everywhere else."""
        with self._uow() as uow:
            teacher = self._require_teacher(uow, teacher_ref)
            classroom = self._require_own_class(uow, teacher, class_id)
            return self._roster_view(uow, teacher, classroom)

    def reporting_rosters(self, teacher_ref: str) -> list[dict[str, Any]]:
        """``reporting_roster`` for every class the teacher owns."""
        with self._uow() as uow:
            teacher = self._require_teacher(uow, teacher_ref)
            return [
                self._roster_view(uow, teacher, c)
                for c in uow.classrooms.for_teacher(teacher.organization_id, teacher.teacher_ref)
            ]

    def _roster_view(
        self, uow: SchoolUnitOfWork, teacher: Teacher, classroom: Classroom
    ) -> dict[str, Any]:
        org = uow.organizations.get(teacher.organization_id)
        members = uow.enrolments.for_class(teacher.organization_id, classroom.class_id)
        return {
            "class_id": classroom.class_id,
            "organization_id": classroom.organization_id,
            "class_name": classroom.name,
            "organization_name": org.name if org else "",
            "curriculum_pack_id": org.curriculum_pack_id if org else "",
            "teacher_name": teacher.display_name,
            "student_refs": [e.student_ref for e in members],
        }

    def marked_homework(self, student_ref: str) -> list[dict[str, Any]]:
        """Every marked submission of one learner (refs, outcome and time only — never the text
        or the feedback), for the report cards derived from it."""
        with self._uow() as uow:
            subs = uow.submissions.for_student(student_ref)
        return [
            {
                "submission_id": s.submission_id,
                "organization_id": s.organization_id,
                "class_id": s.class_id or "",
                "source": s.source.value,
                "objective_code": s.objective_code,
                "outcome": s.outcome.value,
                "marked_at": s.marked_at,
            }
            for s in subs
            if s.status is SubmissionStatus.MARKED and s.outcome is not None
        ]

    def _teacher_submission(
        self, uow: SchoolUnitOfWork, teacher_ref: str, submission_id: str
    ) -> tuple[Teacher, Submission, str]:
        """A submission in the teacher's own class of a learner they may see now (else 404)."""
        teacher = self._require_teacher(uow, teacher_ref)
        sub = uow.submissions.get(teacher.organization_id, submission_id)
        if sub is None or sub.class_id is None:  # a self-paced answer has no teacher
            raise _submission_not_found()
        classroom = uow.classrooms.get(teacher.organization_id, sub.class_id)
        if classroom is None or classroom.teacher_ref != teacher.teacher_ref:
            raise _submission_not_found()
        if uow.enrolments.get(teacher.organization_id, sub.class_id, sub.student_ref) is None:
            raise _submission_not_found()
        name = self._learners.visible_to_teacher([sub.student_ref]).get(sub.student_ref)
        if name is None:
            raise _submission_not_found()
        return teacher, sub, name

    def _ensure_evidence(self, sub: Submission) -> None:
        if self._written is None or sub.outcome is None:
            return
        self._written.record_marked(
            submission_id=sub.evidence_id,
            student_ref=sub.student_ref,
            objective_code=sub.objective_code,
            item_ref=sub.item_ref,
            met=sub.outcome is MarkOutcome.MET,
        )

    def _learner_assignment(
        self, uow: SchoolUnitOfWork, student_ref: str, assignment_id: str
    ) -> Assignment:
        for e in uow.enrolments.for_student(student_ref):
            a = uow.assignments.get(e.organization_id, assignment_id)
            if a is not None and a.class_id == e.class_id:
                return a
        raise not_found("assignment not found")

    def _lessons(self, objective_codes: set[str]) -> dict[str, WrittenLesson]:
        if self._written is None:
            return {}
        out: dict[str, WrittenLesson] = {}
        for code in sorted(objective_codes):
            lesson = self._written.lesson(code)
            if lesson is not None:
                out[code] = lesson
        return out

    def _record_submission(
        self, action: str, actor_ref: str, actor_role: str, sub: Submission
    ) -> None:
        # Refs only: the submission id names the row; its text and feedback stay out of the log.
        self._audit.record(
            SchoolAuditEvent(
                action=action,
                actor_ref=actor_ref,
                actor_role=actor_role,
                subject_ref=sub.student_ref,
                organization_id=sub.organization_id,
                class_id=sub.class_id or "",
                at=self._now(),
                object_ref=sub.submission_id,
            )
        )

    # ------------------------------------------------------------------------------ helpers

    def _visible_names(self, enrolments: list[Enrolment]) -> dict[str, str]:
        # LIVE, per request: a withdrawn progress_sharing consent hides the learner immediately.
        # One batched identity read per request, never cached across requests.
        return self._learners.visible_to_teacher([e.student_ref for e in enrolments])

    def _visible(self, enrolments: list[Enrolment]) -> list[tuple[Enrolment, str]]:
        """The enrolments the teacher may see right now, in order, with display names."""
        names = self._visible_names(enrolments)
        return [(e, names[e.student_ref]) for e in enrolments if e.student_ref in names]

    def _learner_cohort(self, student_ref: str) -> str:
        cohort_of = getattr(self._learners, "cohort_of", None)
        return str(cohort_of(student_ref)) if callable(cohort_of) else ""

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


def _learner_item_view(item: WrittenItem) -> dict[str, Any]:
    """What a learner sees of a written item: prompt, hints, length cap. No marking aid."""
    return {
        "item_ref": item.item_ref,
        "kind": "written",
        "prompt": dict(item.prompt),
        "hints": list(item.hints),
        "max_chars": item.max_chars,
    }


COMPARE_LABEL = "compare_your_answer"


def _compare_view(item: WrittenItem, sub: Submission | None) -> dict[str, Any] | None:
    """The author's sample answer / guidance for an open (``self_check``) item, shown to the
    learner only once they have submitted, labelled "compare your answer" (contract §6). None
    before submission, for an exact-key item, and when the author provided neither."""
    if sub is None or item.auto_markable or not (item.sample_answer or item.guidance):
        return None
    return {
        "label": COMPARE_LABEL,
        "sample_answer": item.sample_answer,
        "guidance": item.guidance,
    }


def _learner_homework_item(
    item: WrittenItem, source: SubmissionSource, sub: Submission | None
) -> dict[str, Any]:
    return {
        **_learner_item_view(item),
        "source": source.value,
        "marking": item.marking,
        "state": sub.status.value if sub else "not_started",
        "can_retry": sub.can_retry if sub else False,
        "submission": _learner_submission_view(sub) if sub else None,
        "compare": _compare_view(item, sub),
    }


def _learner_submit_view(sub: Submission, item: WrittenItem) -> dict[str, Any]:
    return {
        "source": sub.source.value,
        "assignment_id": sub.assignment_id,
        "objective_code": sub.objective_code,
        "item_ref": sub.item_ref,
        "marking": item.marking,
        "state": sub.status.value,
        "can_retry": sub.can_retry,
        "submission": _learner_submission_view(sub),
        "compare": _compare_view(item, sub),
    }


def _learner_submission_view(s: Submission) -> dict[str, Any]:
    """The learner's own submission. Feedback shows once the teacher returned or marked it."""
    reviewed = s.status is not SubmissionStatus.SUBMITTED
    marked = s.status is SubmissionStatus.MARKED
    return {
        "submission_id": s.submission_id,
        "state": s.status.value,
        "text": s.text,
        "attempt": s.attempt,
        "submitted_at": s.submitted_at,
        "feedback": s.feedback if reviewed else None,
        "returned_at": s.returned_at if s.status is SubmissionStatus.RETURNED else None,
        "outcome": s.outcome.value if marked and s.outcome else None,
        "score": s.score if marked else None,
        "max_score": s.max_score if marked else None,
        "marked_at": s.marked_at if marked else None,
        "reviewed_by": AUTO_REVIEWER if s.auto_marked else None,
        "can_retry": s.can_retry,
    }


def _teacher_submission_view(
    s: Submission, display_name: str, lesson: WrittenLesson | None
) -> dict[str, Any]:
    """One marking-queue row: the learner, the item with its marking aids, and the answer."""
    item = lesson.item(s.item_ref) if lesson else None
    return {
        "submission_id": s.submission_id,
        "student_ref": s.student_ref,
        "learner_display_name": display_name,
        "class_id": s.class_id,
        "assignment_id": s.assignment_id,
        "objective_code": s.objective_code,
        "lesson_title": dict(lesson.title) if lesson else {},
        "item_ref": s.item_ref,
        "prompt": dict(item.prompt) if item else {},
        "max_chars": item.max_chars if item else None,
        "rubric": item.rubric if item else None,
        "sample_answer": item.sample_answer if item else None,
        "guidance": item.guidance if item else None,
        "text": s.text,
        "state": s.status.value,
        "attempt": s.attempt,
        "outcome": s.outcome.value if s.outcome else None,
        "score": s.score,
        "max_score": s.max_score,
        "feedback": s.feedback or None,
        "submitted_at": s.submitted_at,
        "returned_at": s.returned_at,
        "marked_at": s.marked_at,
        "reviewed_by": s.reviewed_by,
    }
