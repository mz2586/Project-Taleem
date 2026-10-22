"""Learner permission gate for offline sync — now the shared ``auth.learner_gate``.

Sync was the first surface to re-check live consent and account status (a device can hold a child's
answers for days, and an operator token carries none of the learner's state). The check is now
shared by every learner surface; this module keeps the sync-facing names stable.

A refused learner rejects the **whole batch** (nothing applied) with 403 ``CONSENT_REQUIRED`` /
``LEARNER_INACTIVE``; the client holds the deltas (never deleted, never retried in a loop).
"""

from __future__ import annotations

from ...auth.learner_gate import (
    CONSENT_REQUIRED,
    LEARNER_INACTIVE,
    IdentityLearnerGate,
    LearnerGate,
    LearnerRefusedError,
    enforce,
)

# Sync-facing aliases (kept for callers and tests written against the sync context).
IdentitySyncGate = IdentityLearnerGate
SyncRefusedError = LearnerRefusedError

__all__ = [
    "CONSENT_REQUIRED",
    "LEARNER_INACTIVE",
    "IdentitySyncGate",
    "LearnerGate",
    "SyncRefusedError",
    "enforce",
]
