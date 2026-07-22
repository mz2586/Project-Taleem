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
    # Auth: JWT verification secret is a *placeholder* for the walking skeleton only.
    # Production uses asymmetric JWKS + KMS (docs/11 + FD-14). Never a real secret.
    jwt_dev_secret: str = field(
        default_factory=lambda: _get("TALEEM_JWT_DEV_SECRET", "dev-only-not-secret")
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

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    def enabled_flags(self) -> frozenset[str]:
        return frozenset(f.strip() for f in self.enabled_flags_csv.split(",") if f.strip())


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
    if settings.jwt_dev_secret == DEFAULT_JWT_DEV_SECRET or not settings.jwt_dev_secret.strip():
        problems.append("TALEEM_JWT_DEV_SECRET is the built-in default (forgeable tokens)")
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
