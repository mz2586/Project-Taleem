"""Curriculum Studio staff accounts: operator provisioning and passphrase sign-in.

Rules this service holds, and why:

1. **An operator provisions; nobody self-registers.** ``system`` creates a staff account with
   exactly one Studio role. There is no route by which a staff account changes its own role, and the
   repository never rewrites ``role``.
2. **A staff token carries only that role.** Issuance reads the role from the stored account, never
   from a request, and the domain plus a database CHECK limit it to ``STAFF_ROLES``. A staff account
   can therefore never obtain a learner, guardian, teacher, mentor or operator token.
3. **One person, one subject.** The token subject is the account's ``staff_ref``. The Studio blocks
   self-approval by subject, so the subject must be stable and must not be shared.
4. **Sign-in fails uniformly** (one 401 for every cause, with equalised work for an unknown
   address), and ten wrong passphrases lock the account durably. Only an operator unlocks.
5. **Suspension is immediate.** Suspending revokes every refresh family, and the per-request staff
   gate (``staff_refusal``) refuses the still-unexpired access token on its next Studio request.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any, Protocol

from ....platform.correlation import get_correlation_id
from ....platform.errors import Problem, conflict, not_found, unauthorized, validation_error
from ..domain import credentials
from ..domain.accounts import AccountStatus, InvalidAccountError, normalise_email
from ..domain.audit import AuditAction, AuditEvent
from ..domain.staff import STAFF_ROLES, StaffAccount
from .ports import IdentityUnitOfWork
from .tokens import IssuedToken, TokenIssuer

# A reviewer works in sessions of an hour; the refresh chain keeps them signed in through a working
# day and lapses after twelve idle hours, much shorter than a family device's thirty days.
STAFF_TOKEN_TTL_SECONDS = 60 * 60
STAFF_REFRESH_TTL_SECONDS = 12 * 60 * 60

STAFF_INACTIVE = "STAFF_INACTIVE"


def _sign_in_failed() -> Problem:
    return unauthorized("Sign-in details are not correct")


def _invalid(exc: InvalidAccountError | credentials.WeakSecretError) -> Problem:
    entry = {"code": exc.code, "message": str(exc)}
    if exc.field:
        entry["field"] = exc.field
    return validation_error(str(exc), errors=[entry])


def staff_view(account: StaffAccount) -> dict[str, Any]:
    return {
        "staff_ref": account.staff_ref,
        "email": account.email,
        "display_name": account.display_name,
        "role": account.role,
        "status": account.status.value,
        "created_at": account.created_at,
    }


class SessionRegistry(Protocol):
    """The part of ``IdentityService`` that carries sessions for roles it does not own."""

    def register_session_subject(
        self,
        role: str,
        *,
        is_active: Callable[[str], bool],
        issue_access: Callable[[str, float], IssuedToken],
        profile: Callable[[str], dict[str, Any]] | None = None,
        refresh_ttl_seconds: int = ...,
    ) -> None: ...

    def issue_refresh_token(self, subject_ref: str, role: str, device_id: str = "") -> str: ...


class StaffService:
    def __init__(
        self,
        uow_factory: Callable[[], IdentityUnitOfWork],
        issuer: TokenIssuer,
        clock: Callable[[], float],
        hasher: credentials.SecretHasher,
        sessions: SessionRegistry,
    ) -> None:
        self._uow = uow_factory
        self._issuer = issuer
        self._now = clock
        self._hasher = hasher
        self._equalising: str | None = None
        self._sessions = sessions
        # Each Studio role continues its sessions through identity's generic refresh flow, with a
        # live account check on every refresh (suspended, locked, or role changed -> 401).
        for role in STAFF_ROLES:
            sessions.register_session_subject(
                role,
                is_active=partial(self._active_in_role, role),
                issue_access=self._access_for_subject,
                profile=self._profile_payload,
                refresh_ttl_seconds=STAFF_REFRESH_TTL_SECONDS,
            )

    # ------------------------------------------------------------------------ operator actions

    def create_staff(
        self,
        *,
        operator_ref: str,
        email: str,
        passphrase: str,
        display_name: str,
        role: str,
    ) -> dict[str, Any]:
        try:
            credentials.assert_passphrase_policy(passphrase)
            account = StaffAccount.create(
                email=email,
                passphrase_hash="",
                display_name=display_name,
                role=role,
                created_by=operator_ref,
                now=self._now(),
            )
        except (InvalidAccountError, credentials.WeakSecretError) as exc:
            raise _invalid(exc) from exc
        account.passphrase_hash = self._hasher.hash(passphrase)
        with self._uow() as uow:
            if uow.staff.by_email(account.email) is not None:
                raise Problem(409, "EMAIL_IN_USE", "Conflict", "a staff account has this email")
            uow.staff.add(account)
            self._audit(uow, AuditAction.STAFF_CREATED, operator_ref, "system", account, role=role)
            uow.commit()
        return staff_view(account)

    def list_staff(self) -> list[dict[str, Any]]:
        with self._uow() as uow:
            return [staff_view(a) for a in uow.staff.all()]

    def suspend_staff(self, *, operator_ref: str, staff_ref: str) -> dict[str, Any]:
        now = self._now()
        with self._uow() as uow:
            account = self._require(uow, staff_ref)
            revoked = uow.refresh_tokens.revoke_all_for(staff_ref, now=now)
            if account.status is not AccountStatus.SUSPENDED or revoked:
                account.status = AccountStatus.SUSPENDED
                uow.staff.save(account)
                self._audit(
                    uow,
                    AuditAction.STAFF_SUSPENDED,
                    operator_ref,
                    "system",
                    account,
                    revoked_sessions=revoked,
                )
            uow.commit()
            return staff_view(account)

    def reinstate_staff(self, *, operator_ref: str, staff_ref: str) -> dict[str, Any]:
        """Lift a suspension or a lockout (the operator is the only unlock path)."""
        with self._uow() as uow:
            account = self._require(uow, staff_ref)
            if account.status is not AccountStatus.ACTIVE:
                account.status = AccountStatus.ACTIVE
                account.failed_attempts = 0
                uow.staff.save(account)
                self._audit(uow, AuditAction.STAFF_REINSTATED, operator_ref, "system", account)
                uow.commit()
            return staff_view(account)

    # ------------------------------------------------------------------------- staff sign-in

    def sign_in_staff(self, *, email: str, passphrase: str) -> dict[str, Any]:
        now = self._now()
        try:
            normalised = normalise_email(email)
        except InvalidAccountError:
            raise _sign_in_failed() from None
        with self._uow() as uow:
            account = uow.staff.by_email(normalised)
            if account is None:
                self._hasher.verify(passphrase, self._equalising_hash())
                raise _sign_in_failed()
            correct = self._hasher.verify(passphrase, account.passphrase_hash)
            if not account.can_sign_in or not correct:
                self._record_failure(uow, account)
                uow.commit()
                raise _sign_in_failed()
            account.failed_attempts = 0
            uow.staff.save(account)
            self._audit(uow, AuditAction.STAFF_SIGNED_IN, account.staff_ref, account.role, account)
            uow.commit()
        refresh = self._sessions.issue_refresh_token(account.staff_ref, account.role, "")
        return {
            "staff": staff_view(account),
            "session": self.issue_access(account, now),
            "refresh_token": refresh,
        }

    def staff_profile(self, staff_ref: str) -> dict[str, Any]:
        with self._uow() as uow:
            account = self._require(uow, staff_ref)
        if not account.can_sign_in:
            raise Problem(403, STAFF_INACTIVE, "Staff account inactive", "sign in again")
        return staff_view(account)

    def change_passphrase(
        self, *, staff_ref: str, current: str, new_passphrase: str
    ) -> dict[str, Any]:
        """The operator chose the first passphrase; the staff member replaces it.

        Every session ends, so a passphrase the operator knew stops being useful at once.
        """
        try:
            credentials.assert_passphrase_policy(new_passphrase)
        except credentials.WeakSecretError as exc:
            raise _invalid(exc) from exc
        now = self._now()
        with self._uow() as uow:
            account = self._require(uow, staff_ref)
            if not account.can_sign_in or not self._hasher.verify(current, account.passphrase_hash):
                self._record_failure(uow, account)
                uow.commit()
                raise _sign_in_failed()
            account.passphrase_hash = self._hasher.hash(new_passphrase)
            account.failed_attempts = 0
            uow.staff.save(account)
            revoked = uow.refresh_tokens.revoke_all_for(staff_ref, now=now)
            self._audit(
                uow,
                AuditAction.STAFF_PASSPHRASE_CHANGED,
                staff_ref,
                account.role,
                account,
                revoked_sessions=revoked,
            )
            uow.commit()
        return {"changed": True, "revoked_sessions": revoked}

    # -------------------------------------------------------------- shared with other adapters

    def issue_access(self, account: StaffAccount, now: float) -> dict[str, object]:
        return self._mint_access(account, now).to_dict()

    def _mint_access(self, account: StaffAccount, now: float) -> IssuedToken:
        """The only way a staff access token is minted: role and subject from the stored account."""
        if account.role not in STAFF_ROLES:  # defence in depth; the domain and DB already enforce
            raise conflict("staff account holds an unexpected role")
        return self._issuer.issue(
            subject=account.staff_ref,
            role=account.role,
            now=now,
            ttl_seconds=STAFF_TOKEN_TTL_SECONDS,
        )

    # Session-subject hooks (registered with identity's refresh flow) --------------------------

    def _active_in_role(self, role: str, staff_ref: str) -> bool:
        with self._uow() as uow:
            account = uow.staff.get(staff_ref)
        return account is not None and account.can_sign_in and account.role == role

    def _access_for_subject(self, staff_ref: str, now: float) -> IssuedToken:
        with self._uow() as uow:
            account = self._require(uow, staff_ref)
        return self._mint_access(account, now)

    def _profile_payload(self, staff_ref: str) -> dict[str, Any]:
        with self._uow() as uow:
            account = self._require(uow, staff_ref)
        return {"staff": staff_view(account)}

    def staff_refusal(self, staff_ref: str, role: str, *, require_account: bool) -> str | None:
        """Per-request check for a Studio-role token. ``None`` means proceed.

        A token naming a staff account is refused once that account is suspended, locked, or holds
        a different role. A Studio-role token naming *no* staff account is refused when
        ``require_account`` (production: every legitimate Studio token comes from staff sign-in);
        outside production such hand-minted dev/test tokens still pass.
        """
        with self._uow() as uow:
            account = uow.staff.get(staff_ref)
        if account is None:
            return STAFF_INACTIVE if require_account else None
        if not account.can_sign_in or account.role != role:
            return STAFF_INACTIVE
        return None

    # ---------------------------------------------------------------------------------- helpers

    def _equalising_hash(self) -> str:
        if self._equalising is None:
            self._equalising = self._hasher.equalising_hash()
        return self._equalising

    def _require(self, uow: IdentityUnitOfWork, staff_ref: str) -> StaffAccount:
        account = uow.staff.get(staff_ref)
        if account is None:
            raise not_found("staff account not found")
        return account

    def _record_failure(self, uow: IdentityUnitOfWork, account: StaffAccount) -> None:
        account.failed_attempts += 1
        action = AuditAction.STAFF_SIGN_IN_FAILED
        if (
            account.failed_attempts >= credentials.MAX_PASSPHRASE_ATTEMPTS
            and account.status is AccountStatus.ACTIVE
        ):
            account.status = AccountStatus.LOCKED
            action = AuditAction.STAFF_LOCKED
        uow.staff.save(account)
        self._audit(
            uow,
            action,
            account.staff_ref,
            account.role,
            account,
            failed_attempts=account.failed_attempts,
        )

    def _audit(
        self,
        uow: IdentityUnitOfWork,
        action: AuditAction,
        actor_ref: str,
        actor_role: str,
        account: StaffAccount,
        **detail: Any,
    ) -> None:
        uow.audit.append(
            AuditEvent.record(
                action=action,
                actor_ref=actor_ref,
                actor_role=actor_role,
                subject_ref=account.staff_ref,
                now=self._now(),
                correlation_id=get_correlation_id() or "",
                detail=detail,
            )
        )
