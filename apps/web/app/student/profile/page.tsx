"use client";
// Profile — the learner's own view: mastery map (state via label+shape, never colour-only), a
// plain-language summary, and the app-language choice for this device. IDOR-guarded server-side: a
// learner sees only their own data.
import { useCallback, useEffect, useId, useState } from "react";

import { AppShell } from "@/components/student/AppShell";
import { LoadFailure } from "@/components/student/LoadFailure";
import { Card, EmptyState, Skeleton, StateBadge } from "@/components/student/ui";
import { LOCALE_META, SUPPORTED_LOCALES, isSupportedLocale } from "@/lib/i18n/config";
import { useLocale } from "@/lib/i18n/useLocale";
import { useLearner } from "@/lib/session/useLearner";
import { learningApi } from "@/lib/student/api";
import {
  classifyLoadError,
  emptyKnowledge,
  gradeLabel,
  masteryStateKey,
  orOnNotFound,
  type LoadFailure as Failure,
} from "@/lib/student/journey";
import type { KnowledgeView } from "@/lib/student/types";

export default function ProfilePage() {
  const { studentRef: ref, band, displayName, learner } = useLearner();
  const { t, locale, setLocale } = useLocale();
  const languageId = useId();
  const [knowledge, setKnowledge] = useState<KnowledgeView | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | Failure>("loading");

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      // A brand-new learner has no knowledge record yet (404): an empty map, not an error.
      setKnowledge(await orOnNotFound(learningApi.knowledge(ref), emptyKnowledge(ref)));
      setStatus("ready");
    } catch (e) {
      setStatus(classifyLoadError(e));
    }
  }, [ref]);

  useEffect(() => {
    void load();
  }, [load]);

  const objectives = knowledge ? Object.entries(knowledge.objectives) : [];
  const mastered = objectives.filter(([, o]) => o.state === "mastered").length;
  const grade = gradeLabel(learner?.grade_level);

  return (
    <AppShell title={t("student.profile.title")} band={band}>
      <section style={{ display: "grid", gap: "var(--space-1)" }}>
        <h2 style={{ margin: 0 }} dir="auto">
          {displayName}
        </h2>
        {grade ? <span>{t(grade.key, grade.params)}</span> : null}
      </section>

      <section style={{ display: "grid", gap: "var(--space-1)", justifyItems: "start" }}>
        <label htmlFor={languageId}>{t("common.interfaceLanguage")}</label>
        <select
          id={languageId}
          value={locale}
          onChange={(e) => {
            const next = e.target.value;
            if (isSupportedLocale(next)) setLocale(next);
          }}
          style={{
            minHeight: "var(--size-touch-min)",
            minWidth: "var(--size-touch-min)",
            padding: "var(--space-2) var(--space-3)",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--color-focus-ring)",
            background: "var(--color-bg-canvas)",
            color: "var(--color-text-primary)",
            font: "inherit",
          }}
        >
          {SUPPORTED_LOCALES.map((code) => (
            // Each language is named in itself, so a child who cannot read the current one can still
            // find their own.
            <option key={code} value={code} lang={code} dir={LOCALE_META[code].dir}>
              {LOCALE_META[code].nativeName}
            </option>
          ))}
        </select>
      </section>

      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {status === "loading" ? <Skeleton lines={5} label={t("common.loading")} /> : null}
        {status !== "loading" && status !== "ready" ? (
          <LoadFailure
            failure={status}
            offlineTitle="student.profile.offlineTitle"
            offlineBody="student.profile.offlineBody"
            errorMessage="student.profile.error"
            onRetry={() => void load()}
          />
        ) : null}

        {status === "ready" ? (
          objectives.length === 0 ? (
            <EmptyState title={t("student.profile.mapEmptyTitle")} body={t("student.profile.mapEmptyBody")} />
          ) : (
            <>
              <p style={{ margin: 0 }}>{t("student.profile.summary", { mastered, total: objectives.length })}</p>
              <section aria-label={t("student.profile.mapLabel")} style={{ display: "grid", gap: "var(--space-2)" }}>
                {objectives.map(([code, o]) => (
                  <Card key={code}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)" }}>
                      <span dir="auto">{code}</span>
                      <StateBadge state={o.state} label={t(masteryStateKey(o.state))} />
                    </div>
                  </Card>
                ))}
              </section>
            </>
          )
        ) : null}
      </div>
    </AppShell>
  );
}
