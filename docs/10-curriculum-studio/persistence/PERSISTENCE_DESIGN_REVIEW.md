# Curriculum Studio — Persistence Design Review

Reviewer role: independent Principal Engineer (adversarial). Subject: the persistence design in
[DATABASE_ARCHITECTURE.md](DATABASE_ARCHITECTURE.md), [ERD.md](ERD.md),
[POSTGRES_SCHEMA.md](POSTGRES_SCHEMA.md), [EVENT_MODEL.md](EVENT_MODEL.md).
Mandate (from the brief): review for **scalability, maintainability, performance, future
extensibility**. Implementation may begin **only if this review passes**.

Method: I attacked the design across four axes and along the Engineering Constitution
(no shortcuts, no silent failure, child safety, honesty). Each finding has a severity, the
concrete failure it predicts, and its resolution. A finding is only "resolved" if the resolution is
in the design (not a promise). The verdict and its conditions are at the end.

Severity: **C**ritical (blocks), **H**igh (must fix before GA), **M**edium (fix opportunistically),
**L**ow (note).

---

## Findings

### F1 (H) — FTS trigger silently indexes nothing if the body shape drifts

`cs_lesson_search_vector` reads fixed JSON paths (`body #>> '{title,text,ur}'`). If the domain
renames `title`→`heading`, the trigger keeps running, throws no error, and silently produces an
empty vector — search quietly rots. This violates "no silent failures."

Resolution (in design): the body shape is the domain's `LocalizedText`/`Lesson` value objects,
which are covered by domain tests; **additionally** the persistence test-suite asserts that a saved
lesson is findable by its title term (a search round-trip test). A shape change that breaks the path
fails that test in CI. The path contract is documented in POSTGRES_SCHEMA.md next to the trigger.
Accepted with the round-trip test as the guard. *Status: resolved.*

### F2 (H) — Audit hash-chain has a race on `prev_hash` under concurrent writes

Two concurrent mutations to the *same* entity could both read the same `prev_hash` and produce a
fork in the chain, defeating tamper-evidence. This is the classic append-chain concurrency bug.

Resolution (in design): the chain is **per-entity**, and every mutation to a mutable aggregate root
already takes that root's **optimistic lock** (`lock_version`, architecture §9). The audit row is
written in the *same* Unit of Work as the state change, so two concurrent writers to the same
`entity_id` cannot both commit — the loser fails the `lock_version` check and retries, re-reading
the new `prev_hash`. Thus the chain is serialized by the same mechanism that serializes the writes.
For append-only entities that have no `lock_version` (none currently emit audit outside a locked
root), the chain would instead need `SELECT … FOR UPDATE` on the latest chain row; documented as the
rule. *Status: resolved — architecture §7 updated to state the serialization guarantee.*

### F3 (M) — `item_statistics.item_ref` points into JSONB; item identity must be stable

Item psychometrics reference an assessment item by `item_ref` (a path/id inside the lesson `body`).
If item ids inside the body are not stable across edits, feedback attaches to the wrong item — a
correctness and, indirectly, a pedagogy risk.

Resolution (in design): assessment items in the body carry a stable `id` (per the `AssessmentItem`
domain type) that is preserved across edits; `item_ref` uses that id, not a positional path. The
coupling (stats key ↔ body item id) is documented in POSTGRES_SCHEMA.md and EVENT_MODEL.md, and the
inbound handler tolerates unmatched refs (stores them, flags them) rather than failing. This is the
accepted cost of keeping items in the document (architecture §2); the alternative (promoting every
item to a relational table) was weighed and rejected as over-normalization. *Status: resolved
(documented coupling + tolerant handler).*

### F4 (M) — DAG acyclicity is not enforceable by the database

`objective_prereq` can, at the SQL level, express a cycle; only a `CHECK` for self-loops exists.
A cycle would break prerequisite pathing (infinite loop / no valid order).

Resolution (in design): acyclicity is enforced in the application on edge insert (a reachability
check), which is the only correct place — Postgres cannot declaratively forbid a cycle. This is
explicitly documented in POSTGRES_SCHEMA.md. A periodic verifier job (recursive CTE) provides a
detection backstop. Accepted as an app-enforced invariant with a DB detection net. *Status:
accepted (documented, with a backstop verifier).*

### F5 (M) — Version snapshots duplicate the full body; unbounded growth on hot lessons

`lesson_version.body_snapshot` copies the whole body each publish. A frequently-revised lesson
could accumulate large duplicate snapshots.

Resolution (in design): immutability is worth more than the space (architecture §6), and at tens of
thousands of lessons with human-paced publishing the volume is trivial (megabytes, not terabytes).
Snapshots TOAST-compress (`lz4`); cold versions tier to cheaper storage under retention (doc 57).
Content-addressing makes an unchanged publish a no-op, so we never store identical back-to-back
snapshots. If a pathological case ever emerged, delta-encoding against the prior snapshot is an
additive change (a `base_version_no` + patch column) requiring no redesign. *Status: accepted with a
non-breaking escape hatch.*

