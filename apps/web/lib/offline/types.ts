// Offline-lite types (Phase 6.2A). Mirrors the backend offline package contract
// (packages/contracts/offline.openapi.yaml) and the local IndexedDB stores
// (OFFLINE_STORAGE_SPEC.md). No child PII: only the pseudonymous student_ref.

export interface PackageAsset {
  ref: string;
  kind: string;
  sha256: string;
  bytes: number;
}

export interface PackageManifest {
  package_id: string;
  lesson_id: string;
  objective_code: string;
  version: string; // short content_hash prefix — changes iff content changes
  content_hash: string; // SHA-256 hex over the canonical offline content
  assets: PackageAsset[];
  total_bytes: number;
  created_at_ms: number;
  // Phase 6.2C-1 (optional — empty/absent = unsigned, backward-compatible with 6.2A/6.2B).
  signature?: string; // hex Ed25519 signature over `${package_id}\n${version}\n${content_hash}`
  signing_key_id?: string;
}

export interface SigningKey {
  key_id: string;
  algorithm: string; // "Ed25519"
  public_key_hex: string;
}

export interface OfflineItem {
  item_ref: string;
  objective_code: string;
  prompt: Record<string, string>; // locale -> text
  options: string[];
  hints: string[];
  // NOTE: no correct_option / option_misconceptions — answer keys never reach the device (6.2A).
}

export interface OfflineContent {
  lesson_id: string;
  objective_code: string;
  title: Record<string, string>;
  explanation: Record<string, string>;
  worked_example_steps: string[];
  practice_items: OfflineItem[];
  homework_items: OfflineItem[];
  assessment_formative: OfflineItem[];
  summative_mentor_mediated: boolean;
}

export interface OfflinePackage {
  manifest: PackageManifest;
  content: OfflineContent;
}

// Local IndexedDB record for an installed package.
export type InstallState = "downloading" | "ready" | "superseded";

export interface StoredPackage {
  package_id: string;
  lesson_id: string;
  content_hash: string;
  version: string;
  state: InstallState;
  total_bytes: number;
  installed_at: number;
  last_used_at: number;
  signature_ok?: boolean; // Phase 6.2C-1: whether the manifest signature verified at install
}

// A locally-recorded learning event (offline-lite: persisted locally; NOT synced in 6.2A).
export type ProgressEventKind = "lesson_opened" | "item_attempted" | "lesson_completed";

export interface LocalProgressEvent {
  client_event_id: string; // uuid7 — stable id (reused as the sync idempotency key in 6.2B)
  student_ref: string;
  lesson_id: string;
  objective_code: string;
  kind: ProgressEventKind;
  item_ref?: string;
  selected_option?: number; // the child's choice (NOT graded on device)
  created_at: number;
}

// A resumable session checkpoint (client-side durability; server sessions are in-memory).
export interface SessionCheckpoint {
  session_id: string; // uuid7 (client-generated offline)
  student_ref: string;
  lesson_id: string;
  objective_code: string;
  item_index: number; // position within the lesson's items
  completed_item_refs: string[];
  updated_at: number;
}

export interface StorageEstimate {
  usage: number;
  quota: number;
}

// ---------------------------------------------------------------- sync engine (Phase 6.2B)

// Mirrors the backend DeltaType (contexts/sync/domain.py) and the sync.batch contract.
export type DeltaType =
  | "progress.updated"
  | "lesson.completed"
  | "attempt.submitted"
  | "preference.set";

export type SyncStatus = "applied" | "duplicate" | "ignored" | "conflict";

// An offline attempt payload (graded server-side on sync; NO answer key on the device).
export interface AttemptPayload {
  student_ref: string;
  objective_code: string;
  item_ref: string;
  option: number;
  evidence_id: string; // client uuid7 — the durable idempotency key
  session_id?: string;
  hints_used?: number;
  response_time_ms?: number;
  self_confidence?: number | null;
  context?: string;
}

export interface SyncDelta {
  clientEventId: string; // uuid7 idempotency key
  type: DeltaType;
  entityKey: string;
  payload: Record<string, unknown>;
  clientSeq: number; // Lamport seq (never wall-clock)
}

export type QueueState = "pending" | "sending" | "failed" | "dead";

export interface QueuedDelta extends SyncDelta {
  syncState: QueueState;
  attempts: number;
  createdAt: number;
  lastError?: string;
}

export interface ItemResult {
  clientEventId: string;
  status: SyncStatus;
  version: number;
}

export interface BatchResult {
  cursor: number;
  results: ItemResult[];
  // Phase 6.2C-1 (optional, backward-compatible): student_refs the server asks the client to purge
  // (de-enrolment / consent withdrawal). Absent when the server does not send it.
  purge?: string[];
}

export interface SyncDiagnostics {
  queued: number;
  applied: number;
  duplicate: number;
  ignored: number;
  conflict: number;
  failed: number;
  deadLettered: number;
  drains: number;
  lastSyncAt: number | null;
  lastError: string | null;
  // Phase 6.2C-1 hardening counters (all local; C1-only; no student_ref, no content, no PII).
  signatureFailures: number;
  integrityFailures: number;
  evictions: number;
  evictedBytes: number;
  purges: number;
}

export interface DrainSummary {
  sent: number;
  applied: number;
  duplicate: number;
  ignored: number;
  conflict: number;
  remaining: number;
  cursor: number;
}
