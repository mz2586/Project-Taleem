"""Identity domain tests — credentials, accounts, consent folding, audit.

Pure-domain: no database, no FastAPI. These assert the rules that protect a child independently of
how they are reached.
"""

from __future__ import annotations

import pytest

from taleem_core.contexts.identity.domain import credentials
from taleem_core.contexts.identity.domain.accounts import (
    FAMILY_CODE_PATTERN,
    AccountStatus,
    GuardianAccount,
    InvalidAccountError,
    LearnerAccount,
    new_family_code,
    normalise_display_name,
    normalise_email,
    normalise_family_code,
    roster_key,
)
from taleem_core.contexts.identity.domain.audit import AuditAction, AuditEvent
from taleem_core.contexts.identity.domain.consent import (
    CURRENT_POLICY_VERSION,
    ConsentAction,
    ConsentError,
    ConsentEvidence,
    ConsentRecord,
    ConsentScope,
    derive_state,
)

FAST = credentials.SecretHasher(iterations=1_000)


# ------------------------------------------------------------------------------- credentials


def test_hash_and_verify_roundtrip() -> None:
    encoded = FAST.hash("a-long-enough-passphrase")
    assert FAST.verify("a-long-enough-passphrase", encoded)
    assert not FAST.verify("a-long-enough-passphras", encoded)


def test_hash_is_salted_so_equal_secrets_do_not_collide() -> None:
    a = FAST.hash("same-secret-value")
    b = FAST.hash("same-secret-value")
    assert a != b
    assert FAST.verify("same-secret-value", a)
    assert FAST.verify("same-secret-value", b)


def test_unicode_normalisation_makes_equivalent_urdu_forms_one_credential() -> None:
    # ALEF + combining MADDA (U+0627 U+0653) versus the precomposed ALEF WITH MADDA (U+0622).
    # Two keyboards produce different code points for a passphrase the person considers one.
    decomposed = "\u067e\u0627\u0633\u0648\u0631\u0688\u0627\u0653"
    composed = "\u067e\u0627\u0633\u0648\u0631\u0688\u0622"
    assert decomposed != composed
    assert FAST.verify(composed, FAST.hash(decomposed))


def test_malformed_stored_hash_verifies_false_rather_than_raising() -> None:
    assert not FAST.verify("anything", "not-a-hash")
    assert not FAST.verify("anything", "")
    assert not FAST.verify("anything", "scrypt$1$aa$bb")


def test_passphrase_policy_is_length_led() -> None:
    credentials.assert_passphrase_policy("a" * credentials.MIN_PASSPHRASE_LENGTH)
    with pytest.raises(credentials.WeakSecretError):
        credentials.assert_passphrase_policy("short")
    with pytest.raises(credentials.WeakSecretError):
        credentials.assert_passphrase_policy("a" * 300)


def test_pin_policy_rejects_shape_and_common_values() -> None:
    credentials.assert_pin_policy("4813")
    with pytest.raises(credentials.WeakSecretError):
        credentials.assert_pin_policy("12")  # too short
    with pytest.raises(credentials.WeakSecretError):
        credentials.assert_pin_policy("abcd")  # not digits
    with pytest.raises(credentials.WeakSecretError):
        credentials.assert_pin_policy("1234")  # most-guessed


# ---------------------------------------------------------------------------------- accounts


def test_family_code_is_readable_and_unambiguous() -> None:
    for _ in range(50):
        code = new_family_code()
        assert FAMILY_CODE_PATTERN.match(code), code
        # The characters that get misread aloud are excluded on purpose.
        assert not set(code) & {"O", "I", "L", "0", "1"}


def test_family_code_normalisation_accepts_what_a_parent_types() -> None:
    assert normalise_family_code("k7qm3xpz") == "K7QM-3XPZ"
    assert normalise_family_code("K7QM 3XPZ") == "K7QM-3XPZ"
    assert normalise_family_code(" k7qm-3xpz ") == "K7QM-3XPZ"
    with pytest.raises(InvalidAccountError):
        normalise_family_code("TOO-SHORT1")


