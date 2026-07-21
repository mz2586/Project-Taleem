# Curriculum Studio — Event Model

Companion to [DATABASE_ARCHITECTURE.md](DATABASE_ARCHITECTURE.md) (§10, §17) and
[POSTGRES_SCHEMA.md](POSTGRES_SCHEMA.md) (`outbox`). Defines the domain events Curriculum Studio
emits, the transactional-outbox mechanism that guarantees they are never lost, the envelope and
per-event schemas, versioning rules, and consumer contracts.

Guiding rule: **the outbox is the only egress from this context.** Curriculum Studio never writes
into another context's database and never calls another context synchronously in a write path.
Integration is by events, at-least-once, with idempotent consumers. This is what keeps the
authoring primary off the 1M-student read path (architecture §0, §10).

---

## 1. Why an outbox (not direct publish, not dual-write)

A publish must do two things atomically: change local state *and* tell the world. Doing them as
two separate operations (write DB, then call a broker) is the classic dual-write bug — a crash
between them loses the event or emits a phantom. The **transactional outbox** removes the failure
window:

1. The state change and an `outbox` row are written in **one local transaction**. Either both
   commit or neither does — the event is as durable as the fact it describes.
2. A separate **relay** reads unpublished `outbox` rows and delivers them to the broker / consumers,
   marking them published on success. Delivery is retried until it succeeds.

Result: **exactly the events that happened, at least once each, never lost, never phantom.**
Consumers dedupe (§6) to make at-least-once effectively exactly-once.

---

## 2. The relay

- **Poll mode (baseline):** every *N* ms, `SELECT ... FROM outbox WHERE published_at IS NULL
  ORDER BY occurred_at FOR UPDATE SKIP LOCKED LIMIT k`, deliver, then set `published_at = now()`,
  `delivery_attempts = delivery_attempts + 1`. `SKIP LOCKED` lets multiple relay workers run
  without contending. The partial index `ix_outbox_unpublished` keeps this poll cheap regardless of
  total table size.
- **CDC mode (later, no schema change):** logical decoding streams `outbox` inserts to the broker
  with lower latency. The table design is identical; only the drainer changes.
- **Ordering:** per aggregate, events are ordered by `occurred_at` and a monotonic version
  (`version_no` for lessons). Cross-aggregate ordering is not guaranteed and consumers must not
  assume it.
- **Backpressure / failure:** a row that fails delivery stays unpublished and is retried with
  exponential backoff (tracked by `delivery_attempts`); after a threshold it is flagged for the
  dead-letter workflow and alerted. Nothing is dropped.
- **Retention:** delivered rows are pruned after a short audit window (default 14 days) by a
  maintenance job. The permanent record of what happened is `audit_log`, **not** the outbox
  (architecture §7, §17) — the two have deliberately different retention.

---

## 3. Event envelope

Every event shares one envelope so consumers parse uniformly. Stored as the `outbox.payload` plus
top-level columns; delivered as a single JSON document.

```json
{
  "event_id": "0190f2c1-7e3a-7b6c-9a1d-2f4e6a8c0b11",
  "event_type": "LessonPublished",
  "event_version": 1,
  "occurred_at": "2026-07-20T09:15:23.481Z",
  "producer": "curriculum_studio",
  "aggregate": { "type": "lesson", "id": "0190f2b0-...", "version_no": 3 },
  "correlation_id": "req-7f3c...",
  "data": { }
}
```

| Field | Meaning |
| --- | --- |
| `event_id` | UUIDv7; the idempotency key consumers dedupe on. |
| `event_type` | Discriminator (§4). |
| `event_version` | Schema version of `data` (§5). |
| `occurred_at` | When the fact happened (server time, same tx). |
| `producer` | Always `curriculum_studio`. |
| `aggregate` | Type + id (+ `version_no` for versioned aggregates) — the natural dedupe/order key. |
| `correlation_id` | Ties the event to the originating request across contexts and to `audit_log`. |
| `data` | Event-specific payload (§4). Contains **no PII** (there is none in this context). |

---

## 4. Event catalogue

All events are **facts in the past tense**. `data` payloads carry ids and hashes, not full bodies —
consumers fetch the immutable version if they need content (keeps events small and avoids stale
duplication). Every event is emitted **in the same transaction** as the mutation that caused it.

### `LessonPublished` (`event_version: 1`)

Emitted when a lesson is published to a new immutable version (architecture §10). The trigger for
every downstream read model to ingest new curriculum.

```json
{
  "lesson_id": "0190f2b0-...",
  "version_no": 3,
  "content_hash": "sha256:9f2b...",
  "system_key": "NCP-2023-NATIONAL",
  "grade_key": "G1",
  "subject_key": "math",
  "learning_outcomes": ["MATH-G1-N-01", "MATH-G1-N-02"],
  "languages": ["ur", "en"],
  "published_by": "curriculum_architect"
}
```

Consumers: Curriculum Engine (activates the version), AI Knowledge Base (indexes for RAG —
approved content only), learner Search index, Offline-Package builder.

### `LessonVersionRolledBack` (`event_version: 1`)

Emitted when a rollback creates a new head from a prior version (architecture §6). Rollback is
forward-moving, so this is a publish-like fact with provenance of what it restored.

```json
{
  "lesson_id": "0190f2b0-...",
  "new_version_no": 5,
  "restored_from_version_no": 3,
  "content_hash": "sha256:9f2b...",
  "actor_role": "curriculum_architect"
}
```

