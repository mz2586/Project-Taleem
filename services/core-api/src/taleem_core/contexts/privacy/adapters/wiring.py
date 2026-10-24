"""Composition helper: one call from main.py builds the privacy service over every store."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ..application.service import PrivacyService
from ..domain.policy import PrivacyConfig
from .identity_data import IdentityLearnerData
from .learning_data import LearningLearnerData
from .memory_data import AiUsageLearnerData, GuardianViewData, SyncLearnerData
from .reporting_data import ReportingLearnerData
from .safeguarding_data import SafeguardingLearnerData
from .school_data import SchoolLearnerData


def build_privacy_service(
    *,
    identity_sf: sessionmaker[Session],
    learning_sf: sessionmaker[Session],
    school_sf: sessionmaker[Session],
    safeguarding_sf: sessionmaker[Session],
    reporting_sf: sessionmaker[Session],
    session_store: Any,
    sync_store: Any,
    ai_ledger: Any,
    env: Mapping[str, str],
    production: bool,
    clock: Callable[[], float],
) -> PrivacyService:
    return PrivacyService(
        IdentityLearnerData(identity_sf),
        [
            LearningLearnerData(learning_sf, session_store),
            SchoolLearnerData(school_sf),
            SafeguardingLearnerData(safeguarding_sf),
            ReportingLearnerData(reporting_sf),
            SyncLearnerData(sync_store),
            AiUsageLearnerData(ai_ledger),
            GuardianViewData(),
        ],
        PrivacyConfig.from_env(env, production=production),
        clock,
    )