def test_display_name_normalisation_collapses_whitespace_and_rejects_control_chars() -> None:
    assert normalise_display_name("  Ali   Raza ") == "Ali Raza"
    assert roster_key("ALI RAZA") == roster_key("ali  raza")
    with pytest.raises(InvalidAccountError):
        normalise_display_name("   ")
    with pytest.raises(InvalidAccountError):
        normalise_display_name("Ali\x07Raza")
    with pytest.raises(InvalidAccountError):
        normalise_display_name("x" * 200)


def test_email_normalisation_and_rejection() -> None:
    assert normalise_email("  Guardian@Example.COM ") == "guardian@example.com"
    for bad in ("no-at-sign", "a@b", "a@@b.com", "a b@c.com"):
        with pytest.raises(InvalidAccountError):
            normalise_email(bad)


def test_guardian_gets_a_family_code_and_an_opaque_ref() -> None:
    account = GuardianAccount.create(
        email="g@example.com",
        passphrase_hash="h",  # noqa: S106 (opaque placeholder, not a secret)
        display_name="Guardian",
        now=1.0,
    )
    assert account.guardian_ref.startswith("gdn_")
    assert FAMILY_CODE_PATTERN.match(account.family_code)
    assert account.can_sign_in


def test_learner_ref_is_opaque_and_not_derived_from_shareable_data() -> None:
    learner = LearnerAccount.create(
        guardian_ref="gdn_1", display_name="Ayesha", pin_hash="h", now=1.0
    )
    assert learner.student_ref.startswith("stu_")
    assert "Ayesha" not in learner.student_ref
    assert learner.roster_key == "ayesha"


def test_learner_rejects_out_of_range_grade_and_unknown_band() -> None:
    with pytest.raises(InvalidAccountError):
        LearnerAccount.create(guardian_ref="g", display_name="A", pin_hash="h", grade_band="cosmic")
    with pytest.raises(InvalidAccountError):
        LearnerAccount.create(guardian_ref="g", display_name="A", pin_hash="h", grade_level=99)


def test_known_devices_are_bounded_and_most_recent_first() -> None:
    learner = LearnerAccount.create(guardian_ref="g", display_name="A", pin_hash="h")
    for i in range(8):
        learner.remember_device(f"dev-{i}")
    assert learner.known_devices[0] == "dev-7"
    assert len(learner.known_devices) == 5
    learner.remember_device("dev-7")  # re-signing in on the same device does not duplicate it
    assert learner.known_devices.count("dev-7") == 1
    learner.remember_device("")  # an anonymous client adds nothing
    assert "" not in learner.known_devices


def test_locked_and_suspended_accounts_cannot_sign_in() -> None:
    learner = LearnerAccount.create(guardian_ref="g", display_name="A", pin_hash="h")
    learner.status = AccountStatus.LOCKED
    assert not learner.can_sign_in
    learner.status = AccountStatus.SUSPENDED
    assert not learner.can_sign_in


# ----------------------------------------------------------------------------------- consent


def _grant(scopes: set[ConsentScope], at: float, policy: str = CURRENT_POLICY_VERSION):
    return ConsentRecord.grant(
        guardian_ref="gdn_1", student_ref="stu_1", scopes=scopes, now=at, policy_version=policy
    )


def test_consent_must_include_the_required_scope() -> None:
    with pytest.raises(ConsentError):
        _grant({ConsentScope.AI_TEACHING}, 1.0)


def test_derived_state_permits_sign_in_after_a_grant() -> None:
    state = derive_state("stu_1", [_grant({ConsentScope.LEARNING_DATA}, 1.0)])
    assert state.permits_sign_in
    assert state.granted_at == 1.0


