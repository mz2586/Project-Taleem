"use client";
// Lesson detail for reviewers and authors: provisional/provenance up front, the stage actions for
// this role, the 9 gates with findings, the learner preview, every localized field side by side,
// and version history. Where the API does not return something yet, the page says so plainly.
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/design-system/Button";
import { contentAttrs } from "@/lib/i18n/content";
import { useLocale } from "@/lib/i18n/useLocale";
import { classifyLoadError } from "@/lib/student/journey";
import { ApiError } from "@/lib/student/types";
import { studioApi, type CurriculumPackSummary, type LessonView, type ValidationResult, type VersionView } from "@/lib/studio-api";
import { lessonLocales, localizedRows, versionRows, hasContent } from "@/lib/studio/preview";
import { gateLabelKey, gateRows, importedFrom, isProvisional, stageLabelKey } from "@/lib/studio/workflow";

import { ActionPanel } from "../../ActionPanel";
import { ProvisionalBadge } from "../../controls";
import { LearnerPreview } from "../../LearnerPreview";
import { useActor } from "../../StudioShell";

type Load = "loading" | "ready" | "not-found" | "offline" | "error";

const cell = { padding: "var(--space-2)", borderBottom: "1px solid var(--color-focus-ring)", textAlign: "start" as const, verticalAlign: "top" as const };

