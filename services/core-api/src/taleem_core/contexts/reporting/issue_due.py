"""Scheduler / ops entrypoint: Taleem issues every eligible learner's report card for a period.

    python -m taleem_core.contexts.reporting.issue_due --period 2026-09
    python -m taleem_core.contexts.reporting.issue_due --start 1756684800 --end 1759276800

``--period YYYY-MM`` is a UTC calendar month (start inclusive, end exclusive). The period must be
closed (its end not in the future). Every learner account is tried; ``issue_for_learner`` itself
refuses a learner without an active account and live learning consent, and never issues a second
system card for the same learner and period — so a re-run is safe and only fills gaps. Learners in
no class get cards too. Prints a JSON summary (counts and card ids only; no names).
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from ...platform.cohort import REAL, reading_as
from ...platform.errors import Problem


class _Issuer(Protocol):
    def issue_for_learner(
        self, student_ref: str, period_start: int, period_end: int
    ) -> dict[str, Any]: ...


def month_period(value: str) -> tuple[int, int]:
    """``YYYY-MM`` -> (first second of the month, first second of the next), UTC."""
    try:
        year, month = (int(part) for part in value.split("-", 1))
        start = datetime(year, month, 1, tzinfo=UTC)
    except ValueError as exc:
        raise ValueError(f"--period must be YYYY-MM, not {value!r}") from exc
    days = calendar.monthrange(year, month)[1]
    end = start.timestamp() + days * 86_400
    return int(start.timestamp()), int(end)


def issue_due(
    service: _Issuer,
    learners: Iterable[str],
    start: int,
    end: int,
    cohort_of: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Issue each learner's card. ``cohort_of`` (the learner account's cohort) makes each card
    derive from the lessons that learner can see (DEMO_COHORT_CONTRACT §3); without it every card
    is derived as the real cohort."""
    issued: list[str] = []
    existing = not_eligible = 0
    for ref in learners:
        try:
            with reading_as(cohort_of(ref) if cohort_of is not None else REAL):
                card = service.issue_for_learner(ref, start, end)
            issued.append(str(card["card_id"]))
        except Problem as exc:
            if exc.status == 409:
                existing += 1
            elif exc.status == 403:
                not_eligible += 1
            else:
                raise
    return {
        "period_start": start,
        "period_end": end,
        "issued": len(issued),
        "already_issued": existing,
        "not_eligible": not_eligible,
        "card_ids": issued,
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    app_factory: Callable[[], Any] | None = None,
    out: Callable[[str], object] = print,
) -> int:
    parser = argparse.ArgumentParser(prog="issue_due", description=__doc__.splitlines()[0])
    parser.add_argument("--period", help="a UTC calendar month, YYYY-MM")
    parser.add_argument("--start", type=int, help="period start, epoch seconds (inclusive)")
    parser.add_argument("--end", type=int, help="period end, epoch seconds (exclusive)")
    args = parser.parse_args(argv)
    try:
        if args.period:
            start, end = month_period(args.period)
        elif args.start is not None and args.end is not None:
            start, end = args.start, args.end
        else:
            parser.error("give --period YYYY-MM, or both --start and --end")
    except ValueError as exc:
        parser.error(str(exc))
    if app_factory is None:  # the composition root, built only when run as a program
        from ...main import create_app

        app_factory = create_app
    app = app_factory()
    try:
        summary = issue_due(
            app.state.reporting_service,
            app.state.reporting_learner_refs(),
            start,
            end,
            cohort_of=getattr(app.state, "learner_cohort", None),
        )
    except Problem as exc:  # an invalid period (422): report it, exit non-zero
        out(json.dumps({"error": exc.code, "detail": exc.detail}))
        return 2
    out(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main() in the tests
    sys.exit(main())
