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
5. **A forgotten passphrase is recoverable without email** — with a one-time recovery code
   (domain/recovery.py). Recovery fails with the same ``401`` as sign-in for every cause, has its
   own durable lockout, and ends every existing guardian session.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ....platform.cohort import COHORTS
from ....platform.correlation import get_correlation_id
from ....platform.errors import Problem, forbidden, not_found, unauthorized, validation_error
from ..domain import credentials, recovery
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
from ..domain.sessions import REFRESH_TOKEN_TTL_SECONDS, RefreshToken, RefreshTokenError
from ..domain.sessions import split as split_refresh_token
from .ports import IdentityUnitOfWork
from .tokens import (
    GUARDIAN_TOKEN_TTL_SECONDS,
    LEARNER_TOKEN_TTL_SECONDS,
    IssuedToken,
    TokenIssuer,
)

UnitOfWorkFactory = Callable[[], IdentityUnitOfWork]

# Roles whose session continuity identity implements itself; nothing may re-register them.
_BUILT_IN_SESSION_ROLES = frozenset({"student", "guardian"})


@dataclass(frozen=True)
class SessionSubject:
    """How identity's refresh flow continues a session for a role another component owns.

    ``is_active(subject_ref)`` is consulted on **every** refresh — return ``False`` for an
    unknown, suspended or locked subject, or one that no longer holds this role, and the refresh
    fails with the uniform ``401``. ``issue_access(subject_ref, now)`` mints the access token
    (role and subject must come from the owner's stored record, never from the refresh request).
    ``profile(subject_ref)`` optionally adds ``{key: view}`` to the response.
    ``refresh_ttl_seconds`` is the idle lifetime of each token in the chain.
    """

    is_active: Callable[[str], bool]
    issue_access: Callable[[str, float], IssuedToken]
    profile: Callable[[str], dict[str, Any]] | None = None
    refresh_ttl_seconds: int = REFRESH_TOKEN_TTL_SECONDS


def _invalid(code: str, detail: str, field: str = "") -> Problem:
    """A 422 with a stable, machine-readable reason (identity.openapi.yaml ``ValidationProblem``).

    The top-level ``code`` stays ``VALIDATION_FAILED`` for compatibility; the refinement is the
    single entry in ``errors``: ``{"code": <REASON>, "field": <request field>, "message": ...}``.
    """
    entry = {"code": code, "message": detail}
    if field:
        entry["field"] = field
    return validation_error(detail, errors=[entry])


def _invalid_from(exc: InvalidAccountError | credentials.WeakSecretError) -> Problem:
    return _invalid(exc.code, str(exc), exc.field)


def _duplicate_name() -> Problem:
    return _invalid(
        "DUPLICATE_LEARNER_NAME",
        "a learner with this name already exists in your family",
        "displayName",
    )


def _sign_in_failed() -> Problem:
    """One error for every sign-in failure — see rule 2 in the module docstring."""
    return unauthorized("Sign-in details are not correct")


def _recovery_failed() -> Problem:
    """One error for every recovery failure: unknown email, wrong / used / malformed code, locked
    recovery, suspended account. Same status and detail as a failed sign-in."""
    return unauthorized("Sign-in details are not correct")


