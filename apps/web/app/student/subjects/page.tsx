"use client";
// Learn — the child's path: Subjects → Units → Lessons with each state, the AI teacher's suggested
// next step, and a "Unit check" entry where the server says one is available
// (PROGRESSION_AND_EXAMINATION_CONTRACT §1). Read live: offline says so and points to the offline
// lessons already on this phone. View models: lib/progression/{wire,view}.ts.
import { useCallback, useEffect, useMemo, useState } from "react";

import { PathBrowser } from "@/components/progression/PathBrowser";
import { AppShell } from "@/components/student/AppShell";
import { LoadFailure } from "@/components/student/LoadFailure";
import { EmptyState, Skeleton } from "@/components/student/ui";
import { ButtonLink } from "@/design-system/ButtonLink";
import { useLocale } from "@/lib/i18n/useLocale";
import { pathApi } from "@/lib/progression/api";
import { browserSessionStore, readStoredSitting } from "@/lib/progression/sitting";
import { pathView, type PathView } from "@/lib/progression/wire";
import { useLearner } from "@/lib/session/useLearner";
import { classifyLoadError, INSTRUCTION_LOCALE_PREFERENCE, type LoadFailure as Failure } from "@/lib/student/journey";

export default function SubjectsPage() {
  const { studentRef: ref, band } = useLearner();
  const { t, locale, formatPercent } = useLocale();
  const [path, setPath] = useState<PathView | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | Failure>("loading");
  const [stored, setStored] = useState<ReadonlySet<string>>(new Set());

  const preference = useMemo(() => [locale, ...INSTRUCTION_LOCALE_PREFERENCE], [locale]);

  const load = useCallback(async () => {
    if (!ref) return;
    setStatus("loading");
    try {
      const view = pathView(await pathApi.path(ref), preference);
      setPath(view);
      // Sittings remembered on this phone (read after mount: storage does not exist on the server).
      const store = browserSessionStore();
      const keys = view.subjects.flatMap((s) => s.units.map((u) => u.key));
      setStored(new Set(keys.filter((k) => readStoredSitting(store, ref, k) !== null)));
      setStatus("ready");
    } catch (e) {
      setStatus(classifyLoadError(e));
    }
  }, [ref, preference]);

  useEffect(() => {
    void load();
  }, [load]);

  const ctx = useMemo(() => ({ t, locale, formatPercent }), [t, locale, formatPercent]);
  const empty = status === "ready" && (!path || path.subjects.every((s) => s.units.length === 0));

  return (
    <AppShell title={t("student.subjects.title")} band={band}>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {status === "loading" ? <Skeleton lines={5} label={t("progression.path.loading")} /> : null}
        {status !== "loading" && status !== "ready" ? (
          <LoadFailure
            failure={status}
            offlineTitle="progression.path.offlineTitle"
            offlineBody="progression.path.offlineBody"
            errorMessage="progression.path.error"
            onRetry={() => void load()}
          />
        ) : null}
        {empty ? (
          <EmptyState
            title={t("progression.path.emptyTitle")}
            body={t("progression.path.emptyBody")}
            action={<ButtonLink href="/student/today" variant="brand" label={t("common.goToToday")} />}
          />
        ) : null}
      </div>

      {status === "ready" && path && !empty ? <PathBrowser path={path} ctx={ctx} storedSittings={stored} /> : null}

      <section style={{ display: "grid", gap: "var(--space-2)", justifyItems: "center", textAlign: "center" }}>
        <ButtonLink href="/student/record" variant="ghost" label={t("progression.path.myRecord")} icon={<span aria-hidden="true">📒</span>} />
        <p style={{ margin: 0 }}>{t("student.offline.entryBody")}</p>
        <ButtonLink href="/student/offline" variant="ghost" label={t("student.offline.entry")} icon={<span aria-hidden="true">📥</span>} />
      </section>
    </AppShell>
  );
}
