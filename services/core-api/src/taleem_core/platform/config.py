"""12-Factor configuration (pure-stdlib).

Config comes from the environment only (12-Factor III). No secrets in code.
A typed, immutable settings object is built once at startup.
See docs/07-engineering/41-coding-standards.md and 04-non-functional-requirements.md (MNT-06).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum


class Environment(StrEnum):
    LOCAL = "local"
    CI = "ci"
    STAGING = "staging"
    PRODUCTION = "production"


def _get(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Immutable application settings, sourced from the environment."""

    environment: Environment = field(
        default_factory=lambda: Environment(_get("TALEEM_ENV", "local"))
    )
    service_name: str = field(default_factory=lambda: _get("TALEEM_SERVICE_NAME", "core-api"))
    log_level: str = field(default_factory=lambda: _get("TALEEM_LOG_LEVEL", "INFO"))
    default_locale: str = field(default_factory=lambda: _get("TALEEM_DEFAULT_LOCALE", "ur"))
    # Feature flags may be seeded from env as CSV of enabled flag keys.
    enabled_flags_csv: str = field(default_factory=lambda: _get("TALEEM_ENABLED_FLAGS", ""))
    metrics_enabled: bool = field(default_factory=lambda: _get_bool("TALEEM_METRICS_ENABLED", True))
    tracing_enabled: bool = field(default_factory=lambda: _get_bool("TALEEM_TRACING_ENABLED", True))
    # Auth (dev/test only): HS256 verification secret — a placeholder for the walking skeleton.
    # Rejected in production, which is asymmetric-only (below).
    jwt_dev_secret: str = field(
        default_factory=lambda: _get("TALEEM_JWT_DEV_SECRET", "dev-only-not-secret")
    )
    # Auth (production): asymmetric token signing/verification — Ed25519/EdDSA, rotating JWKS keys
    # (FD-14, docs/03 §11 §7, §13). The signing seed is a 32-byte Ed25519 seed as hex; the Identity
    # node holds it and issues tokens, resource servers hold only the derived public key. Empty in
    # dev (HS256 path). ``TALEEM_JWT_VERIFICATION_KEYS`` = extra "kid:hexpub,.." public keys held
    # during a rotation overlap. iss/aud bind tokens to this issuer + audience.
    jwt_signing_seed_hex: str = field(default_factory=lambda: _get("TALEEM_JWT_SIGNING_SEED", ""))
    jwt_signing_kid: str = field(
        default_factory=lambda: _get("TALEEM_JWT_SIGNING_KID", "taleem-ed25519-1")
    )
    jwt_verification_keys_csv: str = field(
        default_factory=lambda: _get("TALEEM_JWT_VERIFICATION_KEYS", "")
    )
    # Signer port backend (FD-14): "env" signs with TALEEM_JWT_SIGNING_SEED held in memory (the
    # only backend that can be built today); "kms" needs a key reference, its public key, and a
    # provider adapter that does not exist until FD-14 is decided, so it fails closed at startup.
    signer_backend: str = field(default_factory=lambda: _get("TALEEM_SIGNER_BACKEND", "env"))
    kms_token_key_ref: str = field(default_factory=lambda: _get("TALEEM_KMS_TOKEN_KEY_REF", ""))
    kms_token_public_key_hex: str = field(
        default_factory=lambda: _get("TALEEM_KMS_TOKEN_PUBLIC_KEY", "")
    )
    jwt_issuer: str = field(default_factory=lambda: _get("TALEEM_JWT_ISSUER", "taleem-identity"))
    jwt_audience: str = field(
        default_factory=lambda: _get("TALEEM_JWT_AUDIENCE", "taleem-core-api")
    )
    # Database URL for the SQL persistence adapters. Empty => in-memory SQLite (governance-safe
    # local/dev default). Production MUST set a real PostgreSQL URL (enforced in load_settings).
    database_url: str = field(default_factory=lambda: _get("TALEEM_DATABASE_URL", ""))
    request_timeout_ms: int = field(
        default_factory=lambda: _get_int("TALEEM_REQUEST_TIMEOUT_MS", 30000)
    )
    # Offline package signing (Phase 6.2C-1): a 32-byte Ed25519 seed as hex. DEV DEFAULT ONLY —
    # a fixed, well-known seed for local/dev; production MUST supply a real seed (ideally KMS-held,
    # FD-14) via env. The private seed never leaves the server; clients hold only the public key.
    offline_signing_seed_hex: str = field(
        default_factory=lambda: _get("TALEEM_OFFLINE_SIGNING_SEED", DEFAULT_OFFLINE_SIGNING_SEED)
    )
    offline_signing_key_id: str = field(
        default_factory=lambda: _get("TALEEM_OFFLINE_SIGNING_KEY_ID", "dev-ed25519-1")
    )
    # Browser SPAs are served from a different origin than the API (e.g. app.taleem.dev vs
    # api.taleem.dev), so cross-origin requests need an explicit CORS allowlist. CSV of exact
    # origins; empty => same-origin only (no CORS headers). Never "*" — the API is credentialed.
    cors_allowed_origins_csv: str = field(
        default_factory=lambda: _get("TALEEM_CORS_ALLOWED_ORIGINS", "")
    )
    # Work factor for guardian passphrase and child PIN hashing (identity context). Exposed so the
    # test suite can run hundreds of sign-ins without spending minutes on PBKDF2; production is
    # protected by ``_assert_production_safe``, which refuses to boot below the OWASP minimum, so a
    # stray environment variable cannot weaken a real deployment.
    kdf_iterations: int = field(
        default_factory=lambda: _get_int("TALEEM_KDF_ITERATIONS", MIN_KDF_ITERATIONS)
    )
    # DEV/DEMO SEED ONLY: static guardian→children links layered under the identity context's real
    # links (enrolled learners with live consent). Ignored in production, where only consent links.
    # Format: "guardianRef=Name:childA,childB;guardianRef2:childC".
    guardian_links_csv: str = field(default_factory=lambda: _get("TALEEM_GUARDIAN_LINKS", ""))
    # Header a trusted edge overwrites with the real client address, used to key the public identity
    # routes' rate limit. Without it every request behind a proxy shares one budget. Defaults to
    # ``x-real-ip`` on Vercel (``VERCEL=1``), which sets that header itself and does not pass a
    # client-supplied value through; empty elsewhere (the socket peer is used).
    client_ip_header: str = field(
        default_factory=lambda: _get(
            "TALEEM_CLIENT_IP_HEADER", "x-real-ip" if os.environ.get("VERCEL") == "1" else ""
        )
    )
    # AI Teacher generative tier provider slot (Phase D). "" => no generative tier at all;
    # "stub" => the deterministic offline stub (dev/test only, refused in production);
    # "anthropic" => the FD-03 Claude adapter (ports/llm_anthropic.py), built ONLY when every FD-03
    # approval setting below is present (production refuses to boot on a partial set; elsewhere the
    # app stays on the deterministic engine); any other value names a provider but is inert.
    # The tier itself is off unless the `ai_teacher.generative_rephrase` flag is enabled.
    ai_provider: str = field(default_factory=lambda: _get("TALEEM_AI_PROVIDER", ""))
    # FD-03 approval settings for TALEEM_AI_PROVIDER=anthropic. Unset in every environment until the
    # founder records the six FD-03 approvals (docs/decisions/FD-03-ai-provider-residency.md).
    # A dedicated key variable: the SDK's ANTHROPIC_API_KEY / profile discovery is never used.
    ai_anthropic_api_key: str = field(
        default_factory=lambda: _get("TALEEM_AI_ANTHROPIC_API_KEY", ""), repr=False
    )
    ai_inference_geo: str = field(default_factory=lambda: _get("TALEEM_AI_INFERENCE_GEO", ""))
    ai_zdr_confirmed: str = field(default_factory=lambda: _get("TALEEM_AI_ZDR_CONFIRMED", ""))
    ai_fd03_approval_ref: str = field(
        default_factory=lambda: _get("TALEEM_AI_FD03_APPROVAL_REF", "")
    )
    ai_timeout_seconds: float = field(
        default_factory=lambda: float(_get_int("TALEEM_AI_TIMEOUT_SECONDS", 15))
    )
    # Per-learner, per-UTC-day inference quota for the generative tier (free-tier sustainability).
    # Exhaustion serves the templated authored engine — never an error. Real values await FD-07.
    ai_learner_daily_calls: int = field(
        default_factory=lambda: _get_int("TALEEM_AI_LEARNER_DAILY_CALLS", 20)
    )
    ai_learner_daily_tokens: int = field(
        default_factory=lambda: _get_int("TALEEM_AI_LEARNER_DAILY_TOKENS", 20_000)
    )
    # Per-learner, per-UTC-day cost cap in micro-USD (the FD-07 envelope). 0 => no cost cap; a real
    # provider in production requires a positive value.
    ai_learner_daily_cost_micros: int = field(
        default_factory=lambda: _get_int("TALEEM_AI_LEARNER_DAILY_COST_MICROS", 0)
    )
    # Safeguarding "acknowledge within" thresholds, JSON {"T1": seconds, ...}. UNSET by default and
    # deliberately so: the SLA is an owner decision (FD-06); no number is invented here.
    safeguarding_ack_sla_json: str = field(
        default_factory=lambda: _get("TALEEM_SAFEGUARDING_ACK_SLA_SECONDS", "")
    )

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def has_asymmetric_signing(self) -> bool:
        return bool(self.jwt_signing_seed_hex.strip())

    def enabled_flags(self) -> frozenset[str]:
        return frozenset(f.strip() for f in self.enabled_flags_csv.split(",") if f.strip())

    def cors_allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins_csv.split(",") if o.strip()]


