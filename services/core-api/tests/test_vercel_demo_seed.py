"""The Vercel build's opt-in demo-cohort seed: off unless asked for; demo-cohort data only."""

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


def test_seed_runs_on_production_and_writes_only_the_demo_cohort(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """DEMO_COHORT_CONTRACT §5: the demo-cohort seeder runs in every environment, production
    included, because it writes only demo-flagged accounts and ``audience = "demo"`` content."""
    url = f"sqlite:///{tmp_path / 'taleem.db'}"
    monkeypatch.setenv("TALEEM_DEMO_SEED", "1")
    monkeypatch.setenv("TALEEM_ENV", "production")
    monkeypatch.setenv("TALEEM_DATABASE_URL", url)
    monkeypatch.setenv("TALEEM_KDF_ITERATIONS", "1000")  # test-only work factor
    monkeypatch.setenv("TALEEM_DEMO_GUARDIAN_PASSPHRASE", "synthetic build-step passphrase 5512")
    monkeypatch.setenv("TALEEM_DEMO_LEARNER_PIN", "4826")
    assert _module()._seed_demo_fixture() == 0
    first = capsys.readouterr().out
    assert _module()._seed_demo_fixture() == 0  # idempotent
    second = capsys.readouterr().out
    assert "lessons_published" in first and "lessons_published" not in second
    for out in (first, second):  # counts only: never a secret
        assert "synthetic build-step passphrase" not in out and "4826" not in out


def test_seed_refuses_to_create_the_demo_family_without_its_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TALEEM_DEMO_SEED", "1")
    monkeypatch.setenv("TALEEM_ENV", "production")
    monkeypatch.setenv("TALEEM_DATABASE_URL", f"sqlite:///{tmp_path / 'taleem.db'}")
    monkeypatch.setenv("TALEEM_KDF_ITERATIONS", "1000")
    monkeypatch.delenv("TALEEM_DEMO_GUARDIAN_PASSPHRASE", raising=False)
    monkeypatch.delenv("TALEEM_DEMO_LEARNER_PIN", raising=False)
    assert _module()._seed_demo_fixture() == 1  # non-zero fails the build loudly
    assert "TALEEM_DEMO_GUARDIAN_PASSPHRASE is unset" in capsys.readouterr().err


def test_the_generic_fixture_seeder_still_refuses_production(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from taleem_core.tools.e2e_journey import _seed_from_environment

    monkeypatch.setenv("TALEEM_ENV", "production")
    monkeypatch.setenv("TALEEM_DATABASE_URL", "sqlite://")
    assert _seed_from_environment() == 1
    assert "refusing to seed" in capsys.readouterr().err
