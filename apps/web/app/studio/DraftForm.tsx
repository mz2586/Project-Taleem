"use client";
// New-draft form, shown only to subject authors (the only role the PDP lets author). It takes the
// fields the create API accepts today; validation rules are in lib/studio/draft.ts.
import { useEffect, useId, useState, type FormEvent } from "react";

import { FormError, FormNotice, TextField } from "@/components/form";
import { Button } from "@/design-system/Button";
import { useLocale } from "@/lib/i18n/useLocale";
import { ApiError } from "@/lib/student/types";
import { studioApi, type CurriculumPackSummary } from "@/lib/studio-api";
import { EMPTY_DRAFT, draftErrors, packLocales, toDraftIn, type DraftErrors, type DraftForm as Form } from "@/lib/studio/draft";

import { SelectField, TextAreaField } from "./controls";

type Hierarchy = { grades: string[]; subjects_by_grade: Record<string, string[]> };

export function DraftForm({ packs, onCreated }: { packs: CurriculumPackSummary[]; onCreated: () => void }) {
  const { t } = useLocale();
  const base = useId();
  const [form, setForm] = useState<Form>(EMPTY_DRAFT);
  const [errors, setErrors] = useState<DraftErrors>({});
  const [hierarchy, setHierarchy] = useState<Hierarchy | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    studioApi
      .hierarchy(form.pack || undefined)
      .then((h) => alive && setHierarchy(h))
      .catch(() => alive && setHierarchy(null));
    return () => {
      alive = false;
    };
  }, [form.pack]);

  const set = (key: Exclude<keyof Form, "titles">, value: string) => setForm((f) => ({ ...f, [key]: value }));
  const err = (key: keyof DraftErrors) => (errors[key] ? t(errors[key]!) : undefined);
  const locales = packLocales(packs.find((p) => p.pack_id === form.pack));

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setNotice(null);
    setFailure(null);
    const found = draftErrors(form, hierarchy, locales.map((l) => l.tag));
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    try {
      const created = await studioApi.create(toDraftIn(form));
      setNotice(t("studio.draft.created", { id: created.lesson_id }));
      setForm(EMPTY_DRAFT);
      onCreated();
    } catch (x) {
      const detail = x instanceof ApiError ? (x.problem.detail ?? x.message) : String(x);
      setFailure(t("studio.actions.refused", { detail }));
    } finally {
      setBusy(false);
    }
  };

  const grades = hierarchy?.grades ?? [];
  const subjects = form.grade ? (hierarchy?.subjects_by_grade[form.grade] ?? []) : [];

  return (
    <section aria-labelledby={`${base}-h`} style={{ display: "grid", gap: "var(--space-3)", maxWidth: 640 }}>
      <h2 id={`${base}-h`} style={{ margin: 0 }}>
        {t("studio.draft.heading")}
      </h2>
      <p style={{ margin: 0 }}>{t("studio.draft.localesNote")}</p>
      <p style={{ margin: 0 }}>{t("studio.draft.editHint")}</p>
      <form onSubmit={(e) => void onSubmit(e)} noValidate style={{ display: "grid", gap: "var(--space-3)" }}>
        <TextField id={`${base}-id`} label={t("studio.draft.lessonId")} value={form.lessonId} onChange={(e) => set("lessonId", e.target.value)} dir="ltr" error={err("lessonId")} />
        <SelectField id={`${base}-pack`} label={t("studio.draft.pack")} value={form.pack} onChange={(e) => setForm((f) => ({ ...f, pack: e.target.value, grade: "", subject: "", titles: {} }))}>
          <option value="">{t("studio.draft.choose")}</option>
          {packs.map((p) => (
            <option key={p.pack_id} value={p.pack_id}>
              {p.pack_id} · {p.education_system}
            </option>
          ))}
        </SelectField>
        <fieldset style={{ border: "1px solid var(--color-focus-ring)", borderRadius: "var(--radius-md)", display: "grid", gap: "var(--space-2)", padding: "var(--space-3)" }}>
          <legend>{t("studio.draft.titles")}</legend>
          {locales.length === 0 ? <p style={{ margin: 0 }}>{t("studio.draft.choosePackFirst")}</p> : null}
          {locales.map((l) => (
            <TextField
              key={l.tag}
              id={`${base}-title-${l.tag}`}
              label={t("studio.draft.title", { locale: `${l.name} · ${l.tag}` })}
              value={form.titles[l.tag] ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, titles: { ...f.titles, [l.tag]: e.target.value } }))}
              lang={l.tag}
              dir={l.direction}
            />
          ))}
          {errors.titles ? (
            <span role="alert" style={{ color: "var(--color-danger)" }}>
              {err("titles")}
            </span>
          ) : null}
        </fieldset>
        <SelectField id={`${base}-grade`} label={t("studio.draft.grade")} value={form.grade} onChange={(e) => setForm((f) => ({ ...f, grade: e.target.value, subject: "" }))} error={err("grade")}>
          <option value="">{t("studio.draft.choose")}</option>
          {grades.map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </SelectField>
        <SelectField id={`${base}-subject`} label={t("studio.draft.subject")} value={form.subject} onChange={(e) => set("subject", e.target.value)} error={err("subject")}>
          <option value="">{t("studio.draft.choose")}</option>
          {subjects.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </SelectField>
        <TextAreaField
          id={`${base}-outcomes`}
          label={t("studio.draft.outcomes")}
          hint={t("studio.draft.outcomesHint")}
          value={form.outcomes}
          onChange={(e) => set("outcomes", e.target.value)}
          dir="ltr"
          error={err("outcomes")}
        />
        <div aria-live="polite">
          {notice ? <FormNotice message={notice} /> : null}
          {failure ? <FormError message={failure} /> : null}
        </div>
        <div>
          <Button type="submit" variant="brand" label={t("studio.draft.create")} loading={busy} />
        </div>
      </form>
    </section>
  );
}
