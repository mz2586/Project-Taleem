"""Durable, shared per-learner AI usage ledger (``learning.ai_usage_ledger``, migration 0007).

Implements the ``LearnerUsageLedger`` port in SQL so the AI Teacher's per-learner quota holds across
every instance and survives restarts. Each gateway call appends one row of counts — provider, tier,
tokens, cost — attributed to the learner's pseudonymous ``student_ref``. No prompt or output text is
ever stored. ``purge_older_than`` is the hook for the future retention schedule.

Quota semantics across instances: the quota check reads the ledger, then the call is made and
recorded. Two instances serving the same learner at the *same instant* can therefore each pass the
check once, so a concurrent burst may overshoot a limit by at most (instances - 1) calls. Sequential
use — the normal case for one child on one device — is enforced exactly.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from .....ports.llm import UsageRecord, UsageSummary
from .models import AIUsageRow


class SqlLearnerUsageLedger:
    """``LearnerUsageLedger`` over the learning schema. Each method is its own short transaction."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def record(self, usage: UsageRecord) -> None:
        with self._sf() as session:
            session.add(
                AIUsageRow(
                    learner_ref=usage.learner_ref,
                    provider=usage.provider[:64],
                    tier=usage.tier.value,
                    purpose=usage.purpose[:64],
                    prompt_tokens=max(0, usage.prompt_tokens),
                    completion_tokens=max(0, usage.completion_tokens),
                    cost_micros=max(0, usage.cost_micros),
                    recorded_at=usage.recorded_at,
                )
            )
            session.commit()

    def usage_for(
        self, learner_ref: str, *, since: float = 0.0, until: float | None = None
    ) -> UsageSummary:
        stmt = select(
            func.count(AIUsageRow.id),
            func.coalesce(func.sum(AIUsageRow.prompt_tokens + AIUsageRow.completion_tokens), 0),
            func.coalesce(func.sum(AIUsageRow.cost_micros), 0),
        ).where(AIUsageRow.learner_ref == learner_ref, AIUsageRow.recorded_at >= since)
        if until is not None:
            stmt = stmt.where(AIUsageRow.recorded_at < until)
        with self._sf() as session:
            calls, tokens, cost = session.execute(stmt).one()
        return UsageSummary(calls=int(calls), tokens=int(tokens), cost_micros=int(cost))

    def by_learner(
        self, *, since: float = 0.0, until: float | None = None
    ) -> dict[str, UsageSummary]:
        stmt = (
            select(
                AIUsageRow.learner_ref,
                func.count(AIUsageRow.id),
                func.coalesce(func.sum(AIUsageRow.prompt_tokens + AIUsageRow.completion_tokens), 0),
                func.coalesce(func.sum(AIUsageRow.cost_micros), 0),
            )
            .where(AIUsageRow.recorded_at >= since)
            .group_by(AIUsageRow.learner_ref)
            .order_by(AIUsageRow.learner_ref)
        )
        if until is not None:
            stmt = stmt.where(AIUsageRow.recorded_at < until)
        with self._sf() as session:
            rows = session.execute(stmt).all()
        return {
            str(ref): UsageSummary(calls=int(c), tokens=int(t), cost_micros=int(m))
            for ref, c, t, m in rows
        }

    def purge_older_than(self, cutoff: float) -> int:
        with self._sf() as session:
            result = session.execute(delete(AIUsageRow).where(AIUsageRow.recorded_at < cutoff))
            session.commit()
        return int(getattr(result, "rowcount", 0) or 0)