def test_full_withdrawal_revokes_sign_in_but_keeps_the_history() -> None:
    history = [
        _grant({ConsentScope.LEARNING_DATA, ConsentScope.AI_TEACHING}, 1.0),
        ConsentRecord.withdraw(guardian_ref="gdn_1", student_ref="stu_1", now=2.0),
    ]
    state = derive_state("stu_1", history)
    assert not state.permits_sign_in
    assert state.granted_scopes == frozenset()
    assert state.last_change_at == 2.0
    assert len(history) == 2  # nothing was mutated or removed


def test_partial_withdrawal_keeps_learning_but_stops_the_withdrawn_feature() -> None:
    state = derive_state(
        "stu_1",
        [
            _grant({ConsentScope.LEARNING_DATA, ConsentScope.AI_TEACHING}, 1.0),
            ConsentRecord.withdraw(
                guardian_ref="gdn_1",
                student_ref="stu_1",
                scopes={ConsentScope.AI_TEACHING},
                now=2.0,
            ),
        ],
    )
    assert state.permits_sign_in
    assert state.allows(ConsentScope.LEARNING_DATA)
    assert not state.allows(ConsentScope.AI_TEACHING)


def test_regranting_after_withdrawal_restores_permission() -> None:
    state = derive_state(
        "stu_1",
        [
            _grant({ConsentScope.LEARNING_DATA}, 1.0),
            ConsentRecord.withdraw(guardian_ref="gdn_1", student_ref="stu_1", now=2.0),
            _grant({ConsentScope.LEARNING_DATA}, 3.0),
        ],
    )
    assert state.permits_sign_in
    assert state.granted_at == 3.0


def test_consent_under_a_superseded_policy_version_does_not_permit_sign_in() -> None:
    """A material change to how a child's data is used needs fresh agreement, not inheritance."""
    state = derive_state(
        "stu_1", [_grant({ConsentScope.LEARNING_DATA}, 1.0, policy="2020-ancient-v0")]
    )
    assert not state.is_current
    assert not state.permits_sign_in
    assert not state.allows(ConsentScope.LEARNING_DATA)


def test_history_is_folded_in_time_order_regardless_of_input_order() -> None:
    records = [
        ConsentRecord.withdraw(guardian_ref="gdn_1", student_ref="stu_1", now=2.0),
        _grant({ConsentScope.LEARNING_DATA}, 1.0),
    ]
    assert not derive_state("stu_1", records).permits_sign_in
    assert not derive_state("stu_1", list(reversed(records))).permits_sign_in


def test_no_records_at_all_denies() -> None:
    assert not derive_state("stu_1", []).permits_sign_in


def test_consent_state_serialises_the_fields_a_guardian_ui_needs() -> None:
    body = derive_state("stu_1", [_grant({ConsentScope.LEARNING_DATA}, 1.0)]).to_dict()
    assert body["permits_sign_in"] is True
    assert body["granted_scopes"] == ["learning_data"]
    assert body["current_policy_version"] == CURRENT_POLICY_VERSION


def test_evidence_carries_hashes_not_raw_context() -> None:
    record = ConsentRecord.grant(
        guardian_ref="gdn_1",
        student_ref="stu_1",
        scopes={ConsentScope.LEARNING_DATA},
        now=1.0,
        evidence=ConsentEvidence(ip_hash="abc123", attestation="I am the guardian"),
    )
    assert record.action is ConsentAction.GRANTED
    assert record.evidence.ip_hash == "abc123"
    assert record.consent_id.startswith("con_")


# ------------------------------------------------------------------------------------- audit


def test_audit_event_is_serialisable_and_carries_no_names() -> None:
    event = AuditEvent.record(
        action=AuditAction.LEARNER_SIGNED_IN,
        actor_ref="stu_1",
        actor_role="student",
        subject_ref="stu_1",
        now=5.0,
        correlation_id="cid-1",
        detail={"device_bound": True},
    )
    body = event.to_dict()
    assert body["action"] == "learner.signed_in"
    assert body["correlation_id"] == "cid-1"
    assert event.event_id.startswith("aud_")
