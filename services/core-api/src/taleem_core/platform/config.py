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
    # Guardian→children associations (the only new state the Guardian Portal adds). Software layer,
    # not the M-Gov consent flow. Format: "guardianRef=Name:childA,childB;guardianRef2:childC".
    # Empty in production until the consent workflow populates links; a demo link is seeded in dev.
    guardian_links_csv: str = field(default_factory=lambda: _get("TALEEM_GUARDIAN_LINKS", ""))

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
    if not settings.has_asymmetric_signing:
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
        elif seed == settings.offline_signing_seed_hex.strip():
            problems.append(
                "TALEEM_JWT_SIGNING_SEED must differ from the offline-signing seed (key separation)"
            )
    if not settings.database_url.strip():
        problems.append(
            "TALEEM_DATABASE_URL is unset (production must use PostgreSQL, not in-memory)"
        )
    if settings.offline_signing_seed_hex == DEFAULT_OFFLINE_SIGNING_SEED:
        problems.append("TALEEM_OFFLINE_SIGNING_SEED is the built-in default (forgeable packages)")
    if problems:
        raise InsecureConfigurationError(
            "refusing to start in production with insecure defaults: " + "; ".join(problems)
        )


def load_settings() -> Settings:
    """Build settings from the environment (fails closed on insecure production defaults)."""
    settings = Settings()
    _assert_production_safe(settings)
    return settings