### F6 (M) — RLS policies in the schema doc are illustrative, not complete

The `lesson` RLS policy shown covers soft-delete visibility but not per-state write authorization;
shipping partial RLS could give false confidence.

Resolution (in design): RLS is explicitly **defence-in-depth**; the authoritative authorization is
the application PDP (deny-by-default) and the domain workflow rules (no-self-approval enforced
server-side). POSTGRES_SCHEMA.md states this and marks write-policy RLS as delivered with the auth
model integration, not now. The baseline migration enables RLS + the visibility policy; write
policies are a later, additive migration tied to the auth epic. Honest scoping, not a gap. *Status:
accepted (scoped, documented, additive).*

### F7 (L) — Urdu full-text search has no stemming

`simple` config = exact/prefix only for Urdu; recall on morphological variants is limited.

Resolution (in design): documented as a known limitation with an upgrade path (custom dictionary /
`pg_trgm` assist, already added on `lesson_key`). Authoring search at this scale tolerates it;
learner-facing search is a different context. Honesty over a fake stemmer. *Status: accepted
(documented limitation).*

### F8 (L) — Polymorphic tables lack DB-level referential integrity

`translation`, `audit_log`, `outbox` reference entities by `(entity_type, entity_id)` with no FK.
An orphaned reference is possible if the app misbehaves.

Resolution (in design): this is the deliberate, standard trade-off for polymorphic audit/outbox
tables that must **outlive** their referents (you cannot FK to a row you intend to keep after the
row is gone). Integrity is enforced in the Unit of Work; audit/outbox rows are *supposed* to survive
deletion. Documented in POSTGRES_SCHEMA.md §Foreign keys and ERD.md §2. *Status: accepted by design.*

### F9 (L) — `search_path`-based schema addressing and cross-context isolation

Relying on `search_path` can surprise; and the "no cross-context FK" rule is a convention a future
migration could violate.

Resolution (in design): the ORM binds the schema explicitly per table (`__table_args__ = {"schema":
"curriculum_studio"}`), not via mutable `search_path`. Cross-context FKs are prevented by the
context living in its own schema with its own migration history and a CI check that migrations touch
only `curriculum_studio`. *Status: resolved (explicit schema binding + CI guard).*

---

## Axis assessment

**Scalability.** The design's central move — placing student-scale data (millions of interactions,
1M learners) in the delivery/analytics stores and keeping only tens of thousands of authored objects
here — is correct and is what makes every other choice (full normalization, rich indexing,
immutable versioning, RLS) affordable. The one large-growth table (`audit_log`) is partitioned. The
1M read fan-out is served by event-fed read models, never the authoring primary. This scales for a
decade because authored-object count grows with curriculum breadth (bounded), not user count. **Pass.**

**Maintainability.** One schema, one migration history, expand/contract discipline, reversible
migrations tested in CI, Purpose on every table, justification on every index. The hybrid
relational+JSONB body means domain evolution is mostly no-DDL. The Repository/UoW boundary keeps the
domain pure and swappable. **Pass.**

**Performance.** Hot paths (placement list, workflow dashboards, version timeline, outbox drain,
coverage queries) each have a justified, often-partial index; equality-then-range column order;
UUIDv7 keeps PK inserts sequential; FTS via GIN; outbox drain via a tiny partial index +
`SKIP LOCKED`. No hot-path query filters inside JSON. **Pass.**

**Future extensibility.** New curriculum authorities, provinces, countries, and languages are
**rows**, not migrations (`education_system.parent_system_id`, free-form `locale`, versioned
taxonomy). New content blocks are JSON-shape changes with no DDL. New events are additive
(tolerant-reader + `event_version`). Delta-encoded snapshots, an authoring search index, and CDC
event delivery are all reachable without a redesign. **Pass.**

---

## Verdict

**PASS — cleared for implementation.**

No Critical findings. F1 and F2 (High) are resolved *in the design* (a CI round-trip test for the
FTS path; the optimistic-lock serialization of the audit chain, now stated in architecture §7). All
Medium/Low findings are either resolved or accepted with documented rationale and a non-breaking
escape hatch. No finding requires a schema redesign; none is deferred silently.

Conditions carried into implementation (tracked as acceptance criteria of the build task):

1. A persistence test asserts FTS title round-trip (guards F1).
2. The audit row is written inside the same UoW as the mutation, under the aggregate's optimistic
   lock (guards F2). No audit write outside a locked root without a `FOR UPDATE` on the chain tail.
3. Assessment-item `id`s in the body are stable across edits; `item_ref` uses them (guards F3).
4. Alembic migration is reversible and verified `upgrade → downgrade → upgrade` against a real
   PostgreSQL before merge (architecture §20).
5. ORM binds `schema="curriculum_studio"` explicitly; no reliance on mutable `search_path` (F9).
6. `item_statistics` and every table remain free of `student_ref` / child PII (architecture §16) —
   asserted by a schema test.

Implementation may proceed against the SQLAlchemy 2.x + Alembic + Repository + Unit of Work plan,
replacing `InMemoryLessonRepository` behind the existing `LessonRepository` port.
