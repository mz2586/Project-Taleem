"use client";
// Interactive authoring console: create draft, list, validate, and drive the review workflow.
// Client component (interactive state). Degrades gracefully when the API is unavailable.
import { useCallback, useEffect, useState } from "react";

import { Button } from "../../design-system/Button";
import { type LessonView, type ValidationResult, studioApi } from "../../lib/studio-api";

const REVIEW_ROLES = [
  "subject_expert",
  "instructional_designer",
  "a11y_specialist",
  "language_editor",
  "safety_officer",
];

export function StudioConsole() {
  const [lessons, setLessons] = useState<LessonView[]>([]);
  const [error, setError] = useState<string>("");
  const [validation, setValidation] = useState<Record<string, ValidationResult>>({});
  const [draftId, setDraftId] = useState("L-new");

  const refresh = useCallback(async () => {
    try {
      const { lessons: ls } = await studioApi.list();
      setLessons(ls);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "API unavailable");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const run = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await refresh();
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "error");
    }
  };

  const createDraft = () =>
    run(() =>
      studioApi.create({
        lesson_id: draftId,
        title_ur: "نئی درس",
        title_en: "New lesson",
        grade: "G1",
        subject: "math",
        learning_outcomes: ["MATH-G1-N-01"],
        provenance: { aligned_slo_codes: ["MATH-G1-N-01"] },
      }),
    );

  const validate = async (id: string) => {
    try {
      const result = await studioApi.validate(id);
      setValidation((v) => ({ ...v, [id]: result }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "error");
    }
  };

  return (
    <section>
      {error ? (
        <p style={{ color: "var(--color-danger)" }}>API: {error}</p>
      ) : null}

      <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center", margin: "var(--space-4) 0" }}>
        <input
          value={draftId}
          onChange={(e) => setDraftId(e.target.value)}
          aria-label="New lesson id"
          style={{ minHeight: "var(--size-touch-min)", padding: "var(--space-2)" }}
        />
        <Button variant="brand" label="Create draft" onClick={() => void createDraft()} />
        <Button variant="ghost" label="Refresh" onClick={() => void refresh()} />
      </div>

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {["Lesson", "Grade/Subject", "State", "Version", "Gates", "Actions"].map((h) => (
              <th key={h} style={{ textAlign: "start", borderBottom: "1px solid var(--color-border-default)" }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lessons.map((l) => (
            <tr key={l.lesson_id}>
              <td>{l.lesson_id}</td>
              <td>
                {l.grade}/{l.subject}
              </td>
              <td>
                <strong>{l.state}</strong>
              </td>
              <td>{l.version}</td>
              <td>
                {l.gates.filter((g) => g.passed).length}/9
              </td>
              <td style={{ display: "flex", gap: "var(--space-1)", flexWrap: "wrap" }}>
                <Button variant="ghost" label="Validate" onClick={() => void validate(l.lesson_id)} />
                {l.state === "draft" ? (
                  <Button
                    variant="primary"
                    label="Submit"
                    onClick={() => void run(() => studioApi.submit(l.lesson_id, "subject_author"))}
                  />
                ) : null}
                {REVIEW_ROLES.includes(l.state) ? (
                  <Button
                    variant="primary"
                    label={`Approve (${l.state})`}
                    onClick={() =>
                      void run(() => studioApi.review(l.lesson_id, "approve", l.state))
                    }
                  />
                ) : null}
                {l.state === "approved" ? (
                  <Button
                    variant="brand"
                    label="Publish"
                    onClick={() =>
                      void run(() => studioApi.publish(l.lesson_id, "curriculum_architect", "v"))
                    }
                  />
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {Object.entries(validation).map(([id, v]) => (
        <div key={id} style={{ marginTop: "var(--space-4)" }}>
          <strong>
            {id}: {v.ok ? "✓ valid" : "✗ findings"}
          </strong>
          <ul>
            {v.structural.map((f, i) => (
              <li key={i} style={{ color: "var(--color-danger)" }}>
                {f.field}: {f.message}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
