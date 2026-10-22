"use client";
// New-draft form, shown only to subject authors (the only role the PDP lets author). It takes the
// fields the create API accepts today; validation rules are in lib/studio/draft.ts.
import { useEffect, useId, useState, type FormEvent } from "react";

import { FormError, FormNotice, TextField } from "@/components/form";
import { Button } from "@/design-system/Button";
import { useLocale } from "@/lib/i18n/useLocale";
import { ApiError } from "@/lib/student/types";
import { studioApi, type CurriculumPackSummary } from "@/lib/studio-api";
import { EMPTY_DRAFT, draftErrors, toDraftIn, type DraftErrors, type DraftForm as Form } from "@/lib/studio/draft";

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

  const set = (key: keyof Form, value: string) => setForm((f) => ({ ...f, [key]: value }));
  const err = (key: keyof Form) => (errors[key] ? t(errors[key]!) : undefined);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setNotice(null);
    setFailure(null);
    const found = draftErrors(form, hierarchy);
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
      <p style={{ margin: 0 }}>{t("studio.draft.editUnavailable")}</p>
      <form onSubmit={(e) => void onSubmit(e)} noValidate style={{ display: "grid", gap: "var(--space-3)" }}>
        <TextField id={`${base}-id`} label={t("studio.draft.lessonId")} value={form.lessonId} onChange={(e) => set("lessonId", e.target.value)} dir="ltr" error={err("lessonId")} />
        <TextField id={`${base}-ur`} label={t("studio.draft.titleUr")} value={form.titleUr} onChange={(e) => set("titleUr", e.target.value)} lang="ur" dir="rtl" error={err("titleUr")} />
        <TextField id={`${base}-en`} label={t("studio.draft.titleEn")} value={form.titleEn} onChange={(e) => set("titleEn", e.target.value)} lang="en" dir="ltr" error={err("titleEn")} />
        <SelectField id={`${base}-pack`} label={t("studio.draft.pack")} value={form.pack} onChange={(e) => setForm((f) => ({ ...f, pack: e.target.value, grade: "", subject: "" }))}>
          <option value="">{t("studio.draft.choose")}</option>
          {packs.map((p) => (
            <option key={p.pack_id} value={p.pack_id}>
              {p.pack_id} · {p.education_system}
            </option>
          ))}
        </SelectField>
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
