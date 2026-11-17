"""The review pack's phrase table matches the live phrase list (docs/safeguarding/...)."""

from __future__ import annotations

import json

import pytest

from taleem_core.tools import safeguarding_phrase_table as table


def test_review_pack_table_is_current(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["safeguarding_phrase_table", "--check"])
    assert table.main() == 0


def test_every_live_phrase_appears_exactly_once() -> None:
    rendered = table.render()
    data = json.loads(table.PHRASES.read_text(encoding="utf-8"))
    for phrase in data["phrases"]:
        assert rendered.count(f"| `{phrase['id']}` |") == 1