def _passphrase_incorrect() -> Problem:
    """The current passphrase did not verify on an authenticated route. A 403, not a 401: the token
    is fine, and a 401 would make a client refresh and resubmit (counting the failure twice)."""
    return Problem(
        403,
        "PASSPHRASE_INCORRECT",
        "Passphrase is not correct",
        "the current passphrase is not correct",
    )


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
        # Recovery codes carry ~59 bits, so they take a lower work factor (domain/recovery.py) — but
        # never higher than the injected hasher's, so a test's fast factor stays fast.
        self._code_hasher = credentials.SecretHasher(
            iterations=min(self._hasher.iterations, recovery.RECOVERY_CODE_ITERATIONS)
        )
        self._equalising_code_hash = self._code_hasher.equalising_hash()
        self._session_subjects: dict[str, SessionSubject] = {}

    # ------------------------------------------------------------ sessions for other components

    def register_session_subject(
        self,
        role: str,
        *,
        is_active: Callable[[str], bool],
        issue_access: Callable[[str, float], IssuedToken],
        profile: Callable[[str], dict[str, Any]] | None = None,
        refresh_ttl_seconds: int = REFRESH_TOKEN_TTL_SECONDS,
    ) -> None:
        """Let identity's rotating refresh tokens carry sessions for a role it does not own.

        Rotation, single use, replay-revokes-the-family, device binding and sign-out apply
        unchanged; the owner supplies only the live "may this subject continue" check and the
        token minting.
        ``student`` and ``guardian`` are built in and cannot be re-registered, and a role can be
        registered once (a second registration is a wiring bug, so it raises).
        """
        if not role or role in _BUILT_IN_SESSION_ROLES:
            raise ValueError(f"role {role!r} cannot be registered as a session subject")
        if role in self._session_subjects:
            raise ValueError(f"session subject role {role!r} is already registered")
        if refresh_ttl_seconds <= 0:
            raise ValueError("refresh_ttl_seconds must be positive")
        self._session_subjects[role] = SessionSubject(
            is_active=is_active,
            issue_access=issue_access,
            profile=profile,
            refresh_ttl_seconds=refresh_ttl_seconds,
        )

    def issue_refresh_token(self, subject_ref: str, role: str, device_id: str = "") -> str:
        """Open a new refresh chain for a registered role (call after a successful sign-in).

        Returns the wire form, handed to the client once; only its digest is stored. Refuses a role
        nobody registered, so a component cannot mint chains that refresh could never honour.
        """
        registered = self._session_subjects.get(role)
        if registered is None:
            raise ValueError(f"role {role!r} is not a registered session subject")
        now = self._now()
        with self._uow() as uow:
            wire = self._mint_refresh(
                uow, subject_ref, role, device_id, now, ttl_seconds=registered.refresh_ttl_seconds
            )
            uow.commit()
        return wire

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
            raise _invalid_from(exc) from exc

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
            codes = self._issue_recovery_codes(uow, account.guardian_ref, now)
            status = recovery.recovery_status(uow.recovery_codes.for_guardian(account.guardian_ref))
            refresh = self._mint_refresh(uow, account.guardian_ref, "guardian", "", now)
            uow.commit()
            token = self._issue_guardian_token(account, now)
            return {
                "guardian": _guardian_view(account),
                "session": token.to_dict(),
                "refresh_token": refresh,
                # Shown once: the plaintext exists only in this response.
                "recovery_codes": codes,
                "recovery": status,
            }

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
            refresh = self._mint_refresh(uow, account.guardian_ref, "guardian", "", now)
            uow.commit()
            return {
                "guardian": _guardian_view(account),
                "session": self._issue_guardian_token(account, now).to_dict(),
                "refresh_token": refresh,
            }

    def guardian_profile(self, guardian_ref: str) -> dict[str, Any]:
        with self._uow() as uow:
            account = self._require_guardian(uow, guardian_ref)
            status = recovery.recovery_status(uow.recovery_codes.for_guardian(guardian_ref))
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
            "recovery": status,
        }

    # -------------------------------------------------------------------------- recovery codes

    def regenerate_recovery_codes(self, *, guardian_ref: str, passphrase: str) -> dict[str, Any]:
        """A new set of codes for the acting guardian; the previous set stops working at once.

        Requires the current passphrase — a stolen access token alone must not be enough to mint
        the credential that resets the passphrase. A wrong one counts towards the sign-in lockout.
        """
        now = self._now()
        with self._uow() as uow:
            account = self._require_guardian(uow, guardian_ref)
            if not account.can_sign_in or not self._hasher.verify(
                passphrase, account.passphrase_hash
            ):
                self._record_guardian_failure(uow, account, now)
                uow.commit()
                raise _passphrase_incorrect()
            account.failed_attempts = 0
            account.recovery_failed_attempts = 0
            uow.guardians.save(account)
            codes = self._issue_recovery_codes(uow, guardian_ref, now)
            status = recovery.recovery_status(uow.recovery_codes.for_guardian(guardian_ref))
            uow.commit()
            return {"recovery_codes": codes, "recovery": status}

    def recover_guardian(self, *, email: str, code: str, new_passphrase: str) -> dict[str, Any]:
        """Set a new passphrase with one recovery code, and sign the guardian in.

        Every failure — unknown email, malformed / wrong / used code, recovery locked, account
        suspended — is the same ``401`` and costs the same KDF work. Only the new passphrase's
        *policy* is reported (``422``), and it is checked before any account is looked up, so it
        says nothing about the account. On success the code is consumed, both attempt counters
        reset, a passphrase lockout lifts (an operator suspension does not), and every existing
        guardian session is revoked before a new one is issued.
        """
        try:
            credentials.assert_passphrase_policy(new_passphrase)
        except credentials.WeakSecretError as exc:
            raise _invalid_from(exc) from exc
        now = self._now()
        try:
            normalised_email = normalise_email(email)
            presented = recovery.normalise_recovery_code(code)
        except (InvalidAccountError, recovery.InvalidRecoveryCodeError):
            self._match_recovery_code("", [])
            raise _recovery_failed() from None

        with self._uow() as uow:
            account = uow.guardians.by_email(normalised_email)
            if account is None:
                self._match_recovery_code(presented, [])
                raise _recovery_failed()
            stored = uow.recovery_codes.for_guardian(account.guardian_ref)
            match = self._match_recovery_code(presented, [c for c in stored if c.usable])
            # Never gated on failed recovery attempts: that would let anyone who knows the email
            # disable a guardian's recovery. Guessing is bounded by the per-account and
            # per-client rate limits and ~59-bit codes; a suspension still blocks recovery.
            eligible = account.status in (AccountStatus.ACTIVE, AccountStatus.LOCKED)
            if match is None or not eligible:
                self._record_recovery_failure(uow, account, now)
                uow.commit()
                raise _recovery_failed()

            match.consume(now)
            uow.recovery_codes.save(match)
            account.passphrase_hash = self._hasher.hash(new_passphrase)
            account.failed_attempts = 0
            account.recovery_failed_attempts = 0
            if account.status is AccountStatus.LOCKED:
                account.status = AccountStatus.ACTIVE
            uow.guardians.save(account)
            # A new passphrase must end every session opened with the old one — the reason someone
            # recovers may be that another person has their account.
            revoked = uow.refresh_tokens.revoke_all_for(account.guardian_ref, now=now)
            status = recovery.recovery_status(stored)  # ``match`` is one of these, now consumed
            uow.audit.append(
                AuditEvent.record(
                    action=AuditAction.GUARDIAN_RECOVERED,
                    actor_ref=account.guardian_ref,
                    actor_role="guardian",
                    subject_ref=account.guardian_ref,
                    now=now,
                    correlation_id=get_correlation_id() or "",
                    detail={"revoked_sessions": revoked, "codes_remaining": status["remaining"]},
                )
            )
            refresh = self._mint_refresh(uow, account.guardian_ref, "guardian", "", now)
            uow.commit()
            return {
                "guardian": _guardian_view(account),
                "session": self._issue_guardian_token(account, now).to_dict(),
                "refresh_token": refresh,
                "recovery": status,
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
            raise _invalid_from(exc) from exc

        now = self._now()
        with self._uow() as uow:
            guardian = self._require_guardian(uow, guardian_ref)
            siblings = uow.learners.for_guardian(guardian_ref)
            if any(s.roster_key == roster_key(name) for s in siblings):
                # Two children in one family cannot share a display name: the name *is* the child's
                # sign-in handle within the family, so a duplicate would make sign-in ambiguous.
                raise _duplicate_name()
            if len(siblings) >= MAX_LEARNERS_PER_GUARDIAN:
                raise _invalid(
                    "LEARNER_LIMIT_REACHED",
                    f"a guardian may enrol at most {MAX_LEARNERS_PER_GUARDIAN} learners",
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
                    cohort=guardian.cohort,  # a learner's cohort is its guardian's
                )
            except InvalidAccountError as exc:
                raise _invalid_from(exc) from exc
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
            raise _invalid_from(exc) from exc
        now = self._now()
        with self._uow() as uow:
            learner = self._require_own_learner(uow, guardian_ref, student_ref)
            learner.pin_hash = self._hasher.hash(pin)
            learner.failed_attempts = 0
            # Resetting the PIN is also how a guardian unlocks a child who forgot theirs.
            if learner.status is AccountStatus.LOCKED:
                learner.status = AccountStatus.ACTIVE
            uow.learners.save(learner)
            # Changing the credential ends sessions opened with the old one — otherwise a device a
            # guardian was trying to lock out would keep refreshing indefinitely.
            uow.refresh_tokens.revoke_all_for(student_ref, now=now)
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

    def rename_learner(
        self, *, guardian_ref: str, student_ref: str, display_name: str
    ) -> dict[str, Any]:
        """Change a learner's display name — the only field this route touches.

        The name is the child's sign-in handle within the family, so it stays unique there. The
        audit entry records *that* the name changed, never the old or new name: the trail must not
        become a second copy of a child's identifying data.
        """
        try:
            name = normalise_display_name(display_name)
        except InvalidAccountError as exc:
            raise _invalid_from(exc) from exc
        now = self._now()
        with self._uow() as uow:
            learner = self._require_own_learner(uow, guardian_ref, student_ref)
            if name != learner.display_name:
                key = roster_key(name)
                siblings = uow.learners.for_guardian(guardian_ref)
                if any(s.roster_key == key and s.student_ref != student_ref for s in siblings):
                    raise _duplicate_name()
                learner.display_name = name
                uow.learners.save(learner)
                uow.audit.append(
                    AuditEvent.record(
                        action=AuditAction.LEARNER_RENAMED,
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

    def suspend_learner(self, *, guardian_ref: str, student_ref: str) -> dict[str, Any]:
        """A guardian pauses their child's account: sign-in stops and every live session ends.

        Idempotent. An account an operator has ``suspended`` stays operator-suspended (the guardian
        cannot downgrade a safeguarding hold into something they can lift themselves).
        """
        now = self._now()
        with self._uow() as uow:
            learner = self._require_own_learner(uow, guardian_ref, student_ref)
            # Revoke regardless of the prior state: "stop" has to mean every device, now.
            revoked = uow.refresh_tokens.revoke_all_for(student_ref, now=now)
            changed = learner.status not in (AccountStatus.PAUSED, AccountStatus.SUSPENDED)
            if changed:
                learner.status = AccountStatus.PAUSED
                uow.learners.save(learner)
            if changed or revoked:
                uow.audit.append(
                    AuditEvent.record(
                        action=AuditAction.LEARNER_SUSPENDED,
                        actor_ref=guardian_ref,
                        actor_role="guardian",
                        subject_ref=student_ref,
                        now=now,
                        correlation_id=get_correlation_id() or "",
                        detail={"revoked_sessions": revoked},
                    )
                )
            uow.commit()
            return _learner_view(
                learner, derive_state(student_ref, uow.consents.history(student_ref))
            )

    def reinstate_learner(self, *, guardian_ref: str, student_ref: str) -> dict[str, Any]:
        """Lift a guardian's own suspension. Idempotent for a learner that is not paused.

        Reinstating also clears the failed-attempt counter: it is the same guardian authority that a
        PIN reset uses to unlock a child. Consent is untouched — a learner without it still cannot
        sign in. An operator suspension cannot be lifted here (409).
        """
        now = self._now()
        with self._uow() as uow:
            learner = self._require_own_learner(uow, guardian_ref, student_ref)
            if learner.status is AccountStatus.SUSPENDED:
                raise Problem(
                    409,
                    "LEARNER_SUSPENDED_BY_OPERATOR",
                    "Suspended by an operator",
                    "this learner was suspended by an operator and cannot be reinstated here",
                )
            if learner.status is AccountStatus.PAUSED:
                learner.status = AccountStatus.ACTIVE
                learner.failed_attempts = 0
                uow.learners.save(learner)
                uow.audit.append(
                    AuditEvent.record(
                        action=AuditAction.LEARNER_REINSTATED,
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
                raise _invalid("CONSENT_SCOPE_REQUIRED", str(exc), "scopes") from exc
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
            # A withdrawal that no longer permits sign-in ends every live session for this learner
            # now, rather than waiting for an access token to expire. "Stop" has to mean stop.
            remaining = derive_state(student_ref, [*uow.consents.history(student_ref)])
            if not remaining.permits_sign_in:
                uow.refresh_tokens.revoke_all_for(student_ref, now=now)
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

    def portal_links(self, guardian_ref: str) -> tuple[str, list[str]] | None:
        """The learners a guardian may see in the Guardian Portal, read for another context.

        Returns ``(guardian display name, student refs)``, or ``None`` when there is no such
        guardian or the account is suspended. A learner is included only while it belongs to this
        guardian, is not suspended, and holds live, current-policy consent for ``learning_data`` —
        the scope under which a progress record exists at all. Withdrawing it removes the child
        from the portal on the next request; nothing is cached. (``progress_sharing`` governs
        sharing with a mentor or teacher, not the consenting guardian's own view.) A *locked*
        learner stays visible: a forgotten PIN is exactly when a guardian needs to see the account.
        """
        with self._uow() as uow:
            account = uow.guardians.get(guardian_ref)
            if account is None or account.status is AccountStatus.SUSPENDED:
                return None
            refs = [
                learner.student_ref
                for learner in uow.learners.for_guardian(guardian_ref)
                if learner.status is not AccountStatus.SUSPENDED
                and derive_state(
                    learner.student_ref, uow.consents.history(learner.student_ref)
                ).allows(ConsentScope.LEARNING_DATA)
            ]
        return account.display_name, refs

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
            refresh = self._mint_refresh(uow, learner.student_ref, "student", device_id, now)
            uow.commit()
            token = self._issuer.issue(
                subject=learner.student_ref,
                role="student",
                now=now,
                ttl_seconds=LEARNER_TOKEN_TTL_SECONDS,
                device_id=device_id or None,
                cohort=learner.cohort,
            )
            return {
                "learner": _learner_view(learner, state),
                "session": token.to_dict(),
                "consent": state.to_dict(),
                "refresh_token": refresh,
            }

    # --------------------------------------------------------------------------------- sessions

    def refresh_session(self, *, refresh_token: str, device_id: str = "") -> dict[str, Any]:
        """Exchange a refresh token for a new access token and a successor refresh token.

        Every gate that applied at sign-in is re-run here — account status and, for a learner, the
        derived consent state — so session continuity never outlives permission. That is what keeps
        the ten-minute access token an honest bound rather than a formality.
        """
        now = self._now()
        try:
            token_id, secret = split_refresh_token(refresh_token)
        except RefreshTokenError:
            raise _sign_in_failed() from None

        with self._uow() as uow:
            record = uow.refresh_tokens.get(token_id)
            if record is None or not record.matches(secret):
                raise _sign_in_failed()

            if record.consumed_at is not None:
                # Reuse. The legitimate holder and a thief hold members of the same chain and are
                # indistinguishable, so the whole family goes (OAuth 2.0 BCP 4.14.2).
                revoked = uow.refresh_tokens.revoke_family(record.family_id, now=now)
                uow.audit.append(
                    AuditEvent.record(
                        action=AuditAction.SESSION_REUSE_DETECTED,
                        actor_ref=record.subject_ref,
                        actor_role=record.role,
                        subject_ref=record.subject_ref,
                        now=now,
                        correlation_id=get_correlation_id() or "",
                        detail={"revoked_sessions": revoked},
                    )
                )
                uow.commit()
                raise _sign_in_failed()

            if not record.is_usable(now, device_id):
                raise _sign_in_failed()

            if record.role == "student":
                learner = uow.learners.get(record.subject_ref)
                if learner is None or not learner.can_sign_in:
                    raise _sign_in_failed()
                state = derive_state(learner.student_ref, uow.consents.history(learner.student_ref))
                if not state.permits_sign_in:
                    # Consent went away while the session was live. Kill every session for this
                    # learner rather than only this chain: a guardian pressing stop means stop.
                    uow.refresh_tokens.revoke_all_for(learner.student_ref, now=now)
                    uow.audit.append(
                        AuditEvent.record(
                            action=AuditAction.LEARNER_SIGN_IN_DENIED_NO_CONSENT,
                            actor_ref=learner.student_ref,
                            actor_role="student",
                            subject_ref=learner.student_ref,
                            now=now,
                            correlation_id=get_correlation_id() or "",
                            detail={"on": "refresh"},
                        )
                    )
                    uow.commit()
                    raise Problem(
                        403,
                        "CONSENT_REQUIRED",
                        "Guardian consent required",
                        "a guardian must give consent for this learner before they can sign in",
                    )
                access = self._issuer.issue(
                    subject=learner.student_ref,
                    role="student",
                    now=now,
                    ttl_seconds=LEARNER_TOKEN_TTL_SECONDS,
                    device_id=record.device_id or None,
                    cohort=learner.cohort,
                )
                payload: dict[str, Any] = {
                    "learner": _learner_view(learner, state),
                    "consent": state.to_dict(),
                }
            elif record.role in self._session_subjects:
                # A role another component owns (e.g. Studio staff). Its live check runs on every
                # refresh; the token it mints carries the role the chain was opened with.
                registered = self._session_subjects[record.role]
                if not registered.is_active(record.subject_ref):
                    raise _sign_in_failed()
                access = registered.issue_access(record.subject_ref, now)
                if access.role != record.role or access.subject != record.subject_ref:
                    raise _sign_in_failed()  # an owner may never widen or move a session
                payload = registered.profile(record.subject_ref) if registered.profile else {}
            elif record.role == "guardian":
                guardian = uow.guardians.get(record.subject_ref)
                if guardian is None or not guardian.can_sign_in:
                    raise _sign_in_failed()
                access = self._issue_guardian_token(guardian, now)
                payload = {"guardian": _guardian_view(guardian)}
            else:
                raise _sign_in_failed()

            record.consume(now)
            uow.refresh_tokens.save(record)
            successor = self._mint_refresh(
                uow,
                record.subject_ref,
                record.role,
                record.device_id,
                now,
                family_id=record.family_id,
                ttl_seconds=(
                    self._session_subjects[record.role].refresh_ttl_seconds
                    if record.role in self._session_subjects
                    else REFRESH_TOKEN_TTL_SECONDS
                ),
            )
            uow.audit.append(
                AuditEvent.record(
                    action=AuditAction.SESSION_REFRESHED,
                    actor_ref=record.subject_ref,
                    actor_role=record.role,
                    subject_ref=record.subject_ref,
                    now=now,
                    correlation_id=get_correlation_id() or "",
                )
            )
            uow.commit()
            return {**payload, "session": access.to_dict(), "refresh_token": successor}

    def sign_out(self, *, refresh_token: str) -> dict[str, Any]:
        """End one session. Idempotent, and silent about tokens it does not recognise — signing out
        must never become a way to probe whether a token was ever valid."""
        now = self._now()
        try:
            token_id, secret = split_refresh_token(refresh_token)
        except RefreshTokenError:
            return {"signed_out": True}
        with self._uow() as uow:
            record = uow.refresh_tokens.get(token_id)
            if record is None or not record.matches(secret):
                return {"signed_out": True}
            revoked = uow.refresh_tokens.revoke_family(record.family_id, now=now)
            uow.audit.append(
                AuditEvent.record(
                    action=AuditAction.SESSION_SIGNED_OUT,
                    actor_ref=record.subject_ref,
                    actor_role=record.role,
                    subject_ref=record.subject_ref,
                    now=now,
                    correlation_id=get_correlation_id() or "",
                    detail={"revoked_sessions": revoked},
                )
            )
            uow.commit()
            return {"signed_out": True}

    # ---------------------------------------------------------------------------- demo cohort

    def assign_family_cohort(self, *, guardian_ref: str, cohort: str) -> int:
        """Set the cohort of a guardian and all their learners (DEMO_COHORT_CONTRACT §2).

        **Not exposed by any HTTP route**: the only caller is the demo seeder
        (``tools/demo_cohort.py``). Returns the number of accounts changed (0 = already set).
        """
        if cohort not in COHORTS:
            raise ValueError(f"unknown cohort {cohort!r}")
        with self._uow() as uow:
            if uow.guardians.get(guardian_ref) is None:
                raise not_found("guardian account not found")
            changed = uow.guardians.set_family_cohort(guardian_ref, cohort)
            if changed:
                uow.audit.append(
                    AuditEvent.record(
                        action=AuditAction.COHORT_ASSIGNED,
                        actor_ref="system:demo-seed",
                        actor_role="system",
                        subject_ref=guardian_ref,
                        now=self._now(),
                        correlation_id=get_correlation_id() or "",
                        detail={"cohort": cohort, "accounts": changed},
                    )
                )
            uow.commit()
        return changed

    def guardian_cohort(self, guardian_ref: str) -> str:
        """The guardian account's cohort ("" when there is no such account)."""
        with self._uow() as uow:
            account = uow.guardians.get(guardian_ref)
        return account.cohort if account is not None else ""

    def learner_cohort(self, student_ref: str) -> str:
        """The learner account's cohort ("" when there is no such account)."""
        with self._uow() as uow:
            account = uow.learners.get(student_ref)
        return account.cohort if account is not None else ""

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
            cohort=account.cohort,
        )

    def _mint_refresh(
        self,
        uow: IdentityUnitOfWork,
        subject_ref: str,
        role: str,
        device_id: str,
        now: float,
        *,
        family_id: str | None = None,
        ttl_seconds: int = REFRESH_TOKEN_TTL_SECONDS,
    ) -> str:
        record, wire = RefreshToken.issue(
            subject_ref=subject_ref,
            role=role,
            device_id=device_id,
            now=now,
            family_id=family_id,
            ttl_seconds=ttl_seconds,
        )
        uow.refresh_tokens.add(record)
        return wire

    def _issue_recovery_codes(
        self, uow: IdentityUnitOfWork, guardian_ref: str, now: float
    ) -> list[str]:
        """Replace the guardian's set; return the plaintext codes (the only time they exist)."""
        codes = recovery.new_recovery_codes()
        invalidated = uow.recovery_codes.replace_for(
            guardian_ref,
            [
                recovery.RecoveryCode.create(
                    guardian_ref=guardian_ref, code_hash=self._code_hasher.hash(code), now=now
                )
                for code in codes
            ],
        )
        uow.audit.append(
            AuditEvent.record(
                action=AuditAction.GUARDIAN_RECOVERY_CODES_GENERATED,
                actor_ref=guardian_ref,
                actor_role="guardian",
                subject_ref=guardian_ref,
                now=now,
                correlation_id=get_correlation_id() or "",
                detail={"count": len(codes), "invalidated": invalidated},
            )
        )
        return codes

    def _match_recovery_code(
        self, presented: str, usable: list[recovery.RecoveryCode]
    ) -> recovery.RecoveryCode | None:
        """Check ``presented`` against every slot of a full set, without stopping early.

        Always ``RECOVERY_CODE_COUNT`` verifications (padded with a placeholder digest), so the time
        taken says nothing about whether the account exists or how many codes it has left.
        """
        slots: list[recovery.RecoveryCode | None] = [*usable]
        slots += [None] * max(0, recovery.RECOVERY_CODE_COUNT - len(slots))
        match: recovery.RecoveryCode | None = None
        for slot in slots:
            digest = slot.code_hash if slot is not None else self._equalising_code_hash
            if self._code_hasher.verify(presented, digest) and slot is not None and match is None:
                match = slot
        return match

    def _record_recovery_failure(
        self, uow: IdentityUnitOfWork, account: GuardianAccount, now: float
    ) -> None:
        account.recovery_failed_attempts += 1
        action = AuditAction.GUARDIAN_RECOVERY_FAILED
        if account.recovery_failed_attempts >= recovery.MAX_RECOVERY_ATTEMPTS:
            # Recorded for review/alerting only. The account is NOT locked: a recovery lockout
            # is a denial-of-service lever for anyone who knows the guardian's email, and the
            # rate limits already make code guessing infeasible.
            action = AuditAction.GUARDIAN_RECOVERY_LOCKED
        uow.guardians.save(account)
        uow.audit.append(
            AuditEvent.record(
                action=action,
                actor_ref=account.guardian_ref,
                actor_role="guardian",
                subject_ref=account.guardian_ref,
                now=now,
                correlation_id=get_correlation_id() or "",
                detail={"failed_attempts": account.recovery_failed_attempts},
            )
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
        # Only an active account becomes locked: overwriting ``suspended`` with ``locked`` would let
        # an unlock path (a PIN or passphrase reset) lift a suspension it has no authority over.
        if (
            account.failed_attempts >= credentials.MAX_PASSPHRASE_ATTEMPTS
            and account.status is AccountStatus.ACTIVE
        ):
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
        # Same rule as for guardians: a paused or suspended learner stays paused or suspended, or a
        # PIN reset (which unlocks) would become a way round the guardian's or operator's hold.
        if (
            learner.failed_attempts >= credentials.MAX_PIN_ATTEMPTS
            and learner.status is AccountStatus.ACTIVE
        ):
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
