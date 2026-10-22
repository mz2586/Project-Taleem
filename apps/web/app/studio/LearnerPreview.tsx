"use client";
// The learner's view of a lesson, for reviewers. It is driven by the student lesson-player reducer
// (lib/student/lessonPlayer.ts, used read-only) over `learnerPreview(...)`, and drawn with the
// student Card / ReadAloud components, so the paced steps are the ones a child will page through.
// Reviewers see each item's whole authored hint ladder at once, because judging the ladder means
// reading every rung. Nothing is submitted: no session and no evidence are recorded.
import { useEffect, useId, useMemo, useReducer, useState } from "react";

import { ReadAloud } from "@/components/student/ReadAloud";
import { Card } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { contentAttrs } from "@/lib/i18n/content";
import { useLocale } from "@/lib/i18n/useLocale";
import { initialPlayerState, isLastStep, playerReducer, presentationSteps } from "@/lib/student/lessonPlayer";
import type { LessonView } from "@/lib/studio-api";
import { hasContent, itemHints, learnerPreview } from "@/lib/studio/preview";

import { SelectField } from "./controls";

export function LearnerPreview({ lesson, locales }: { lesson: LessonView; locales: string[] }) {
  const { t } = useLocale();
  const selectId = useId();
  const [locale, setLocale] = useState(locales[0] ?? "");
  const teach = useMemo(() => learnerPreview(lesson, locale), [lesson, locale]);
  const [state, dispatch] = useReducer(playerReducer, initialPlayerState);
  const [itemIndex, setItemIndex] = useState(0);

  useEffect(() => {
    dispatch({ type: "taught", objective: lesson.lesson_id, teach });
    setItemIndex(0);
  }, [lesson.lesson_id, teach]);

  if (!hasContent(lesson)) return <p style={{ margin: 0 }}>{t("studio.lesson.previewUnavailable")}</p>;

  const steps = presentationSteps(state);
  const step = steps[state.step];
  const attrs = contentAttrs({ locale });
  const item = teach.items[itemIndex];
  const hints = item ? itemHints(lesson, item.item_ref, locale) : [];

  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }}>
      <SelectField id={selectId} label={t("studio.lesson.previewLocale")} value={locale} onChange={(e) => setLocale(e.target.value)}>
        {locales.map((l) => (
          <option key={l} value={l}>
            {l}
          </option>
        ))}
      </SelectField>

      {step ? (
        <section aria-live="polite" style={{ display: "grid", gap: "var(--space-2)" }}>
          <p style={{ margin: 0 }}>{t("student.session.stepOf", { current: state.step + 1, total: steps.length })}</p>
          <Card>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)", alignItems: "start" }}>
              <p {...attrs} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
                {step.text}
              </p>
              <ReadAloud label={t("student.session.teacherAudio")} text={step.text} lang={locale} />
            </div>
          </Card>
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <Button variant="ghost" label={t("common.back")} disabled={state.step === 0} onClick={() => dispatch({ type: "previousStep" })} />
            <Button variant="ghost" label={t("common.next")} disabled={isLastStep(state)} onClick={() => dispatch({ type: "nextStep" })} />
          </div>
        </section>
      ) : null}

      {item ? (
        <section style={{ display: "grid", gap: "var(--space-2)" }}>
          <p style={{ margin: 0 }}>{t("studio.lesson.previewQuestion", { current: itemIndex + 1, total: teach.items.length })}</p>
          <Card>
            <div style={{ display: "grid", gap: "var(--space-2)" }}>
              <p {...attrs} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
                {item.prompt[locale]}
              </p>
              <ul {...attrs} style={{ margin: 0, display: "grid", gap: "var(--space-1)" }}>
                {item.options.map((o, i) => (
                  <li key={i}>{o}</li>
                ))}
              </ul>
              {hints.length > 0 ? (
                <>
                  <strong>{t("studio.lesson.previewHints")}</strong>
                  <ol {...attrs} style={{ margin: 0, display: "grid", gap: "var(--space-1)" }}>
                    {hints.map((h, i) => (
                      <li key={i}>{h}</li>
                    ))}
                  </ol>
                </>
              ) : null}
            </div>
          </Card>
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <Button variant="ghost" label={t("studio.lesson.previewPrev")} disabled={itemIndex === 0} onClick={() => setItemIndex((i) => i - 1)} />
            <Button
              variant="ghost"
              label={t("studio.lesson.previewNext")}
              disabled={itemIndex >= teach.items.length - 1}
              onClick={() => setItemIndex((i) => i + 1)}
            />
          </div>
        </section>
      ) : (
        <p style={{ margin: 0 }}>{t("studio.lesson.previewNoItems")}</p>
      )}
    </div>
  );
}
