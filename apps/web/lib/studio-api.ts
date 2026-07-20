// Typed client for the Curriculum Studio API (internal authoring tool).
// Mirrors packages/contracts/curriculum-studio.openapi.yaml.

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Gate {
  gate: string;
  passed: boolean;
  mode?: string;
}

export interface LessonView {
  lesson_id: string;
  title: Record<string, string>;
  grade: string;
  subject: string;
  state: string;
  version: number;
  learning_outcomes: string[];
  gates: Gate[];
}

export interface Finding {
  severity: string;
  message: string;
  field: string;
}

export interface ValidationResult {
  ok: boolean;
  structural: Finding[];
  gates: { gate: string; passed: boolean; findings: string[] }[];
}

export interface LessonDraftIn {
  lesson_id: string;
  title_ur: string;
  title_en: string;
  grade: string;
  subject: string;
  learning_outcomes: string[];
  provenance: { aligned_slo_codes: string[] };
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string; code?: string };
      detail = body.detail ?? body.code ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

export const studioApi = {
  hierarchy: () =>
    req<{ grades: string[]; subjects_by_grade: Record<string, string[]> }>("/v1/studio/hierarchy"),
  list: () => req<{ lessons: LessonView[] }>("/v1/studio/lessons"),
  create: (body: LessonDraftIn) =>
    req<LessonView>("/v1/studio/lessons", { method: "POST", body: JSON.stringify(body) }),
  validate: (id: string) =>
    req<ValidationResult>(`/v1/studio/lessons/${id}:validate`, { method: "POST" }),
  submit: (id: string, actor_role: string) =>
    req<LessonView>(`/v1/studio/lessons/${id}:submit`, {
      method: "POST",
      body: JSON.stringify({ actor_role }),
    }),
  review: (id: string, action: string, actor_role: string) =>
    req<LessonView>(`/v1/studio/lessons/${id}:review`, {
      method: "POST",
      body: JSON.stringify({ action, actor_role }),
    }),
  publish: (id: string, actor_role: string, change_summary: string) =>
    req<LessonView>(`/v1/studio/lessons/${id}:publish`, {
      method: "POST",
      body: JSON.stringify({ actor_role, change_summary }),
    }),
};
