"""Curriculum Studio — the AI-native curriculum authoring platform (governance-safe).

Internal authoring/review/versioning/publishing platform for original, NCP-aligned curriculum.
NO child data, NO live students, NO production content in Phase 3 — platform & tooling only.

Architecture: Clean/Hexagonal + DDD. The `domain` layer is pure-stdlib and framework-free and is
fully unit-tested; the FastAPI adapter lives at the edge (`adapters/api.py`).

Standards: docs/10-curriculum-studio/*.
"""
