"use client";
// The stage actions the signed-in role may take on this lesson, and nothing else
// (`availableActions`). Each human decision is an explicit form: a written reason, then a confirm
// button pressed by the reviewer. Nothing here runs on load or approves by default.
import { useId, useState, type FormEvent } from "react";

import { FormError, FormNotice } from "@/components/form";
import { Button } from "@/design-system/Button";
import { useLocale } from "@/lib/i18n/useLocale";
import { ApiError } from "@/lib/student/types";
import { studioApi, type LessonView, type ValidationResult, type VersionView } from "@/lib/studio-api";
import type { StudioActor } from "@/lib/studio/session";
import {
  STAGE_GATES,
  availableActions,
  gateLabelKey,
  isReviewStage,
  noteError,
  type ActionOption,
} from "@/lib/studio/workflow";

import { SelectField, TextAreaField } from "./controls";

function ActionForm({
  option,
  lesson,
  versions,
  onDone,
}: {
  option: ActionOption;
  lesson: LessonView;
  versions: VersionView[];
  onDone: (updated: LessonView) => void;
}) {
  const { t } = useLocale();
  const id = useId();
  const [note, setNote] = useState("");
  const [target, setTarget] = useState<number | null>(versions[0]?.version ?? null);
  const [error, setError] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const label = t(`studio.actions.${option.action}`);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setFailure(null);
    const problem = noteError(option, note);
    setError(problem ? t(problem) : null);
    if (problem || !option.enabled) return;
    setBusy(true);
    try {
      const id_ = lesson.lesson_id;
      let updated: LessonView;
      switch (option.action) {
        case "submit":
          updated = await studioApi.submit(id_, note.trim());
          break;
        case "approve":
        case "request_changes":
          updated = await studioApi.review(id_, option.action, note.trim());
          break;
        case "publish":
          updated = await studioApi.publish(id_, note.trim());
          break;
        case "rollback":
          if (target === null) return;
          updated = await studioApi.rollback(id_, target, note.trim());
          break;
      }
      setNote("");
      onDone(updated);
    } catch (x) {
      if (x instanceof ApiError && x.status === 409) setFailure(t("studio.actions.conflict"));
      else setFailure(t("studio.actions.refused", { detail: x instanceof ApiError ? (x.problem.detail ?? x.message) : String(x) }));
    } finally {
      setBusy(false);
    }
  };

  const gateName = (g: string) => {
    const key = gateLabelKey(g);
    return key ? t(key) : g;
  };
  const stageGates = option.action === "approve" && isReviewStage(lesson.state) ? STAGE_GATES[lesson.state] : [];

  return (
    <form onSubmit={(e) => void onSubmit(e)} noValidate style={{ display: "grid", gap: "var(--space-2)", borderTop: "1px solid var(--color-focus-ring)", paddingTop: "var(--space-3)" }}>
      <strong>{label}</strong>
      {stageGates.length > 0 ? (
        <p style={{ margin: 0 }}>{t("studio.actions.certifies", { gates: stageGates.map((g) => gateName(g)).join(", ") })}</p>
      ) : null}
      {option.reason ? <p style={{ margin: 0 }}>{t(option.reason)}</p> : null}
      {option.blockingGates && option.blockingGates.length > 0 ? (
        <p style={{ margin: 0, color: "var(--color-danger)" }}>
          {t("studio.actions.blocking", { gates: option.blockingGates.map((g) => gateName(g)).join(", ") })}
        </p>
      ) : null}
      {option.action === "rollback" ? (
        <SelectField id={`${id}-target`} label={t("studio.actions.targetVersion")} value={target ?? ""} onChange={(e) => setTarget(Number(e.target.value))}>
          {versions.map((v) => (
            <option key={v.version} value={v.version}>
              v{v.version}
            </option>
          ))}
        </SelectField>
      ) : null}
      <TextAreaField
        id={`${id}-note`}
        label={option.requiresNote ? t("studio.actions.note") : t("studio.actions.noteOptional")}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        error={error ?? undefined}
        disabled={!option.enabled}
      />
      <div aria-live="polite">{failure ? <FormError message={failure} /> : null}</div>
      <div>
        <Button
          type="submit"
          variant={option.action === "request_changes" ? "ghost" : "brand"}
          label={label}
          disabled={!option.enabled || (option.action === "rollback" && versions.length === 0)}
          loading={busy}
        />
      </div>
    </form>
  );
}

export function ActionPanel({
  lesson,
  actor,
  validation,
  versions,
  onChanged,
}: {
  lesson: LessonView;
  actor: StudioActor;
  validation: ValidationResult | null;
  versions: VersionView[];
  onChanged: (updated: LessonView) => void;
}) {
  const { t } = useLocale();
  const [done, setDone] = useState(false);
  const options = availableActions(lesson, actor, validation);
  return (
    <section aria-labelledby="studio-actions-h" style={{ display: "grid", gap: "var(--space-3)", border: "1px solid var(--color-focus-ring)", borderRadius: "var(--radius-md)", padding: "var(--space-4)" }}>
      <h2 id="studio-actions-h" style={{ margin: 0 }}>
        {t("studio.actions.heading")}
      </h2>
      <p style={{ margin: 0 }}>{t("studio.actions.actingAs", { subject: actor.subject, role: t(`studio.roles.${actor.role}`) })}</p>
      <div aria-live="polite">{done ? <FormNotice message={t("studio.actions.done")} /> : null}</div>
      {options.length === 0 ? <p style={{ margin: 0 }}>{t("studio.actions.none")}</p> : null}
      {options.map((o) => (
        <ActionForm
          key={`${lesson.state}-${o.action}`}
          option={o}
          lesson={lesson}
          versions={versions}
          onDone={(u) => {
            setDone(true);
            onChanged(u);
          }}
        />
      ))}
    </section>
  );
}