# OWASP Password Storage Cheat Sheet (2023) for PBKDF2-HMAC-SHA256. Production may raise this but
# never lower it.
MIN_KDF_ITERATIONS = 600_000

DEFAULT_JWT_DEV_SECRET = "dev-only-not-secret"  # noqa: S105 (sentinel default, rejected in prod)
# A fixed dev Ed25519 seed (bytes 00..1f as hex). Dev/local only — rejected in production.
DEFAULT_OFFLINE_SIGNING_SEED = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"


class InsecureConfigurationError(RuntimeError):
    """Raised when production would boot with an insecure default (fail closed)."""


def _assert_production_safe(settings: Settings) -> None:
    """Fail closed on insecure production defaults (CTO H8)."""
    if not settings.is_production:
        return
    problems: list[str] = []
    # Production is asymmetric-only (FD-14): require a real Ed25519 signing seed; the HS256 dev path
    # is not used in production, so a lingering default dev secret is not itself the gate.
    backend = settings.signer_backend.strip().lower() or "env"
    if backend == "kms":
        # The key never leaves the KMS, so there is no seed to check. Startup still fails closed in
        # build_auth_context until a provider adapter exists (FD-14).
        if not settings.kms_token_key_ref.strip() or not settings.kms_token_public_key_hex.strip():
            problems.append(
                "TALEEM_SIGNER_BACKEND=kms needs TALEEM_KMS_TOKEN_KEY_REF and "
                "TALEEM_KMS_TOKEN_PUBLIC_KEY"
            )
        if settings.has_asymmetric_signing:
            problems.append(
                "TALEEM_JWT_SIGNING_SEED must be unset when tokens are signed by a KMS key"
            )
    elif backend != "env":
        problems.append(f"TALEEM_SIGNER_BACKEND={settings.signer_backend!r} is not a known backend")
    elif not settings.has_asymmetric_signing:
        problems.append(
            "TALEEM_JWT_SIGNING_SEED is unset (production signs tokens asymmetrically, not HS256)"
        )
    else:
        seed = settings.jwt_signing_seed_hex.strip()
        try:
            raw = bytes.fromhex(seed)
        except ValueError:
            raw = b""
        if len(raw) != 32:
            problems.append("TALEEM_JWT_SIGNING_SEED must be a 32-byte hex Ed25519 seed")
        elif seed.lower() == DEFAULT_OFFLINE_SIGNING_SEED:
            problems.append("TALEEM_JWT_SIGNING_SEED is the well-known development seed")
        elif seed == settings.offline_signing_seed_hex.strip():
            problems.append(
                "TALEEM_JWT_SIGNING_SEED must differ from the offline-signing seed (key separation)"
            )
    if not settings.database_url.strip():
        problems.append(
            "TALEEM_DATABASE_URL is unset (production must use PostgreSQL, not in-memory)"
        )
    if settings.kdf_iterations < MIN_KDF_ITERATIONS:
        problems.append(
            f"TALEEM_KDF_ITERATIONS is {settings.kdf_iterations}, below the minimum "
            f"{MIN_KDF_ITERATIONS} (guardian passphrases and child PINs would hash too cheaply)"
        )
    if settings.offline_signing_seed_hex == DEFAULT_OFFLINE_SIGNING_SEED:
        problems.append("TALEEM_OFFLINE_SIGNING_SEED is the built-in default (forgeable packages)")
    if settings.ai_provider.strip().lower() == "stub":
        problems.append("TALEEM_AI_PROVIDER=stub (a scripted test gateway; never for children)")
    if settings.ai_provider.strip().lower() == "anthropic":
        # FD-03: a real provider in production needs every approval setting — never a partial set.
        from ..ports.llm_anthropic import settings_problems

        problems.extend(f"TALEEM_AI_PROVIDER=anthropic: {p}" for p in settings_problems(settings))
        if settings.ai_learner_daily_cost_micros <= 0:
            problems.append(
                "TALEEM_AI_PROVIDER=anthropic: TALEEM_AI_LEARNER_DAILY_COST_MICROS is unset "
                "(the FD-07 per-learner cost envelope)"
            )
    if problems:
        raise InsecureConfigurationError(
            "refusing to start in production with insecure defaults: " + "; ".join(problems)
        )


def load_settings() -> Settings:
    """Build settings from the environment (fails closed on insecure production defaults)."""
    settings = Settings()
    _assert_production_safe(settings)
    return settings
