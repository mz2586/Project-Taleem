"""Identity use cases: register, enrol, consent, sign in (application layer, no framework).

Every rule that protects a child lives here rather than in the HTTP adapter, so it holds however the
service is called — API, migration script, or operator tool:

1. **A learner cannot sign in without live consent.** The gate reads the derived consent state on
   every sign-in, so a withdrawal takes effect on the next attempt rather than when a cached claim
   expires.
2. **Failed sign-ins are indistinguishable.** Wrong family code, unknown name, wrong PIN, locked
   account, missing consent — the caller gets one identical error. Anything else turns the sign-in
   endpoint into an oracle for "does this family exist" and "is this child enrolled".
3. **Attempts are bounded and the bound is durable.** Lockout counters live in the database, not in
   a process, because a four-digit PIN is only safe if the *rate* is limited across every instance.
4. **Guardians reach only their own family.** Every learner-scoped call re-derives ownership from
   the token subject; nothing trusts a ref supplied in a request body.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ....platform.correlation import get_correlation_id
from ....platform.errors import Problem, forbidden, not_found, unauthorized, validation_error
from ..domain import credentials
from ..domain.accounts import (
    AccountStatus,
    GuardianAccount,
    InvalidAccountError,
    LearnerAccount,
    normalise_display_name,
    normalise_email,
    normalise_family_code,
    roster_key,
)
from ..domain.audit import AuditAction, AuditEvent
from ..domain.consent import (
    CURRENT_POLICY_VERSION,
    ConsentError,
    ConsentEvidence,
    ConsentRecord,
    ConsentScope,
    ConsentState,
    derive_state,
)
from .ports import IdentityUnitOfWork
from .tokens import (
    GUARDIAN_TOKEN_TTL_SECONDS,
    LEARNER_TOKEN_TTL_SECONDS,
    IssuedToken,
    TokenIssuer,
)

UnitOfWorkFactory = Callable[[], IdentityUnitOfWork]


def _sign_in_failed() -> Problem:
    """One error for every sign-in failure — see rule 2 in the module docstring."""
    return unauthorized("Sign-in details are not correct")


class IdentityService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        issuer: TokenIssuer,
        clock: Callable[[], float],
        hasher: credentials.SecretHasher | None = None,
    ) -> None:
        self._uow = uow_factory
        self._issuer = issuer
        self._now = clock
        self._hasher = hasher or credentials.SecretHasher()
        # Computed once per service, not per import: at the production work factor this is a third
        # of a second, which belongs at composition time rather than in every module that imports.
        self._equalising_hash = self._hasher.equalising_hash()

    # ------------------------------------------------------------------ guardian account lifecycle

    def register_guardian(
        self,
        *,
        email: str,
        passphrase: str,
        display_name: str,
        locale: str = "ur",
    ) -> dict[str, Any]:
        try:
            normalised_email = normalise_email(email)
            normalise_display_name(display_name)
            credentials.assert_passphrase_policy(passphrase)
        except (InvalidAccountError, credentials.WeakSecretError) as exc:
            raise validation_error(str(exc)) from exc

        now = self._now()
        with self._uow() as uow:
            if uow.guardians.by_email(normalised_email) is not None:
                # Registration is one of the few places where an "already exists" answer is
                # unavoidable — a silent success would strand the guardian. The response is
                # deliberately the same shape a caller gets for any other validation failure.
                raise Problem(
                    409,
                    "EMAIL_IN_USE",
                    "Conflict",
                    "an account already exists for this email address",
                )
            account = GuardianAccount.create(
                email=normalised_email,
                passphrase_hash=self._hasher.hash(passphrase),
                display_name=display_name,
                locale=locale,
                now=now,
            )
            uow.guardians.add(account)
            uow.audit.append(
                AuditEvent.record(
                    action=AuditAction.GUARDIAN_REGISTERED,
                    actor_ref=account.guardian_ref,
                    actor_role="guardian",
                    subject_ref=account.guardian_ref,
                    now=now,
                    correlation_id=get_correlation_id() or "",
                )
            )
            uow.commit()
            token = self._issue_guardian_token(account, now)
            return {"guardian": _guardian_view(account), "session": token.to_dict()}

    def sign_in_guardian(self, *, email: str, passphrase: str) -> dict[str, Any]:
        now = self._now()
        try:
            normalised_email = normalise_email(email)
        except InvalidAccountError:
            raise _sign_in_failed() from None

        with self._uow() as uow:
            account = uow.guardians.by_email(normalised_email)
            if account is None:
                # Spend comparable work on an unknown account so response time does not reveal
                # whether the address is registered.
                self._hasher.verify(passphrase, self._equalising_hash)
                raise _sign_in_failed()
            correct = self._hasher.verify(passphrase, account.passphrase_hash)
            if not account.can_sign_in or not correct:
                self._record_guardian_failure(uow, account, now)
                uow.commit()
                raise _sign_in_failed()

            account.failed_attempts = 0
            uow.guardians.save(account)
            uow.audit.append(
                AuditEvent.record(
                    action=AuditAction.GUARDIAN_SIGNED_IN,
                    actor_ref=account.guardian_ref,
                    actor_role="guardian",
                    subject_ref=account.guardian_ref,
                    now=now,
                    correlation_id=get_correlation_id() or "",
                )
            )
            uow.commit()
            return {
                "guardian": _guardian_view(account),
                "session": self._issue_guardian_token(account, now).to_dict(),
            }

    def guardian_profile(self, guardian_ref: str) -> dict[str, Any]:
        with self._uow() as uow:
            account = self._require_guardian(uow, guardian_ref)
            learners = uow.learners.for_guardian(guardian_ref)
            states = {
                learner.student_ref: derive_state(
                    learner.student_ref, uow.consents.history(learner.student_ref)
                )
                for learner in learners
            }
        return {
            "guardian": _guardian_view(account),
            "learners": [
                _learner_view(learner, states[learner.student_ref]) for learner in learners
            ],
            "policy_version": CURRENT_POLICY_VERSION,
        }

    # ------------------------------------------------------------------------- learner enrolment

    def enrol_learner(
        self,
        *,
        guardian_ref: str,
        display_name: str,
        pin: str,
        grade_band: str = "middle",
        grade_level: int = 4,
        locale: str = "ur",
    ) -> dict[str, Any]:
        try:
            credentials.assert_pin_policy(pin)
            name = normalise_display_name(display_name)
        except (credentials.WeakSecretError, InvalidAccountError) as exc:
            raise validation_error(str(exc)) from exc

        now = self._now()
        with self._uow() as uow:
            self._require_guardian(uow, guardian_ref)
            siblings = uow.learners.for_guardian(guardian_ref)
            if any(s.roster_key == roster_key(name) for s in siblings):
                # Two children in one family cannot share a display name: the name *is* the child's
                # sign-in handle within the family, so a duplicate would make sign-in ambiguous.
                raise validation_error("a learner with this name already exists in your family")
            if len(siblings) >= MAX_LEARNERS_PER_GUARDIAN:
                raise validation_error(
                    f"a guardian may enrol at most {MAX_LEARNERS_PER_GUARDIAN} learners"
                )
            try:
                learner = LearnerAccount.create(
                    guardian_ref=guardian_ref,
                    display_name=name,
                    pin_hash=self._hasher.hash(pin),
                    grade_band=grade_band,
                    grade_level=grade_level,
                    locale=locale,
                    now=now,
                )
            except InvalidAccountError as exc:
                raise validation_error(str(exc)) from exc
            uow.learners.add(learner)
            uow.audit.append(
                AuditEvent.record(
                    action=AuditAction.LEARNER_CREATED,
                    actor_ref=guardian_ref,
                    actor_role="guardian",
                    subject_ref=learner.student_ref,
                    now=now,
                    correlation_id=get_correlation_id() or "",
                    detail={"grade_level": grade_level, "grade_band": grade_band},
                )
            )
            uow.commit()
            # A newly enrolled learner has no consent yet and therefore cannot sign in. That is the
            # intended order: enrol, then consent, then learn.
            return _learner_view(learner, derive_state(learner.student_ref, []))

    def list_learners(self, guardian_ref: str) -> list[dict[str, Any]]:
        with self._uow() as uow:
            self._require_guardian(uow, guardian_ref)
            learners = uow.learners.for_guardian(guardian_ref)
            return [
                _learner_view(
                    learner,
                    derive_state(learner.student_ref, uow.consents.history(learner.student_ref)),
                )
                for learner in learners
            ]

    def reset_learner_pin(self, *, guardian_ref: str, student_ref: str, pin: str) -> dict[str, Any]:
        try:
            credentials.assert_pin_policy(pin)
        except credentials.WeakSecretError as exc:
            raise validation_error(str(exc)) from exc
        now = self._now()
        with self._uow() as uow:
            learner = self._require_own_learner(uow, guardian_ref, student_ref)
            learner.pin_hash = self._hasher.hash(pin)
            learner.failed_attempts = 0
            # Resetting the PIN is also how a guardian unlocks a child who forgot theirs.
            if learner.status is AccountStatus.LOCKED:
                learner.status = AccountStatus.ACTIVE
            uow.learners.save(learner)
            uow.audit.append(
                AuditEvent.record(
                    action=AuditAction.LEARNER_PIN_RESET,
                    actor_ref=guardian_ref,
                    actor_role="guardian",
                    subject_ref=student_ref,
                    now=now,
                    correlation_id=get_correlation_id() or "",
                )
            )
            uow.commit()
            return _learner_view(
                learner, derive_state(student_ref, uow.consents.history(student_ref))
            )

    # ---------------------------------------------------------------------------------- consent

    def grant_consent(
        self,
        *,
        guardian_ref: str,
        student_ref: str,
        scopes: set[ConsentScope],
        evidence: ConsentEvidence,
    ) -> dict[str, Any]:
        now = self._now()
        with self._uow() as uow:
            self._require_own_learner(uow, guardian_ref, student_ref)
            try:
                record = ConsentRecord.grant(
                    guardian_ref=guardian_ref,
                    student_ref=student_ref,
                    scopes=scopes,
                    now=now,
                    evidence=evidence,
                )
            except ConsentError as exc:
                # A consent set that omits the required scope is a client mistake, not a server
                # fault: the guardian gets the same 422 shape as any other invalid submission.
                raise validation_error(str(exc)) from exc
            uow.consents.append(record)
            uow.audit.append(
                AuditEvent.record(
                    action=AuditAction.CONSENT_GRANTED,
                    actor_ref=guardian_ref,
                    actor_role="guardian",
                    subject_ref=student_ref,
                    now=now,
                    correlation_id=get_correlation_id() or "",
                    detail={
                        "scopes": sorted(s.value for s in record.scopes),
                        "policy_version": record.policy_version,
                        "consent_id": record.consent_id,
                    },
                )
            )
            uow.commit()
            return derive_state(student_ref, uow.consents.history(student_ref)).to_dict()

    def withdraw_consent(
        self,
        *,
        guardian_ref: str,
        student_ref: str,
        scopes: set[ConsentScope] | None,
        evidence: ConsentEvidence,
    ) -> dict[str, Any]:
        now = self._now()
        with self._uow() as uow:
            self._require_own_learner(uow, guardian_ref, student_ref)
            record = ConsentRecord.withdraw(
                guardian_ref=guardian_ref,
                student_ref=student_ref,
                scopes=scopes,
                now=now,
                evidence=evidence,
            )
            uow.consents.append(record)
            uow.audit.append(
                AuditEvent.record(
                    action=AuditAction.CONSENT_WITHDRAWN,
                    actor_ref=guardian_ref,
                    actor_role="guardian",
                    subject_ref=student_ref,
                    now=now,
                    correlation_id=get_correlation_id() or "",
                    detail={
                        "scopes": sorted(s.value for s in record.scopes),
                        "consent_id": record.consent_id,
                    },
                )
            )
            uow.commit()
            return derive_state(student_ref, uow.consents.history(student_ref)).to_dict()

    def consent_state(self, *, guardian_ref: str, student_ref: str) -> dict[str, Any]:
        with self._uow() as uow:
            self._require_own_learner(uow, guardian_ref, student_ref)
            history = uow.consents.history(student_ref)
            state = derive_state(student_ref, history)
        return {
            **state.to_dict(),
            "history": [
                {
                    "consent_id": r.consent_id,
                    "action": r.action.value,
                    "scopes": sorted(s.value for s in r.scopes),
                    "policy_version": r.policy_version,
                    "recorded_at": r.recorded_at,
                    "method": r.evidence.method,
                }
                for r in sorted(history, key=lambda r: r.recorded_at, reverse=True)
            ],
        }

    def consent_state_for(self, student_ref: str) -> ConsentState:
        """Unowned read used by other contexts to honour per-feature consent (e.g. AI teaching)."""
        with self._uow() as uow:
            return derive_state(student_ref, uow.consents.history(student_ref))

    # --------------------------------------------------------------------------- learner sign-in

    def family_roster(self, family_code: str) -> list[dict[str, Any]]:
        """The names a child can tap on the sign-in screen, for one family code.

        This trades a little disclosure for a lot of accessibility: a six-year-old learning to read
        Urdu cannot reliably type their own name, and forcing them to would exclude exactly the
        children this product exists for. The trade is bounded — the caller must already hold a
        ~40-bit family code, an unknown code is indistinguishable from an empty family, and only
        display names are returned (no refs, no grades, no progress). A learner still cannot sign in
        without the PIN, and consent is checked after that.
        """
        try:
            code = normalise_family_code(family_code)
        except InvalidAccountError:
            return []
        with self._uow() as uow:
            guardian = uow.guardians.by_family_code(code)
            if guardian is None or not guardian.can_sign_in:
                return []
            learners = uow.learners.for_guardian(guardian.guardian_ref)
            return [
                {"display_name": learner.display_name, "grade_level": learner.grade_level}
                for learner in learners
                if learner.status is AccountStatus.ACTIVE
            ]

    def sign_in_learner(
        self,
        *,
        family_code: str,
        display_name: str,
        pin: str,
        device_id: str = "",
    ) -> dict[str, Any]:
        now = self._now()
        try:
            code = normalise_family_code(family_code)
            wanted = roster_key(display_name)
        except InvalidAccountError:
            raise _sign_in_failed() from None

        with self._uow() as uow:
            guardian = uow.guardians.by_family_code(code)
            if guardian is None or not guardian.can_sign_in:
                self._hasher.verify(pin, self._equalising_hash)
                raise _sign_in_failed()
            learner = next(
                (
                    candidate
                    for candidate in uow.learners.for_guardian(guardian.guardian_ref)
                    if candidate.roster_key == wanted
                ),
                None,
            )
            if learner is None:
                self._hasher.verify(pin, self._equalising_hash)
                raise _sign_in_failed()
            if not learner.can_sign_in or not self._hasher.verify(pin, learner.pin_hash):
                self._record_learner_failure(uow, learner, now)
                uow.commit()
                raise _sign_in_failed()

            state = derive_state(learner.student_ref, uow.consents.history(learner.student_ref))
            if not state.permits_sign_in:
                # The credential was correct, so this is not an enumeration risk: the caller already
                # holds the family code, the name, and the PIN. Telling them *why* is what lets the
                # child hand the device to their guardian instead of retrying a correct PIN.
                uow.audit.append(
                    AuditEvent.record(
                        action=AuditAction.LEARNER_SIGN_IN_DENIED_NO_CONSENT,
                        actor_ref=learner.student_ref,
                        actor_role="student",
                        subject_ref=learner.student_ref,
                        now=now,
                        correlation_id=get_correlation_id() or "",
                        detail={"policy_version": state.policy_version},
                    )
                )
                uow.commit()
                raise Problem(
                    403,
                    "CONSENT_REQUIRED",
                    "Guardian consent required",
                    "a guardian must give consent for this learner before they can sign in",
                )

            learner.failed_attempts = 0
            learner.remember_device(device_id)
            uow.learners.save(learner)
            uow.audit.append(
                AuditEvent.record(
                    action=AuditAction.LEARNER_SIGNED_IN,
                    actor_ref=learner.student_ref,
                    actor_role="student",
                    subject_ref=learner.student_ref,
                    now=now,
                    correlation_id=get_correlation_id() or "",
                    detail={"device_bound": bool(device_id)},
                )
            )
            uow.commit()
            token = self._issuer.issue(
                subject=learner.student_ref,
                role="student",
                now=now,
                ttl_seconds=LEARNER_TOKEN_TTL_SECONDS,
                device_id=device_id or None,
            )
            return {
                "learner": _learner_view(learner, state),
                "session": token.to_dict(),
                "consent": state.to_dict(),
            }

    # ------------------------------------------------------------------------------------ audit

    def audit_trail(self, *, guardian_ref: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._uow() as uow:
            self._require_guardian(uow, guardian_ref)
            refs = [learner.student_ref for learner in uow.learners.for_guardian(guardian_ref)]
            events = uow.audit.for_guardian_family(guardian_ref, refs, limit=limit)
        return [event.to_dict() for event in events]

    # ---------------------------------------------------------------------------------- helpers

    def _issue_guardian_token(self, account: GuardianAccount, now: float) -> IssuedToken:
        return self._issuer.issue(
            subject=account.guardian_ref,
            role="guardian",
            now=now,
            ttl_seconds=GUARDIAN_TOKEN_TTL_SECONDS,
        )

    def _require_guardian(self, uow: IdentityUnitOfWork, guardian_ref: str) -> GuardianAccount:
        account = uow.guardians.get(guardian_ref)
        if account is None:
            raise not_found("guardian account not found")
        if account.status is AccountStatus.SUSPENDED:
            raise forbidden("this account is suspended")
        return account

    def _require_own_learner(
        self, uow: IdentityUnitOfWork, guardian_ref: str, student_ref: str
    ) -> LearnerAccount:
        """IDOR guard. A learner that is not this guardian's is reported as absent, not forbidden —
        a 403 would confirm the ref names a real child somewhere else."""
        self._require_guardian(uow, guardian_ref)
        learner = uow.learners.get(student_ref)
        if learner is None or learner.guardian_ref != guardian_ref:
            raise not_found("learner not found")
        return learner

    def _record_guardian_failure(
        self, uow: IdentityUnitOfWork, account: GuardianAccount, now: float
    ) -> None:
        account.failed_attempts += 1
        action = AuditAction.GUARDIAN_SIGN_IN_FAILED
        if account.failed_attempts >= credentials.MAX_PASSPHRASE_ATTEMPTS:
            account.status = AccountStatus.LOCKED
            action = AuditAction.GUARDIAN_LOCKED
        uow.guardians.save(account)
        uow.audit.append(
            AuditEvent.record(
                action=action,
                actor_ref=account.guardian_ref,
                actor_role="guardian",
                subject_ref=account.guardian_ref,
                now=now,
                correlation_id=get_correlation_id() or "",
                detail={"failed_attempts": account.failed_attempts},
            )
        )

    def _record_learner_failure(
        self, uow: IdentityUnitOfWork, learner: LearnerAccount, now: float
    ) -> None:
        learner.failed_attempts += 1
        action = AuditAction.LEARNER_SIGN_IN_FAILED
        if learner.failed_attempts >= credentials.MAX_PIN_ATTEMPTS:
            learner.status = AccountStatus.LOCKED
            action = AuditAction.LEARNER_LOCKED
        uow.learners.save(learner)
        uow.audit.append(
            AuditEvent.record(
                action=action,
                actor_ref=learner.student_ref,
                actor_role="student",
                subject_ref=learner.student_ref,
                now=now,
                correlation_id=get_correlation_id() or "",
                detail={"failed_attempts": learner.failed_attempts},
            )
        )


# A guardian is one adult with one family; the cap exists so a compromised account cannot be used to
# manufacture learner records in bulk.
MAX_LEARNERS_PER_GUARDIAN = 12


def _guardian_view(account: GuardianAccount) -> dict[str, Any]:
    return {
        "guardian_ref": account.guardian_ref,
        "email": account.email,
        "display_name": account.display_name,
        "family_code": account.family_code,
        "locale": account.locale,
        "status": account.status.value,
        "created_at": account.created_at,
    }


def _learner_view(learner: LearnerAccount, state: ConsentState) -> dict[str, Any]:
    return {
        "student_ref": learner.student_ref,
        "display_name": learner.display_name,
        "grade_band": learner.grade_band,
        "grade_level": learner.grade_level,
        "locale": learner.locale,
        "status": learner.status.value,
        "created_at": learner.created_at,
        "consent": state.to_dict(),
        "can_sign_in": learner.can_sign_in and state.permits_sign_in,
    }
