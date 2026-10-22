"use client";
// Curriculum Studio home: the review queue by workflow stage, with filters, landing on the stage the
// signed-in role works in. Authors also get the new-draft form. The rules are in lib/studio/*.
import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useState } from "react";

import { Button } from "@/design-system/Button";
import { useLocale } from "@/lib/i18n/useLocale";
import { classifyLoadError } from "@/lib/student/journey";
import { ApiError } from "@/lib/student/types";
import { studioApi, type CurriculumPackSummary, type LessonView } from "@/lib/studio-api";
import {
  DEFAULT_FILTERS,
  QUEUE_STAGES,
  facets,
  filterQueue,
  gateSummary,
  homeStage,
  isProvisional,
  stageCounts,
  type QueueFilters,
  type QueueStage,
} from "@/lib/studio/workflow";

import { ProvisionalBadge, SelectField } from "./controls";
import { DraftForm } from "./DraftForm";
import { useActor } from "./StudioShell";

type Load = "loading" | "ready" | "offline" | "forbidden" | "error";

export default function StudioQueuePage() {
  const actor = useActor();
  const { t } = useLocale();
  const ids = { subject: useId(), pack: useId(), provisional: useId(), gates: useId(), search: useId() };
  const [lessons, setLessons] = useState<LessonView[]>([]);
  const [packs, setPacks] = useState<CurriculumPackSummary[]>([]);
  const [status, setStatus] = useState<Load>("loading");
  const [filters, setFilters] = useState<QueueFilters>({ stage: homeStage(actor.role), ...DEFAULT_FILTERS });

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const [list, packList] = await Promise.all([studioApi.list(), studioApi.packs().catch(() => ({ packs: [] }))]);
      setLessons(list.lessons);
      setPacks(packList.packs);
      setStatus("ready");
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) return setStatus("forbidden");
      setStatus(classifyLoadError(e) === "offline" ? "offline" : "error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const counts = useMemo(() => stageCounts(lessons), [lessons]);
  const { subjects, packs: packIds } = useMemo(() => facets(lessons), [lessons]);
  const shown = useMemo(() => filterQueue(lessons, filters), [lessons, filters]);
  const tagsKnown = lessons.some((l) => l.metadata?.tags !== undefined);
  const mine = homeStage(actor.role);
  const set = <K extends keyof QueueFilters>(key: K, value: QueueFilters[K]) => setFilters((f) => ({ ...f, [key]: value }));

  return (
    <main style={{ display: "grid", gap: "var(--space-4)" }}>
      <h1 style={{ margin: 0 }}>{t("studio.queue.heading")}</h1>

      <nav aria-label={t("studio.queue.stagesLabel")}>
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
          {QUEUE_STAGES.map((stage: QueueStage) => (
            <li key={stage}>
              <Button
                variant={filters.stage === stage ? "primary" : "ghost"}
                aria-pressed={filters.stage === stage}
                label={`${t(`studio.stages.${stage}`)} (${counts[stage]})${stage === mine ? ` · ${t("studio.queue.yourStage")}` : ""}`}
                onClick={() => set("stage", stage)}
              />
            </li>
          ))}
        </ul>
      </nav>

      <fieldset style={{ border: "1px solid var(--color-focus-ring)", borderRadius: "var(--radius-md)", display: "flex", flexWrap: "wrap", gap: "var(--space-3)", padding: "var(--space-3)" }}>
        <legend>{t("studio.queue.filters")}</legend>
        <SelectField id={ids.subject} label={t("studio.queue.subject")} value={filters.subject ?? ""} onChange={(e) => set("subject", e.target.value || null)}>
          <option value="">{t("studio.queue.any")}</option>
          {subjects.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </SelectField>
        <SelectField id={ids.pack} label={t("studio.queue.pack")} value={filters.pack ?? ""} onChange={(e) => set("pack", e.target.value || null)}>
          <option value="">{t("studio.queue.any")}</option>
          {packIds.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </SelectField>
        <SelectField
          id={ids.provisional}
          label={t("studio.queue.provisional")}
          value={filters.provisional}
          onChange={(e) => set("provisional", e.target.value as QueueFilters["provisional"])}
        >
          <option value="any">{t("studio.queue.any")}</option>
          <option value="only">{t("studio.queue.provisionalOnly")}</option>
          <option value="exclude">{t("studio.queue.provisionalExclude")}</option>
        </SelectField>
        <SelectField id={ids.gates} label={t("studio.queue.gates")} value={filters.gates} onChange={(e) => set("gates", e.target.value as QueueFilters["gates"])}>
          <option value="any">{t("studio.queue.any")}</option>
          <option value="all-green">{t("studio.queue.allGreen")}</option>
          <option value="not-green">{t("studio.queue.notGreen")}</option>
        </SelectField>
        <div style={{ display: "grid", gap: "var(--space-1)" }}>
          <label htmlFor={ids.search}>{t("studio.queue.search")}</label>
          <input
            id={ids.search}
            type="search"
            value={filters.search}
            onChange={(e) => set("search", e.target.value)}
            style={{ minHeight: "var(--size-touch-min)", padding: "var(--space-2) var(--space-3)", borderRadius: "var(--radius-md)", border: "1px solid var(--color-focus-ring)", font: "inherit" }}
          />
        </div>
      </fieldset>
      {!tagsKnown && status === "ready" ? <p style={{ margin: 0 }}>{t("studio.queue.tagsNote")}</p> : null}

      <section aria-live="polite" aria-busy={status === "loading"} style={{ display: "grid", gap: "var(--space-2)" }}>
        {status === "loading" ? <p role="status">{t("studio.queue.loading")}</p> : null}
        {status === "offline" || status === "error" || status === "forbidden" ? (
          <div role="alert" style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
            <p style={{ margin: 0, color: "var(--color-danger)" }}>
              {t(status === "offline" ? "studio.queue.offline" : status === "forbidden" ? "studio.queue.forbidden" : "studio.queue.error")}
            </p>
            {status !== "forbidden" ? <Button variant="ghost" label={t("common.retry")} onClick={() => void load()} /> : null}
          </div>
        ) : null}
        {status === "ready" ? (
          <>
            <p style={{ margin: 0 }}>{t("studio.queue.count", { count: shown.length })}</p>
            {shown.length === 0 ? (
              <p style={{ margin: 0 }}>{counts[filters.stage] === 0 ? t("studio.queue.emptyStage") : t("studio.queue.empty")}</p>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {[t("studio.queue.lesson"), t("studio.queue.gradeSubject"), t("studio.queue.gates"), t("studio.queue.version")].map((h) => (
                      <th key={h} scope="col" style={{ textAlign: "start", borderBottom: "1px solid var(--color-focus-ring)", padding: "var(--space-2)" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {shown.map((l) => {
                    const g = gateSummary(l.gates);
                    return (
                      <tr key={l.lesson_id}>
                        <td style={{ padding: "var(--space-2)" }}>
                          <Link href={`/studio/lessons/${encodeURIComponent(l.lesson_id)}`} style={{ color: "var(--color-action-primary)", display: "inline-block", minHeight: "var(--size-touch-min)", paddingBlock: "var(--space-2)" }}>
                            {l.lesson_id}
                          </Link>
                          <div style={{ display: "grid", gap: "var(--space-1)" }}>
                            {Object.entries(l.title).map(([loc, text]) => (
                              <span key={loc} lang={loc} dir="auto">
                                {text}
                              </span>
                            ))}
                            {isProvisional(l) ? <ProvisionalBadge label={t("studio.tags.provisional")} /> : null}
                          </div>
                        </td>
                        <td style={{ padding: "var(--space-2)" }}>
                          {l.grade} · {l.subject}
                        </td>
                        <td style={{ padding: "var(--space-2)" }}>
                          <span aria-hidden="true">{g.allGreen ? "● " : "○ "}</span>
                          {t("studio.queue.gatesPassed", { passed: g.passed, total: g.total })}
                        </td>
                        <td style={{ padding: "var(--space-2)" }}>{l.version}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </>
        ) : null}
      </section>

      {actor.role === "subject_author" ? <DraftForm packs={packs} onCreated={() => void load()} /> : null}
    </main>
  );
}
