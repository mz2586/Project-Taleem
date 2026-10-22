"""Shared helpers for the store adapters: exact reference matching and JSON-safe row export."""

from __future__ import annotations

import dataclasses
import re
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import String, cast
from sqlalchemy.sql.elements import ColumnElement


def _boundary(ref: str) -> re.Pattern[str]:
    # A ref counts as mentioned only as a whole token: "stu_1" must not match "stu_10".
    return re.compile(rf"(?<![A-Za-z0-9_\-]){re.escape(ref)}(?![A-Za-z0-9_\-])")


def mentions(value: Any, ref: str) -> bool:
    """True if ``ref`` appears as a whole token anywhere inside ``value`` (recursively)."""
    pattern = _boundary(ref)

    def walk(v: Any) -> bool:
        if isinstance(v, str):
            return bool(pattern.search(v))
        if isinstance(v, dict):
            return any(walk(k) or walk(x) for k, x in v.items())
        if isinstance(v, (list, tuple, set, frozenset)):
            return any(walk(x) for x in v)
        return False

    return walk(value)


def text_contains(column: Any, ref: str) -> ColumnElement[bool]:
    """SQL prefilter: the column's text form contains ``ref`` (LIKE wildcards escaped).

    Always confirmed in Python with :func:`mentions` before any row is touched.
    """
    return cast(column, String).contains(ref, autoescape=True)


def affected(result: Any) -> int:
    """Rows affected by a bulk DML statement (``CursorResult.rowcount``)."""
    return int(getattr(result, "rowcount", 0) or 0)


def jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(jsonable(k)): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [jsonable(v) for v in value]
        return sorted(items, key=str) if isinstance(value, (set, frozenset)) else items
    return value


def row_dict(row: Any, *, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        col.key: jsonable(getattr(row, col.key))
        for col in row.__table__.columns
        if col.key not in exclude
    }