export default function StudioLessonPage() {
  const actor = useActor();
  const { t } = useLocale();
  const params = useParams<{ lessonId: string }>();
  const lessonId = decodeURIComponent(String(params.lessonId));
  const [lesson, setLesson] = useState<LessonView | null>(null);
  const [versions, setVersions] = useState<VersionView[]>([]);
  const [packs, setPacks] = useState<CurriculumPackSummary[]>([]);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [validating, setValidating] = useState(false);
  const [status, setStatus] = useState<Load>("loading");

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const [l, v, p] = await Promise.all([
        studioApi.get(lessonId),
        studioApi.versions(lessonId).catch(() => ({ versions: [] as VersionView[] })),
        studioApi.packs().catch(() => ({ packs: [] as CurriculumPackSummary[] })),
      ]);
      setLesson(l);
      setVersions(v.versions);
      setPacks(p.packs);
      setStatus("ready");
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return setStatus("not-found");
      setStatus(classifyLoadError(e) === "offline" ? "offline" : "error");
    }
  }, [lessonId]);

  useEffect(() => {
    void load();
  }, [load]);

  const runValidation = async () => {
    setValidating(true);
    try {
      setValidation(await studioApi.validate(lessonId));
    } catch {
      setValidation(null);
    } finally {
      setValidating(false);
    }
  };

  const pack = useMemo(() => packs.find((p) => p.pack_id === lesson?.curriculum_pack) ?? null, [packs, lesson]);
  const locales = useMemo(() => (lesson ? lessonLocales(lesson, pack) : []), [lesson, pack]);

  if (status !== "ready" || !lesson) {
    return (
      <main aria-live="polite" style={{ display: "grid", gap: "var(--space-3)" }}>
        <h1 style={{ margin: 0 }}>{lessonId}</h1>
        {status === "loading" ? <p role="status">{t("common.loading")}</p> : null}
        {status === "not-found" ? <p role="alert">{t("studio.lesson.notFound")}</p> : null}
        {status === "offline" || status === "error" ? (
          <div role="alert" style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
            <p style={{ margin: 0, color: "var(--color-danger)" }}>{t(status === "offline" ? "studio.queue.offline" : "studio.queue.error")}</p>
            <Button variant="ghost" label={t("common.retry")} onClick={() => void load()} />
          </div>
        ) : null}
        <Link href="/studio" style={{ color: "var(--color-action-primary)" }}>
          {t("studio.lesson.back")}
        </Link>
      </main>
    );
  }

  const firstLocale = locales[0] ?? Object.keys(lesson.title)[0] ?? "";
  const rows = gateRows(lesson.gates, validation);
  const fieldRows = localizedRows(lesson, locales);
  const history = versionRows(versions, lesson.version);
  const sources = importedFrom(lesson);
  const tagsKnown = lesson.metadata?.tags !== undefined;
  const stageName = (s: string) => {
    const key = stageLabelKey(s);
    return key ? t(key) : s;
  };
  const gateName = (g: string) => {
    const key = gateLabelKey(g);
    return key ? t(key) : g;
  };

  return (
    <main style={{ display: "grid", gap: "var(--space-6)" }}>
      <Link href="/studio" style={{ color: "var(--color-action-primary)", minHeight: "var(--size-touch-min)", display: "inline-flex", alignItems: "center" }}>
        ‹ {t("studio.lesson.back")}
      </Link>

      <header style={{ display: "grid", gap: "var(--space-2)" }}>
        <h1 style={{ margin: 0 }} {...contentAttrs({ locale: firstLocale })}>
          {lesson.title[firstLocale] ?? lesson.lesson_id}
        </h1>
        <p style={{ margin: 0 }}>
          <code>{lesson.lesson_id}</code> ·{" "}
          {t("studio.lesson.meta", { grade: lesson.grade, subject: lesson.subject, pack: lesson.curriculum_pack ?? "—", version: lesson.version })}
        </p>
        <p style={{ margin: 0 }}>
          {t("studio.lesson.stage")}: <strong>{stageName(lesson.state)}</strong>
        </p>
        {isProvisional(lesson) ? <ProvisionalBadge label={t("studio.tags.provisional")} /> : null}
        {sources.map((s) => (
          <p key={s} style={{ margin: 0 }}>
            {t("studio.tags.importedFrom", { source: s })}
          </p>
        ))}
        {!tagsKnown ? <p style={{ margin: 0 }}>{t("studio.lesson.tagsUnavailable")}</p> : null}
        {lesson.learning_outcomes.length > 0 ? (
          <p style={{ margin: 0 }}>
            {t("studio.lesson.outcomes")}: <code>{lesson.learning_outcomes.join(", ")}</code>
          </p>
        ) : null}
      </header>

      <ActionPanel
        lesson={lesson}
        actor={actor}
        validation={validation}
        versions={versions}
        onChanged={(u) => {
          setLesson(u);
          setValidation(null);
          void studioApi.versions(lessonId).then((v) => setVersions(v.versions)).catch(() => undefined);
        }}
      />

      <section aria-labelledby="gates-h" style={{ display: "grid", gap: "var(--space-3)" }}>
        <h2 id="gates-h" style={{ margin: 0 }}>
          {t("studio.lesson.gatesHeading")}
        </h2>
        <div>
          <Button variant="ghost" label={t("studio.lesson.validate")} loading={validating} onClick={() => void runValidation()} />
        </div>
        <div aria-live="polite">
          {validation ? <p style={{ margin: 0 }}>{validation.ok ? t("studio.lesson.validationOk") : t("studio.lesson.validationFailed")}</p> : null}
          {validation && validation.structural.length > 0 ? (
            <>
              <h3 style={{ marginBlockEnd: 0 }}>{t("studio.lesson.structural")}</h3>
              <ul>
                {validation.structural.map((f, i) => (
                  <li key={i}>
                    <strong>{f.severity}</strong> {f.field ? <code>{f.field}</code> : null} {f.message}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr>
              <th scope="col" style={cell}>{t("studio.lesson.gateColumn")}</th>
              <th scope="col" style={cell}>{t("studio.lesson.modeColumn")}</th>
              <th scope="col" style={cell}>{t("studio.lesson.findingsColumn")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.gate}>
                <th scope="row" style={cell}>
                  <span aria-hidden="true">{r.status === "passed" ? "● " : r.status === "failed" ? "✕ " : "○ "}</span>
                  {gateName(r.gate)} —{" "}
                  {t(r.status === "passed" ? "studio.gateStatus.passed" : r.status === "failed" ? "studio.gateStatus.failed" : "studio.gateStatus.notRun")}
                </th>
                <td style={cell}>
                  {t(r.mode === "auto" ? "studio.gateMode.auto" : r.mode === "human" ? "studio.gateMode.human" : "studio.gateMode.autoHuman")}
                  {r.certifiedAt ? <div>{t("studio.lesson.certifiedAt", { stage: t(`studio.stages.${r.certifiedAt}`) })}</div> : null}
                  {r.reviewerRole ? <div>{t("studio.lesson.certifiedBy", { role: r.reviewerRole })}</div> : null}
                </td>
                <td style={cell}>
                  {r.findings.length > 0 ? (
                    <ul style={{ margin: 0 }}>
                      {r.findings.map((f, i) => (
                        <li key={i}>{f}</li>
                      ))}
                    </ul>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section aria-labelledby="preview-h" style={{ display: "grid", gap: "var(--space-3)" }}>
        <h2 id="preview-h" style={{ margin: 0 }}>
          {t("studio.lesson.preview")}
        </h2>
        <LearnerPreview lesson={lesson} locales={locales} />
      </section>

      <section aria-labelledby="fields-h" style={{ display: "grid", gap: "var(--space-3)" }}>
        <h2 id="fields-h" style={{ margin: 0 }}>
          {t("studio.lesson.fields")}
        </h2>
        {!hasContent(lesson) ? <p style={{ margin: 0 }}>{t("studio.lesson.fieldsTitleOnly")}</p> : null}
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>
                <th scope="col" style={cell}>{t("studio.lesson.field")}</th>
                {locales.map((l) => (
                  <th key={l} scope="col" style={cell}>
                    {l}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {fieldRows.map((r) => (
                <tr key={r.field}>
                  <th scope="row" style={cell}>
                    <code>{r.field}</code>
                  </th>
                  {r.values.map((v) => (
                    <td key={v.locale} style={cell} {...(v.missing ? {} : contentAttrs({ locale: v.locale }))}>
                      {v.missing ? (
                        <span style={{ color: "var(--color-danger)" }}>
                          <span aria-hidden="true">✕ </span>
                          {t("studio.lesson.missing")}
                        </span>
                      ) : (
                        v.text
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="prov-h" style={{ display: "grid", gap: "var(--space-2)" }}>
        <h2 id="prov-h" style={{ margin: 0 }}>
          {t("studio.lesson.provenance")}
        </h2>
        {lesson.provenance ? (
          <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "max-content 1fr", gap: "var(--space-1) var(--space-3)" }}>
            <dt>{t("studio.lesson.derivation")}</dt>
            <dd style={{ margin: 0 }}>{lesson.provenance.derivation}</dd>
            <dt>{t("studio.lesson.source")}</dt>
            <dd style={{ margin: 0 }}>{lesson.provenance.source}</dd>
            <dt>{t("studio.lesson.license")}</dt>
            <dd style={{ margin: 0 }}>{lesson.provenance.license}</dd>
            <dt>{t("studio.lesson.permission")}</dt>
            <dd style={{ margin: 0 }}>{lesson.provenance.permission_ref ?? t("studio.lesson.none")}</dd>
          </dl>
        ) : (
          <p style={{ margin: 0 }}>{t("studio.lesson.provenanceUnavailable")}</p>
        )}
      </section>

      <section aria-labelledby="versions-h" style={{ display: "grid", gap: "var(--space-2)" }}>
        <h2 id="versions-h" style={{ margin: 0 }}>
          {t("studio.lesson.versions")}
        </h2>
        {history.length === 0 ? (
          <p style={{ margin: 0 }}>{t("studio.lesson.versionsEmpty")}</p>
        ) : (
          <>
            <ol style={{ margin: 0, display: "grid", gap: "var(--space-2)" }}>
              {history.map((v) => (
                <li key={v.version}>
                  <strong>v{v.version}</strong>
                  {v.isCurrent ? ` · ${t("studio.lesson.versionCurrent")}` : ""} · {v.changeSummary || "—"} · {v.authorRole} ·{" "}
                  {v.contentChanged ? t("studio.lesson.contentChanged") : t("studio.lesson.contentSame")} · <code>{v.contentHash.slice(0, 19)}</code>
                </li>
              ))}
            </ol>
            <p style={{ margin: 0 }}>{t("studio.lesson.diffUnavailable")}</p>
          </>
        )}
        <h3 style={{ marginBlockEnd: 0 }}>{t("studio.lesson.history")}</h3>
        {lesson.workflow?.history ? (
          <ol style={{ margin: 0 }}>
            {lesson.workflow.history.map((h, i) => (
              <li key={i}>
                {h.action} · {h.from_state} → {h.to_state} · {h.actor_role}
                {h.note ? ` · ${h.note}` : ""}
              </li>
            ))}
          </ol>
        ) : (
          <p style={{ margin: 0 }}>{t("studio.lesson.historyUnavailable")}</p>
        )}
      </section>
    </main>
  );
}
