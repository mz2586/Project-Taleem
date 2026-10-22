"use client";
// Draft editor: shown only to a subject author on a draft (the PDP's "author" right; the server also
// refuses edits outside the draft state). Each localized field is edited per lesson locale with its
// own lang/dir. Saving sends only what changed (lib/studio/edit.ts), guarded by If-Match: if
// someone else saved first, the server answers 412 and nothing is overwritten.
import { useId, useMemo, useState, type FormEvent } from "react";

import { FormError, FormNotice } from "@/components/form";
import { Button } from "@/design-system/Button";
import { directionOf } from "@/lib/i18n/config";
import { useLocale } from "@/lib/i18n/useLocale";
import { ApiError } from "@/lib/student/types";
import { PATCHABLE_LOCALIZED, studioApi, type LessonView } from "@/lib/studio-api";
import { buildPatch, editErrors, editableFields, type EditableFields } from "@/lib/studio/edit";

import { TextAreaField } from "./controls";

export function DraftEditor({
  lesson,
  locales,
  onSaved,
  onReload,
}: {
  lesson: LessonView;
  locales: string[];
  onSaved: (updated: LessonView) => void;
  onReload: () => void;
}) {
  const { t } = useLocale();
  const base = useId();
  const original = useMemo(() => editableFields(lesson), [lesson]);
  const [edited, setEdited] = useState<EditableFields>(original);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setNotice(null);
    setFailure(null);
    const problem = editErrors(edited);
    if (problem) return setFailure(t(problem));
    const patch = buildPatch(original, edited);
    if (!patch) return setNotice(t("studio.edit.noChanges"));
    if (!lesson.etag) return setStale(true); // no precondition to send: reload rather than guess
    setBusy(true);
    try {
      const updated = await studioApi.patch(lesson.lesson_id, patch, lesson.etag);
      setNotice(t("studio.edit.saved"));
      onSaved(updated);
    } catch (x) {
      if (x instanceof ApiError && (x.status === 412 || x.status === 409 || x.status === 428)) setStale(true);
      else setFailure(t("studio.actions.refused", { detail: x instanceof ApiError ? (x.problem.detail ?? x.message) : String(x) }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-labelledby={`${base}-h`} style={{ display: "grid", gap: "var(--space-3)", border: "1px solid var(--color-focus-ring)", borderRadius: "var(--radius-md)", padding: "var(--space-4)" }}>
      <h2 id={`${base}-h`} style={{ margin: 0 }}>
        {t("studio.edit.heading")}
      </h2>
      <p style={{ margin: 0 }}>{t("studio.edit.intro")}</p>
      <form onSubmit={(e) => void onSubmit(e)} noValidate style={{ display: "grid", gap: "var(--space-4)" }}>
        {PATCHABLE_LOCALIZED.map((field) => (
          <fieldset key={field} style={{ border: "none", padding: 0, margin: 0, display: "grid", gap: "var(--space-2)" }}>
            <legend style={{ fontWeight: 700 }}>{t(`studio.edit.fields.${field}`)}</legend>
            {locales.map((locale) => (
              <TextAreaField
                key={locale}
                id={`${base}-${field}-${locale}`}
                label={locale}
                lang={locale}
                dir={directionOf(locale)}
                rows={field === "title" ? 1 : 3}
                value={edited[field][locale] ?? ""}
                onChange={(ev) => {
                  const value = ev.target.value;
                  setEdited((cur) => ({ ...cur, [field]: { ...cur[field], [locale]: value } }));
                }}
              />
            ))}
          </fieldset>
        ))}
        <div aria-live="polite" style={{ display: "grid", gap: "var(--space-2)" }}>
          {notice ? <FormNotice message={notice} /> : null}
          {failure ? <FormError message={failure} /> : null}
          {stale ? (
            <>
              <FormError message={t("studio.edit.stale")} />
              <div>
                <Button variant="ghost" label={t("studio.edit.reload")} onClick={onReload} />
              </div>
            </>
          ) : null}
        </div>
        <div>
          <Button type="submit" variant="brand" label={t("studio.edit.save")} loading={busy} disabled={stale} />
        </div>
      </form>
    </section>
  );
}
