"""The reader's cohort: which audience of published content a request may see.

Accounts carry a ``cohort``: ``""`` (real) or ``"demo"`` (the designated synthetic demo accounts,
set only by ``tools/demo_cohort.py`` through a non-HTTP application-service method). A lesson
carries ``metadata.audience``: ``""`` (everyone) or ``"demo"``. A lesson is visible to a reader iff
its audience is ``""`` or equals the reader's cohort — so a real reader never sees demo content,
and a demo reader sees demo content plus every real published lesson.

The reader's cohort is a per-request value held in a context variable:

- The composition root installs, per request, a **lazy** resolver that verifies the bearer token
  and reads the cohort from the **account** (learner / guardian / teacher). The token's
  informational ``cohort`` claim is never consulted. The resolver runs only when a read actually
  needs it, at most once per request.
- Anything outside a request (scripts, background jobs) reads as the real cohort unless it says
  otherwise with ``reading_as``.

**Fail closed:** no resolver, an unverifiable token, a resolver error or an unknown cohort value
all mean the real cohort, which sees no demo content. The only effect of a failure is that a demo
reader does not see demo lessons.
"""

from __future__ import annotations

import contextvars
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

REAL = ""
DEMO = "demo"
COHORTS: tuple[str, ...] = (REAL, DEMO)
# Lesson audiences are the same vocabulary: "" = everyone, "demo" = the demo cohort only.
AUDIENCES: tuple[str, ...] = COHORTS


def normalise_cohort(value: object) -> str:
    """A stored or resolved value as a known cohort; anything unknown is the real cohort."""
    return value if isinstance(value, str) and value in COHORTS else REAL


class _LazyCohort:
    """Resolves the reader's cohort once, on first use (thread-safe; shared by context copies)."""

    def __init__(self, resolve: Callable[[], str]) -> None:
        self._resolve = resolve
        self._value: str | None = None
        self._lock = threading.Lock()

    def get(self) -> str:
        with self._lock:
            if self._value is None:
                try:
                    self._value = normalise_cohort(self._resolve())
                except Exception:  # fail closed: any resolution failure reads as the real cohort
                    self._value = REAL
            return self._value


_reader: contextvars.ContextVar[_LazyCohort | None] = contextvars.ContextVar(
    "taleem_reader_cohort", default=None
)


def current_reader_cohort() -> str:
    """The cohort of whoever the current request reads for (``""`` when unknown)."""
    holder = _reader.get()
    return holder.get() if holder is not None else REAL


def install_reader(resolve: Callable[[], str]) -> contextvars.Token[_LazyCohort | None]:
    """Install a lazy resolver for the current context; returns the token for ``reset_reader``."""
    return _reader.set(_LazyCohort(resolve))


def reset_reader(token: contextvars.Token[_LazyCohort | None]) -> None:
    _reader.reset(token)


@contextmanager
def reading_as(cohort: str) -> Iterator[None]:
    """Read as ``cohort`` inside the block (seeder, background jobs, tests)."""
    token = install_reader(lambda: cohort)
    try:
        yield
    finally:
        reset_reader(token)


def visible_to(audience: object, cohort: str) -> bool:
    """True iff content with ``audience`` may be shown to a reader of ``cohort``."""
    if audience is None or audience == REAL:
        return True  # everyone's content
    # Restricted content: only a reader of exactly that (non-real) cohort. An unknown audience
    # value is restricted to a cohort nobody has, i.e. hidden from everyone.
    return isinstance(audience, str) and cohort != REAL and audience == cohort
