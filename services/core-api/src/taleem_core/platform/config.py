"""12-Factor configuration (pure-stdlib).

Config comes from the environment only (12-Factor III). No secrets in code.
A typed, immutable settings object is built once at startup.
See docs/07-engineering/41-coding-standards.md and 04-non-functional-requirements.md (MNT-06).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum


class Environment(str, Enum):
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
    # Production uses asymmetric JWKS + KMS (see docs/11 + FOUNDER_DECISIONS FD-14). Never a real secret.
    jwt_dev_secret: str = field(default_factory=lambda: _get("TALEEM_JWT_DEV_SECRET", "dev-only-not-secret"))
    request_timeout_ms: int = field(default_factory=lambda: _get_int("TALEEM_REQUEST_TIMEOUT_MS", 30000))

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    def enabled_flags(self) -> frozenset[str]:
        return frozenset(f.strip() for f in self.enabled_flags_csv.split(",") if f.strip())


def load_settings() -> Settings:
    """Build settings from the current environment."""
    return Settings()
