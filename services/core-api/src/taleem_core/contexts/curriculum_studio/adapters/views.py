"""Response views for the Curriculum Studio API: lesson content, answer-key redaction, ETags.

Field names follow ``Lesson.to_dict()`` (the Studio review UI reads them as-is). Answer keys are
the one thing a view must never leak by accident: they are stripped from every list and mutation
response, and served only on a single-lesson / single-version read for reviewer and architect
roles (``ANSWER_KEY_ROLES``).
"""

from __future__ import annotations

from typing import Any

from ..domain.content import Locale, LocalizedText
from ..domain.lesson import Lesson
from ..domain.packs import default_registry
from ..domain.versioning import Version
from ..domain.workflow import STATE_ROLE
from .persistence import serde

# Who may see answer keys: the five review-stage roles and the curriculum architect (publisher).
ANSWER_KEY_ROLES: frozenset[str] = frozenset({*STATE_ROLE.values(), "curriculum_architect"})

# Assessment-item fields that reveal the answer.
ANSWER_FIELDS: tuple[str, ...] = ("answer_key", "accepted_variants", "auto_marking_guidance")

# Lesson fields not echoed as content: identity/flat title are shown separately, bookkeeping is
# shown as ``workflow`` / ``gates`` / ``version``, and published snapshots have their own route.
_NOT_CONTENT = ("lesson_id", "title", "workflow", "quality_gate_results", "version")
_NEVER = ("version_history",)


def may_see_answer_keys(role: str) -> bool:
    return role in ANSWER_KEY_ROLES


def redact_answer_keys(value: Any) -> Any:
    """Recursively drop ``ANSWER_FIELDS`` from every assessment item (a dict with ``item_id``)."""
    if isinstance(value, dict):
        is_item = "item_id" in value and "answer_key" in value
        return {
            k: redact_answer_keys(v)
            for k, v in value.items()
            if not (is_item and k in ANSWER_FIELDS)
        }
    if isinstance(value, list):
        return [redact_answer_keys(v) for v in value]
    return value


def etag(lesson: Lesson) -> str:
    """Strong ETag of the authored content (changes iff the content changes)."""
    return '"' + lesson.content_hash().removeprefix("sha256:") + '"'


def text_of(field: LocalizedText) -> dict[str, str]:
    return {str.__str__(k): v for k, v in field.text.items()}


def lesson_view(lesson: Lesson, *, answer_keys: bool = False) -> dict[str, Any]:
    full = serde.to_jsonable(lesson)
    content = {k: v for k, v in full.items() if k not in _NOT_CONTENT and k not in _NEVER}
    view: dict[str, Any] = {
        "lesson_id": lesson.lesson_id,
        "title": text_of(lesson.title),
        "title_audio": {str.__str__(k): v for k, v in lesson.title.audio_ref.items()},
        "grade": lesson.metadata.grade_key,
        "subject": lesson.metadata.subject_key,
        "curriculum_pack": lesson.metadata.curriculum_pack,
        "instructional_locales": [str.__str__(t) for t in lesson.metadata.instructional_locales],
        "state": lesson.workflow.state.value,
        "version": lesson.version,
        "learning_outcomes": list(lesson.learning_outcomes),
        "gates": [
            {
                "gate": g.gate.value,
                "passed": g.passed,
                "mode": g.mode,
                "reviewer_role": g.reviewer_role,
                "reviewer_subject": g.reviewer_subject,
                "at": g.at,
            }
            for g in lesson.quality_gate_results
        ],
        **content,
        "workflow": full["workflow"],
        "etag": etag(lesson),
        "answer_keys_included": answer_keys,
    }
    return view if answer_keys else redact_answer_keys(view)


def version_view(version: Version, *, body: bool = False, answer_keys: bool = False) -> Any:
    view: dict[str, Any] = {
        "version": version.version,
        "content_hash": version.content_hash,
        "change_summary": version.change_summary,
        "author_role": version.author_role,
        "created_at": version.created_at,
    }
    if body:
        snapshot = serde.to_jsonable(version.snapshot)
        snapshot = {k: v for k, v in snapshot.items() if k not in _NEVER}
        view["body"] = snapshot if answer_keys else redact_answer_keys(snapshot)
        view["answer_keys_included"] = answer_keys
    return view


class LocaleError(ValueError):
    """A localized map uses a malformed tag or a locale its curriculum pack does not declare."""


def localized_map(raw: dict[str, str], pack_id: str, field: str) -> dict[Locale, str]:
    """Validate a ``{locale: text}`` map against the lesson's pack (unknown pack: syntax only)."""
    pack = default_registry().get(pack_id)
    out: dict[Locale, str] = {}
    for tag, text in raw.items():
        try:
            loc = Locale(tag)
        except ValueError as exc:
            raise LocaleError(str(exc)) from exc
        if pack is not None and not pack.supports_locale(loc):
            raise LocaleError(f"{field} locale {tag!r} is not a locale of pack {pack.pack_id}")
        out[loc] = text
    return out
