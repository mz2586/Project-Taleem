"""SQLAlchemy implementation of the ``HierarchyRepository`` port, over the EXISTING taxonomy tables.

Mapping (no new migration):

- ``education_system`` — one row per curriculum pack. PK-NCP maps to the row lessons already use
  (``NCP-2023-NATIONAL``) so lessons and their hierarchy share one system; any other pack uses its
  pack id as ``system_key``.
- ``grade`` — one row per grade key (``display_order`` = position in the pack's grade order).
- ``subject`` — one row per subject key within the system. ``titles`` keeps the documented
  ``{locale: title}`` shape at the top level, plus one reserved key, ``"_structure"`` (never a valid
  locale tag), holding the per-grade placement:
  ``{grade_key: {"position": int, "title": LocalizedText, "chapters": [Chapter...]}}``.

Chapters and topics have no table in the baseline schema, so they live in that JSON. A dedicated
``chapter``/``topic`` table (a migration) is the proper home once the hierarchy is queried directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .....platform.ids import uuid7
from ...domain.content import LocalizedText
from ...domain.hierarchy import Chapter, EducationSystem, Grade, Subject, canonicalize
from ...domain.packs import DEFAULT_PACK_ID, CurriculumPack
from . import serde
from .models import EducationSystemRow, GradeRow, SubjectRow
from .repository import DEFAULT_SYSTEM_KEY

if TYPE_CHECKING:
    from .uow import UnitOfWork

STRUCTURE_KEY = "_structure"


def system_key_for(pack_id: str) -> str:
    return DEFAULT_SYSTEM_KEY if pack_id == DEFAULT_PACK_ID else pack_id


class SqlAlchemyHierarchyRepository:
    def __init__(self, session: Session, uow: UnitOfWork) -> None:
        self._session = session
        self._uow = uow

    # -- port surface ---------------------------------------------------------------------

    def get(self, pack_id: str) -> EducationSystem | None:
        system = self._system_row(pack_id)
        if system is None:
            return None
        grade_rows = self._session.execute(
            select(GradeRow)
            .where(GradeRow.system_id == system.id)
            .order_by(GradeRow.display_order, GradeRow.grade_key)
        ).scalars()
        grades = [Grade(grade_id="", key=g.grade_key) for g in grade_rows]
        if not grades:
            return None
        placed: dict[str, list[tuple[int, Subject]]] = {g.key: [] for g in grades}
        for row in self._subject_rows(system.id).values():
            structure: dict[str, Any] = (row.titles or {}).get(STRUCTURE_KEY, {})
            for grade_key, entry in structure.items():
                if grade_key not in placed:
                    continue
                subject = Subject(
                    subject_id="",
                    key=row.subject_key,
                    title=serde.build(LocalizedText, entry.get("title", {})),
                    chapters=[serde.build(Chapter, c) for c in entry.get("chapters", [])],
                )
                placed[grade_key].append((int(entry.get("position", 0)), subject))
        for grade in grades:
            grade.subjects = [s for _, s in sorted(placed[grade.key], key=lambda p: p[0])]
        return canonicalize(
            EducationSystem(system_id="", key=pack_id, name=system.name, grades=grades)
        )

    def save(self, system: EducationSystem, pack: CurriculumPack) -> None:
        sys_row = self._system_row(pack.pack_id)
        if sys_row is None:
            sys_row = EducationSystemRow(
                id=uuid7(),
                system_key=system_key_for(pack.pack_id),
                name=system.name or pack.education_system,
                jurisdiction="national",
                curriculum_version=pack.version,
            )
            self._session.add(sys_row)
            self._session.flush()
        # An existing system row (e.g. the one lessons already use) keeps its name and version.

        order = {k: i for i, k in enumerate(pack.grade_keys)}
        existing_grades = {
            g.grade_key: g
            for g in self._session.execute(
                select(GradeRow).where(GradeRow.system_id == sys_row.id)
            ).scalars()
        }
        placements: dict[str, dict[str, Any]] = {}
        titles: dict[str, dict[str, str]] = {}
        for grade in system.grades:
            row = existing_grades.get(grade.key)
            display = order.get(grade.key, len(order))
            if row is None:
                self._session.add(
                    GradeRow(
                        id=uuid7(),
                        system_id=sys_row.id,
                        grade_key=grade.key,
                        display_order=display,
                    )
                )
            else:
                row.display_order = display
            for position, subj in enumerate(grade.subjects):
                placements.setdefault(subj.key, {})[grade.key] = {
                    "position": position,
                    "title": serde.to_jsonable(subj.title),
                    "chapters": serde.to_jsonable(subj.chapters),
                }
                for loc, text in subj.title.text.items():
                    if text.strip():
                        titles.setdefault(subj.key, {}).setdefault(str.__str__(loc), text)

        subject_rows = self._subject_rows(sys_row.id)
        for subject_key, structure in placements.items():
            srow = subject_rows.get(subject_key)
            previous: dict[str, Any] = {}
            if srow is None:
                srow = SubjectRow(id=uuid7(), system_id=sys_row.id, subject_key=subject_key)
                self._session.add(srow)
            else:
                previous = dict(srow.titles or {})
            merged_structure = {**previous.get(STRUCTURE_KEY, {}), **structure}
            top = {k: v for k, v in previous.items() if k != STRUCTURE_KEY}
            top.update(titles.get(subject_key, {}))
            # Assign a new dict so the JSON column change is always detected.
            srow.titles = {**top, STRUCTURE_KEY: merged_structure}

        self._uow.record_audit(
            entity_type="education_system",
            entity_id=sys_row.id,
            action="hierarchy_upsert",
            after={
                "pack_id": pack.pack_id,
                "pack_version": pack.version,
                "grades": [g.key for g in system.grades],
                "subjects": sorted(placements),
            },
        )

    # -- internals ------------------------------------------------------------------------

    def _system_row(self, pack_id: str) -> EducationSystemRow | None:
        return self._session.execute(
            select(EducationSystemRow).where(
                EducationSystemRow.system_key == system_key_for(pack_id)
            )
        ).scalar_one_or_none()

    def _subject_rows(self, system_id: str) -> dict[str, SubjectRow]:
        rows = self._session.execute(
            select(SubjectRow).where(SubjectRow.system_id == system_id)
        ).scalars()
        return {r.subject_key: r for r in rows}
