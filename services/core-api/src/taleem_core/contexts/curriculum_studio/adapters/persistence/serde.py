"""Faithful (de)serialization between domain dataclasses and JSON-able dicts.

The Lesson aggregate is a deep graph of dataclasses + StrEnums + value objects (architecture §2:
the authored document is stored as a JSONB ``body``). Rather than a fragile hand-written
converter, we drive it from the dataclasses' own type hints so it stays correct as the domain
evolves (a new content block needs no change here).

- ``to_jsonable`` — dataclass → plain dict (enums → their value, enum-keyed dicts → string keys),
  producing content that is stable to hash and safe to store as JSONB.
- ``build`` — plain dict → a typed dataclass instance, coercing enums/nested dataclasses/lists/dicts
  back to their declared types (the inverse of ``to_jsonable``).

Only stdlib reflection is used; the domain remains framework-free.
"""

from __future__ import annotations

import dataclasses
import types
from enum import Enum
from typing import Any, TypeVar, Union, get_args, get_origin, get_type_hints

T = TypeVar("T")


def to_jsonable(value: Any) -> Any:
    """Recursively convert a domain value into a JSON-serializable structure."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {(k.value if isinstance(k, Enum) else k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    return value


def _is_optional(tp: Any) -> tuple[bool, Any]:
    """If ``tp`` is ``X | None`` return (True, X); otherwise (False, tp)."""
    origin = get_origin(tp)
    if origin is Union or origin is types.UnionType:
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return True, args[0]
    return False, tp


def _coerce(tp: Any, value: Any) -> Any:
    """Coerce a JSON value to the declared type ``tp`` (recursively)."""
    optional, inner = _is_optional(tp)
    if value is None:
        return None
    tp = inner if optional else tp

    if dataclasses.is_dataclass(tp) and isinstance(tp, type):
        return build(tp, value)

    if isinstance(tp, type) and issubclass(tp, Enum):
        return tp(value)

    origin = get_origin(tp)
    if origin in (list, tuple):
        (item_tp,) = get_args(tp) or (Any,)
        seq = [_coerce(item_tp, v) for v in value]
        return tuple(seq) if origin is tuple else seq
    if origin is dict:
        key_tp, val_tp = get_args(tp) or (Any, Any)
        return {_coerce(key_tp, k): _coerce(val_tp, v) for k, v in value.items()}

    return value


def build[T](cls: type[T], data: dict[str, Any]) -> T:
    """Construct an instance of dataclass ``cls`` from a plain dict (inverse of ``to_jsonable``)."""
    if not dataclasses.is_dataclass(cls):
        raise TypeError(f"build() requires a dataclass, got {cls!r}")
    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        kwargs[f.name] = _coerce(hints.get(f.name, Any), data[f.name])
    return cls(**kwargs)
