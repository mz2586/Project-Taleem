"""OpenAPI contract parity — Software Completion Mode (audit remediation).

Guards against the drift where a whole API surface ships with no OpenAPI contract (the `/v1/ops/*`
routes were added without one). For every non-trivial `/v1/...` path the app actually serves, some
contract in ``packages/contracts`` must document it; and every path a contract documents must exist
in the app. Health/metrics/skeleton live in the root ``openapi.yaml``.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from taleem_core.main import create_app
from taleem_core.platform.config import Settings

_CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "packages" / "contracts"
_PARAM = re.compile(r"\{[^}]+\}")


def _normalize(path: str) -> str:
    """Compare path *structure*, ignoring parameter names (code uses snake_case placeholders,
    contracts use camelCase — the same URL template)."""
    return _PARAM.sub("{}", path)


def _app_paths() -> set[str]:
    app = create_app(Settings(database_url=""))
    return {_normalize(p) for p in app.openapi()["paths"]}


def _documented_paths() -> set[str]:
    documented: set[str] = set()
    for yml in _CONTRACTS_DIR.glob("*.yaml"):
        spec = yaml.safe_load(yml.read_text(encoding="utf-8"))
        documented |= {_normalize(p) for p in (spec or {}).get("paths", {})}
    return documented


def test_contracts_dir_present() -> None:
    assert _CONTRACTS_DIR.is_dir(), _CONTRACTS_DIR
    assert list(_CONTRACTS_DIR.glob("*.yaml")), "no contract files found"


def test_every_served_v1_path_is_documented() -> None:
    documented = _documented_paths()
    missing = sorted(p for p in _app_paths() if p.startswith("/v1/") and p not in documented)
    assert not missing, f"served but undocumented in any OpenAPI contract: {missing}"


def test_every_documented_path_is_served() -> None:
    served = _app_paths()
    orphan = sorted(p for p in _documented_paths() if p not in served)
    assert not orphan, f"documented in a contract but not served by the app: {orphan}"


def test_ops_surface_is_documented() -> None:
    # The specific regression this audit fixed: the ops API must be documented.
    documented = _documented_paths()
    for path in (
        "/v1/ops/kill-switch",
        "/v1/ops/kill-switch:engage",
        "/v1/ops/kill-switch:disengage",
        "/v1/ops/status",
    ):
        assert path in documented, path
