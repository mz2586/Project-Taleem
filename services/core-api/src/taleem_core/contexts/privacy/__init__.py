"""Privacy context — per-learner data export, two-step erasure, and the retention schedule.

Orchestrates data-subject rights across every store that holds learner data (identity, learning,
in-process sync and session state, the AI usage ledger) through one ``LearnerDataPort`` per store.
The adapters read other contexts' ORM models and in-process stores; no other context's code is
changed. See ``docs/03-security-privacy/14-privacy-model.md`` §6 and ``57-data-retention-schedule``.

Everything this context *retains* after an erasure, and every retention period, is configuration
that is **PENDING M-Gov approval** — no legal period is invented here.
"""
