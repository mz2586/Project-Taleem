"""Phase 4.2 hardening tests — config safety, observability, and composed-app wiring."""

from __future__ import annotations

import pytest

from taleem_core.platform.config import (
    DEFAULT_JWT_DEV_SECRET,
    Environment,
    InsecureConfigurationError,
    Settings,
    _assert_production_safe,
)
from taleem_core.platform.metrics import registry

# ---- CTO H8: production fails closed on insecure defaults ----


def test_production_rejects_default_jwt_secret() -> None:
    s = Settings(
        environment=Environment.PRODUCTION,
        jwt_dev_secret=DEFAULT_JWT_DEV_SECRET,
        database_url="postgresql+psycopg://u@h/db",
    )
    with pytest.raises(InsecureConfigurationError):
        _assert_production_safe(s)


def test_production_rejects_missing_database_url() -> None:
    s = Settings(
        environment=Environment.PRODUCTION,
        jwt_dev_secret="a-real-secret",  # noqa: S106 (test fixture, not a real secret)
        database_url="",
    )
    with pytest.raises(InsecureConfigurationError):
        _assert_production_safe(s)


def test_production_accepts_real_config() -> None:
    s = Settings(
        environment=Environment.PRODUCTION,
        jwt_dev_secret="a-real-rotated-secret",  # noqa: S106 (test fixture, not a real secret)
        database_url="postgresql+psycopg://u@h/db",
    )
    _assert_production_safe(s)  # no raise


def test_local_allows_defaults() -> None:
    _assert_production_safe(Settings(environment=Environment.LOCAL))  # no raise


# ---- CTO H9: application services emit domain telemetry ----


def test_slice_emits_domain_metrics() -> None:
    from taleem_core.vertical_slice.runner import run_slice

    run_slice()
    for metric in (
        "taleem_lessons_published_total",
        "taleem_objectives_mastered_total",
        "taleem_sessions_started_total",
        "taleem_sessions_completed_total",
    ):
        assert registry().counter_value(metric) > 0, metric
    # This counter is labeled by outcome.
    assert registry().counter_value("taleem_learning_attempts_total", outcome="correct") > 0


# ---- CTO H1: the composed app mounts both business routers (no contract drift) ----


def test_composed_app_mounts_learning_and_studio() -> None:
    from taleem_core.main import create_app

    paths = set(create_app().openapi()["paths"].keys())
    assert "/v1/learning/sessions" in paths  # learning router is actually mounted
    assert "/v1/studio/lessons" in paths
    assert "/v1/learning/students/{student_ref}/knowledge" in paths
