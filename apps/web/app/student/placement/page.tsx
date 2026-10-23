"use client";
// "Find your starting point" — the diagnostic placement for a learner with no history. The server
// chooses every question and decides when to stop; this screen asks, saves, and moves on. It never
// says right or wrong (it is not a test, and one answer is never a verdict). The rules live in
// lib/student/placement.ts, unit-tested.
import { useCallback, useEffect, useReducer, useState } from "react";

import { AppShell } from "@/components/student/AppShell";
import { ReadAloud } from "@/components/student/ReadAloud";
import { Card, EmptyState, ErrorBanner, Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { ButtonLink } from "@/design-system/ButtonLink";
import { contentAttrs } from "@/lib/i18n/content";
import { useLocale } from "@/lib/i18n/useLocale";
import { useLearner } from "@/lib/session/useLearner";
import { learningApi } from "@/lib/student/api";
import { classifyLoadError, type LoadFailure } from "@/lib/student/journey";
import {
  answerReducer,
  classifyAnswerError,
  initialAnswerState,
  PLACEMENT_FAILURE_COPY,
  PLACEMENT_SCREEN_COPY,
  placementScreen,
  type PlacementWire,
} from "@/lib/student/placement";

export default function PlacementPage() {
  const { studentRef: ref, band } = useLearner();
  const { t, locale } = useLocale();
  const [wire, setWire] = useState<PlacementWire | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | LoadFailure>("loading");
  const [answer, dispatch] = useReducer(answerReducer, initialAnswerState);
  const [answered, setAnswered] = useState(0);

  const load = useCallback(async () => {
    if (!ref) return;
    setStatus("loading");
    try {
      setWire(await learningApi.placement(ref));
      setStatus("ready");
    } catch (e) {
      setStatus(classifyLoadError(e));
    }
  }, [ref]);

  useEffect(() => {
    void load();
  }, [load]);

  const screen = wire ? placementScreen(wire, locale) : null;

  async function choose(itemRef: string, option: number) {
    if (!ref || answer.status === "saving") return;
    dispatch({ type: "submit", option });
    try {
      setWire(await learningApi.placementAnswer(ref, { item_ref: itemRef, option }));
      setAnswered((n) => n + 1);
      dispatch({ type: "saved" });
    } catch (e) {
      const kind = classifyAnswerError(e);
      if (kind === "reload") {
        dispatch({ type: "reset" });
        await load();
      } else {
        dispatch({ type: "failed", error: kind });
      }
    }
  }

  return (
    <AppShell title={t("student.placement.title")} band={band}>
      <p style={{ margin: 0 }}>{t("student.placement.intro")}</p>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {status === "loading" ? <Skeleton lines={3} label={t("student.placement.loading")} /> : null}
        {status !== "loading" && status !== "ready" ? (
          <ErrorBanner
            message={t(status === "offline" ? "student.placement.offline" : "student.placement.loadError")}
            action={<Button variant="ghost" label={t("student.placement.retry")} onClick={() => void load()} />}
          />
        ) : null}

        {status === "ready" && screen?.kind === "question" ? (
          <Card>
            <div style={{ display: "grid", gap: "var(--space-3)" }}>
              <p style={{ margin: 0 }}>
                {t("student.placement.questionOf", { current: screen.question.number, max: screen.question.max })}
              </p>
              {answered > 0 && answer.status === "idle" ? <p style={{ margin: 0 }}>{t("student.placement.thanks")}</p> : null}
              <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)", alignItems: "start" }}>
                <p
                  {...contentAttrs({ locale: screen.question.promptLocale, text: screen.question.prompt })}
                  style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}
                >
                  {screen.question.prompt}
                </p>
                <ReadAloud
                  label={t("student.placement.questionAudio")}
                  text={screen.question.prompt}
                  lang={screen.question.promptLocale ?? undefined}
                />
              </div>
              <div role="group" aria-label={t("student.placement.answersLabel")} style={{ display: "grid", gap: "var(--space-2)" }}>
                {screen.question.options.map((opt) => (
                  <Button
                    key={`${screen.question.itemRef}-${opt.index}`}
                    variant="primary"
                    label={opt.label}
                    {...contentAttrs({ text: opt.label })}
                    disabled={answer.status === "saving"}
                    loading={answer.status === "saving" && answer.option === opt.index}
                    onClick={() => void choose(screen.question.itemRef, opt.index)}
                  />
                ))}
              </div>
              {answer.status === "saving" ? <p style={{ margin: 0 }}>{t("student.placement.saving")}</p> : null}
              {answer.status === "failed" ? <ErrorBanner message={t(PLACEMENT_FAILURE_COPY[answer.error])} /> : null}
              <div>
                <ButtonLink href="/student/today" variant="ghost" label={t("student.placement.skip")} />
              </div>
            </div>
          </Card>
        ) : null}

        {status === "ready" && screen && screen.kind !== "question" ? (
          <EmptyState
            title={t(PLACEMENT_SCREEN_COPY[screen.kind].title)}
            body={t(PLACEMENT_SCREEN_COPY[screen.kind].body)}
            action={
              screen.kind === "done" ? (
                <ButtonLink href="/student/session" variant="brand" label={t("student.placement.start")} icon={<span aria-hidden="true">▶</span>} />
              ) : (
                <ButtonLink href="/student/today" variant="ghost" label={t("student.placement.back")} />
              )
            }
          />
        ) : null}
      </div>
    </AppShell>
  );
}