Consumers: same as `LessonPublished` (they re-point to the new active version).

### `LessonArchived` (`event_version: 1`)

Emitted when a published lesson is archived (retired from the active curriculum). Consumers stop
serving it to new learners; existing offline packs remain valid until refreshed.

```json
{ "lesson_id": "0190f2b0-...", "last_version_no": 5, "actor_role": "curriculum_architect", "reason": "superseded" }
```

### `ObjectiveAdded` / `ObjectiveUpdated` (`event_version: 1`)

Emitted when the SLO taxonomy changes for a curriculum edition. Consumers that model the
prerequisite DAG (mastery/pathing) update their copy.

```json
{
  "objective_id": "0190f2aa-...",
  "system_key": "NCP-2023-NATIONAL",
  "curriculum_version": "2023",
  "standard_code": "MATH-G1-N-01",
  "grade_key": "G1",
  "subject_key": "math",
  "prerequisite_codes": ["MATH-G1-N-00"]
}
```

### `MediaAssetApproved` (`event_version: 1`)

Emitted when a media asset passes scan + license checks and becomes linkable/publishable. Lets the
CDN/pre-warm and integrity systems react.

```json
{ "media_id": "0190f2c9-...", "content_hash": "sha256:...", "kind": "diagram", "mime": "image/svg+xml", "license": "cc0" }
```

### Inbound (consumed, not produced): `ItemStatisticsUpdated`

The one event Curriculum Studio **consumes** — aggregated, de-identified psychometrics from the
Analytics warehouse (architecture §16). Handled idempotently by upserting `item_statistics`
keyed on `(item_ref, sample_window)`. Carries **no `student_ref`** and is rejected if it does
(a schema guard, protecting the no-PII invariant).

```json
{
  "item_ref": "L-math-g1-add::item-04",
  "lesson_id": "0190f2b0-...",
  "attempts": 12840,
  "p_value": 0.41,
  "discrimination": 0.28,
  "mean_time_s": 37.5,
  "misconception_hit_rate": { "carry-omitted": 0.22 },
  "sample_window": "2026-Q2"
}
```

---

## 5. Schema versioning and evolution

- `event_version` is bumped only on a **breaking** change to a `data` shape (removed/renamed field,
  changed meaning). Additive optional fields do **not** bump the version — consumers must ignore
  unknown fields (tolerant reader).
- Producers may emit **two versions in parallel** during a migration window (expand/contract at the
  event level), then retire the old. This mirrors the DB migration discipline (architecture §20).
- Event schemas are contract-tested: a golden sample per `(event_type, event_version)` lives with
  the tests, and a consumer-driven contract check fails CI if a producer change would break a
  known consumer.
- Event `data` is **never** the source of truth for content — it carries ids + hashes. If a
  consumer needs the body, it fetches the immutable `lesson_version` by `content_hash`. This makes
  events small, cache-friendly, and immune to body-shape drift.

---

## 6. Delivery semantics and idempotency (consumer contract)

- **At-least-once.** Consumers **must** be idempotent. The dedupe key is `event_id` (preferred) or
  the natural key `(aggregate.id, aggregate.version_no)` for versioned facts. Processing the same
  `LessonPublished` twice must be a no-op the second time.
- **No cross-aggregate ordering.** Only per-aggregate order (by `version_no` / `occurred_at`) is
  guaranteed. A consumer that has already applied `version_no = 5` must ignore a late `version_no =
  3` for the same lesson (monotonic apply).
- **Poison messages** go to a dead-letter path after bounded retries and alert; they are never
  silently dropped (Engineering Constitution: no silent failures).
- **Replay-safe DR.** Because consumers dedupe and apply monotonically, a DR failover that
  redelivers a few in-flight events cannot double-apply (architecture §19).

---

## 7. Mapping to the write model (where each event is produced)

| Service operation | Local writes (one UoW) | Event enqueued |
| --- | --- | --- |
| `publish(lesson)` | insert `lesson_version`; update `lesson` (state, version, lock); insert `workflow_transition`, `audit_log` | `LessonPublished` |
| `rollback(lesson, target)` | insert new `lesson_version` from snapshot; update `lesson`; `workflow_transition`, `audit_log` | `LessonVersionRolledBack` |
| `archive(lesson)` | update `lesson.state='archived'`; `workflow_transition`, `audit_log` | `LessonArchived` |
| `add/update objective` | upsert `curriculum_objective` (+ `objective_prereq`); `audit_log` | `ObjectiveAdded`/`ObjectiveUpdated` |
| `approve media` | update `media_asset.scan_status='clean'`; `audit_log` | `MediaAssetApproved` |
| (inbound) item stats | upsert `item_statistics` | — (consumes `ItemStatisticsUpdated`) |

Draft/review-stage transitions (`submit`, `review`) are **local-only** — they produce
`workflow_transition` + `audit_log` rows but **no outbox event**, because drafts must never leak
past the authoring boundary (architecture §11). Only published facts are integration events.

---

## 8. Observability

- Every event carries `correlation_id`; the relay logs `event_id → broker offset` so an event can
  be traced end-to-end and reconciled against `audit_log` by `correlation_id`.
- Metrics: outbox backlog depth (`count WHERE published_at IS NULL`), relay lag (`now() -
  min(occurred_at) WHERE published_at IS NULL`), delivery-attempt histogram, dead-letter count.
  Backlog depth and lag are the two SLO alarms — a rising backlog means the relay is unhealthy
  before any consumer notices missing curriculum.
