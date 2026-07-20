"""Clock port (pure-stdlib) — inject time so time-dependent logic is testable."""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> float: ...
    def now_ms(self) -> int: ...


class SystemClock:
    def now(self) -> float:
        return time.time()

    def now_ms(self) -> int:
        return int(time.time() * 1000)


class FakeClock:
    """Manually-advanced clock for deterministic tests."""

    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def now(self) -> float:
        return self._t

    def now_ms(self) -> int:
        return int(self._t * 1000)

    def advance(self, seconds: float) -> None:
        self._t += seconds
