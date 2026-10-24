"""The Vercel build's opt-in demo seed: off unless asked for, and never on production."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "vercel_migrate.py"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vercel_migrate", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_is_off_unless_explicitly_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TALEEM_DEMO_SEED", raising=False)
    assert _module()._seed_demo_fixture() == 0
    monkeypatch.setenv("TALEEM_DEMO_SEED", "yes")  # only the exact value "1" enables it
    assert _module()._seed_demo_fixture() == 0


def test_seed_refuses_a_production_deployment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TALEEM_DEMO_SEED", "1")
    monkeypatch.setenv("TALEEM_ENV", "production")
    monkeypatch.setenv("TALEEM_DATABASE_URL", "sqlite://")
    assert _module()._seed_demo_fixture() == 1  # non-zero fails the build loudly
    assert "refusing to seed" in capsys.readouterr().err


def test_seed_publishes_the_labelled_fixture_outside_production(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from taleem_core.contexts.curriculum_studio.adapters.persistence import (
        Base,
        create_db_engine,
    )

    url = f"sqlite:///{tmp_path / 'demo.db'}"
    engine = create_db_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    monkeypatch.setenv("TALEEM_DEMO_SEED", "1")
    monkeypatch.setenv("TALEEM_ENV", "staging")
    monkeypatch.setenv("TALEEM_DATABASE_URL", url)
    assert _module()._seed_demo_fixture() == 0
    assert _module()._seed_demo_fixture() == 0  # idempotent
