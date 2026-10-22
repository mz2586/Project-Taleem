// Typed client for the Curriculum Studio API (internal authoring and review tool).
// Mirrors packages/contracts/curriculum-studio.openapi.yaml.
//
// Every call carries the staff member's bearer token (lib/studio/session.ts). The actor's role and
// identity come from that verified token server-side — never from a request body. The old client
// sent `actor_role` in bodies, which the server ignored; that misleading field is gone.
//
// Fields marked "not in the contract yet" mirror the domain's `Lesson.to_dict()` names. The current
// API does not return them; they are optional so the UI shows "not provided by the API" honestly
// today and lights up unchanged when the backend exposes them (see the API gaps in the commit).

import { ApiError } from "./student/types";
import { API_BASE } from "./session/config";
import { studioSession } from "./studio/session";

export interface GateView {
  gate: string;
  passed: boolean;
  mode?: "auto" | "human" | string;
  /** Not in the contract yet: the reviewer role the domain records on a human gate. */
  reviewer_role?: string;
}

/** A localized field as the domain serialises it: `{ text: {locale: string}, audio_ref: {...} }`. */
export interface LocalizedTextView {
  text: Record<string, string>;
  audio_ref?: Record<string, string>;
}

export interface HintView {
  trigger?: string;
  hint: LocalizedTextView;
}

export interface AssessmentItemView {
  item_id: string;
  type?: string;
  objective_ref?: string;
  stem: LocalizedTextView;
  options?: LocalizedTextView[];
  hints?: HintView[];
  explanation?: LocalizedTextView;
}

export interface WorkedExampleView {
  prompt: LocalizedTextView;
  steps?: LocalizedTextView[];
}

export interface ProvenanceView {
  derivation: string;
  source: string;
  license: string;
  aligned_slo_codes?: string[];
  permission_ref?: string | null;
}

export interface TransitionView {
  from_state: string;
  to_state: string;
  action: string;
  actor_role: string;
  at: number;
  note?: string;
}

export interface LessonView {
  lesson_id: string;
  title: Record<string, string>;
  grade: string;
  subject: string;
  curriculum_pack?: string;
  instructional_locales?: string[];
  state: string;
  version: number;
  learning_outcomes: string[];
  gates: GateView[];
  // ---- not in the contract yet (domain `Lesson.to_dict()` names) ----
  metadata?: { tags?: string[]; author_role?: string; languages?: string[] };
  provenance?: ProvenanceView;
  student_explanation?: LocalizedTextView;
  worked_examples?: WorkedExampleView[];
  practice_questions?: AssessmentItemView[];
  hints?: HintView[];
  workflow?: { state: string; history: TransitionView[] };
}

export interface Finding {
  severity: "blocker" | "major" | "minor" | string;
  message: string;
  field: string;
}

export interface ValidationResult {
  ok: boolean;
  structural: Finding[];
  gates: { gate: string; passed: boolean; findings: string[] }[];
}

export interface VersionView {
  version: number;
  content_hash: string;
  change_summary: string;
  author_role: string;
}

export interface PackLocale {
  tag: string;
  name: string;
  direction: "ltr" | "rtl";
}

export interface CurriculumPackSummary {
  pack_id: string;
  version: string;
  country: string;
  education_system: string;
  language_of_instruction: string;
  instructional_locales: string[];
  locales: PackLocale[];
}

export interface LessonDraftIn {
  lesson_id: string;
  // The create contract still takes exactly these two locales (locale-generic draft fields are a
  // pending backend change).
  title_ur: string;
  title_en: string;
  grade: string;
  subject: string;
  curriculum_pack?: string;
  instructional_locales?: string[];
  learning_outcomes: string[];
  provenance?: { aligned_slo_codes: string[] };
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const token = studioSession.token();
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "content-type": "application/json",
        ...(token ? { authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(0, { code: "OFFLINE", detail: "network unavailable" });
  }
  if (!res.ok) {
    let problem: Record<string, unknown> = { code: res.statusText };
    try {
      problem = (await res.json()) as Record<string, unknown>;
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401) studioSession.clear(); // expired or revoked: sign in again
    throw new ApiError(res.status, { ...problem, status: res.status });
  }
  return (await res.json()) as T;
}

const post = <T>(path: string, body: unknown = {}): Promise<T> =>
  req<T>(path, { method: "POST", body: JSON.stringify(body) });

export const studioApi = {
  packs: () => req<{ packs: CurriculumPackSummary[] }>("/v1/studio/curriculum-packs"),
  hierarchy: (pack?: string) =>
    req<{ system: string; grades: string[]; subjects_by_grade: Record<string, string[]> }>(
      `/v1/studio/hierarchy${pack ? `?pack=${encodeURIComponent(pack)}` : ""}`,
    ),
  list: () => req<{ lessons: LessonView[] }>("/v1/studio/lessons"),
  get: (id: string) => req<LessonView>(`/v1/studio/lessons/${encodeURIComponent(id)}`),
  versions: (id: string) => req<{ versions: VersionView[] }>(`/v1/studio/lessons/${encodeURIComponent(id)}/versions`),
  create: (body: LessonDraftIn) => post<LessonView>("/v1/studio/lessons", body),
  validate: (id: string) => post<ValidationResult>(`/v1/studio/lessons/${encodeURIComponent(id)}:validate`),
  submit: (id: string, note: string) => post<LessonView>(`/v1/studio/lessons/${encodeURIComponent(id)}:submit`, { note }),
  review: (id: string, action: "approve" | "request_changes", note: string) =>
    post<LessonView>(`/v1/studio/lessons/${encodeURIComponent(id)}:review`, { action, note }),
  publish: (id: string, changeSummary: string) =>
    post<LessonView>(`/v1/studio/lessons/${encodeURIComponent(id)}:publish`, { change_summary: changeSummary }),
  rollback: (id: string, targetVersion: number, note: string) =>
    post<LessonView>(`/v1/studio/lessons/${encodeURIComponent(id)}:rollback`, {
      target_version: targetVersion,
      note,
    }),
};
