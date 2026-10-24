"use client";
// Report cards for one class (REPORT_CARD_CONTRACT.md §2). The teacher chooses the dates (default:
// the last three months), previews — nothing is stored — and sees each learner's card compactly and
// who was left out and why (the server's exact reason codes, in plain words). They may add a note per
// learner. A learner who already has a card for these dates is listed as "already has a card" with
// "Correct it": that re-runs the preview with `supersedes` naming the card the server reported, so
// the replacing card is seen before it is issued. Issuing has an in-page confirm step; focus moves
// to the confirm panel, then to the result. Changing the dates after a preview requires a new one.
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { FormError, FormNotice, TextField } from "@/components/form";
import { ReportCardView } from "@/components/reporting/ReportCardView";
import { RequireSession } from "@/components/RequireSession";
import { Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { ButtonLink } from "@/design-system/ButtonLink";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import { reportIssueApi } from "@/lib/reporting/api";
import {
  defaultPeriod,
  issueBody,
  issueErrorKey,
  periodFromInputs,
  previewBody,
  skippedRows,
  type PeriodInputs,
} from "@/lib/reporting/teacher";
import { cardView, namePreference } from "@/lib/reporting/view";
import { reportCard, resultCards, skipped, type ReportCard, type Skipped } from "@/lib/reporting/wire";
import { localDateInput } from "@/lib/teacher/assignments";
import { teacherApi } from "@/lib/teacher/api";
import { teacherFailure, type TeacherFailure } from "@/lib/teacher/errors";
import type { ClassDetail } from "@/lib/teacher/types";

import { TeacherShell } from "../../../TeacherShell";
import { TeacherState } from "../../../TeacherState";
import { CommentField } from "./CommentField";

const nowSeconds = () => Math.floor(Date.now() / 1000);

const sectionStyle = {
  border: "1px solid var(--color-focus-ring)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-4)",
  display: "grid",
  gap: "var(--space-3)",
  minWidth: 0,
} as const;

interface Preview {
  inputs: PeriodInputs;
  periodStart: number;
  periodEnd: number;
  cards: ReportCard[];
  skipped: Skipped[];
}

function ReportCardsPage() {
  const { t, locale } = useLocale();
  const params = useParams<{ classId: string }>();
  const classId = params?.classId ?? "";
  const [detail, setDetail] = useState<ClassDetail | null>(null);
  const [failure, setFailure] = useState<TeacherFailure | null>(null);

  const [inputs, setInputs] = useState<PeriodInputs>(() => defaultPeriod(nowSeconds()));
  const [periodProblems, setPeriodProblems] = useState<{ start?: MessageKey; end?: MessageKey }>({});
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [comments, setComments] = useState<Record<string, string>>({});
  const [supersedes, setSupersedes] = useState<Record<string, string>>({});
  const [confirming, setConfirming] = useState(false);
  const [issuing, setIssuing] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);
  const [notice, setNotice] = useState<string[] | null>(null);

  const confirmRef = useRef<HTMLHeadingElement | null>(null);
  const issueRef = useRef<HTMLDivElement | null>(null);
  const resultRef = useRef<HTMLDivElement | null>(null);
  const previewRef = useRef<HTMLHeadingElement | null>(null);

  const load = useCallback(async () => {
    setFailure(null);
    try {
      setDetail(await teacherApi.classDetail(classId));
    } catch (e) {
      setFailure(teacherFailure(e));
    }
  }, [classId]);

  useEffect(() => {
    void load();
  }, [load]);

  const stale = !!preview && (preview.inputs.start !== inputs.start || preview.inputs.end !== inputs.end);

  async function runPreview(period: { periodStart: number; periodEnd: number }, dates: PeriodInputs, nextSupersedes: Record<string, string>) {
    setError(null);
    setNotice(null);
    setConfirming(false);
    setPreviewing(true);
    try {
      const wire = await reportIssueApi.preview(classId, previewBody(period, undefined, nextSupersedes));
      setPreview({
        inputs: { ...dates },
        periodStart: period.periodStart,
        periodEnd: period.periodEnd,
        cards: resultCards(wire).map((c) => reportCard(c, namePreference(locale))),
        skipped: skipped(wire),
      });
      setSupersedes(nextSupersedes);
      requestAnimationFrame(() => previewRef.current?.focus());
    } catch (e) {
      setPreview(null);
      setError(issueErrorKey(e));
    } finally {
      setPreviewing(false);
    }
  }

  function submitPreview(event: FormEvent) {
    event.preventDefault();
    const period = periodFromInputs(inputs, nowSeconds());
    if (!period.ok) {
      setPeriodProblems(period.problems);
      return;
    }
    setPeriodProblems({});
    // New dates start without corrections: a correction names a card for specific dates.
    void runPreview(period, inputs, {});
  }

  /** "Correct it" / "Do not correct": the same dates, previewed again with or without the supersede. */
  function setCorrection(studentRef: string, cardId: string | null) {
    if (!preview || previewing) return;
    const next = { ...supersedes };
    if (cardId) next[studentRef] = cardId;
    else delete next[studentRef];
    void runPreview(preview, preview.inputs, next);
  }

  const draft = preview
    ? issueBody({
        periodStart: preview.periodStart,
        periodEnd: preview.periodEnd,
        studentRefs: preview.cards.map((c) => c.studentRef),
        comments,
        supersedes,
      })
    : null;

  function askToIssue() {
    setError(null);
    if (!draft || stale) {
      setError(stale ? "teacher.reportCards.previewStale" : "teacher.reportCards.nothingToIssue");
      return;
    }
    if (!draft.ok) {
      setError(draft.problem);
      return;
    }
    setConfirming(true);
    requestAnimationFrame(() => confirmRef.current?.focus());
  }

  function cancelIssue() {
    setConfirming(false);
    requestAnimationFrame(() => issueRef.current?.querySelector("button")?.focus());
  }

  async function issue() {
    if (!draft?.ok || issuing) return;
    setIssuing(true);
    setError(null);
    try {
      const wire = await reportIssueApi.issue(classId, draft.body);
      const issued = resultCards(wire).length;
      const left = skipped(wire).length;
      const lines = [t("teacher.reportCards.done", { count: issued })];
      if (left > 0) lines.push(t("teacher.reportCards.doneSkipped", { count: left }));
      setNotice(lines);
      setPreview(null);
      setComments({});
      setSupersedes({});
      setConfirming(false);
      requestAnimationFrame(() => resultRef.current?.focus());
    } catch (e) {
      setError(issueErrorKey(e));
      setConfirming(false);
      requestAnimationFrame(() => issueRef.current?.focus());
    } finally {
      setIssuing(false);
    }
  }

  const title = failure === "not-available" ? t("teacher.state.notAvailableTitle") : detail ? `${t("teacher.reportCards.title")} — ${detail.name}` : t("teacher.reportCards.title");
  const corrections = draft?.ok ? Object.keys(draft.body.supersedes ?? {}).length : 0;
  const skippedList = preview ? skippedRows(preview.skipped) : [];

  return (
    <TeacherShell title={title}>
      <div>
        <ButtonLink href={`/teacher/classes/${encodeURIComponent(classId)}`} variant="ghost" label={t("teacher.reportCards.back")} />
      </div>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {failure ? <TeacherState failure={failure} onRetry={() => void load()} /> : null}
        {!failure && !detail ? <Skeleton lines={3} label={t("teacher.detail.loading")} /> : null}
      </div>

      {detail && !failure ? (
        <>
          <p style={{ margin: 0 }}>{t("teacher.reportCards.intro")}</p>

          <div ref={resultRef} tabIndex={-1} style={{ display: "grid", gap: "var(--space-2)" }}>
            {notice ? notice.map((line) => <FormNotice key={line} message={line} />) : null}
          </div>

          <form onSubmit={submitPreview} noValidate style={sectionStyle}>
            <fieldset style={{ border: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-3)", minWidth: 0 }}>
              <legend style={{ padding: 0, fontWeight: 700 }}>{t("teacher.reportCards.periodLegend")}</legend>
              <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t("teacher.reportCards.periodHint")}</p>
              <TextField
                id="period-start"
                type="date"
                label={t("teacher.reportCards.startLabel")}
                error={periodProblems.start ? t(periodProblems.start) : undefined}
                value={inputs.start}
                max={localDateInput(nowSeconds())}
                onChange={(e) => setInputs((v) => ({ ...v, start: e.target.value }))}
                required
              />
              <TextField
                id="period-end"
                type="date"
                label={t("teacher.reportCards.endLabel")}
                error={periodProblems.end ? t(periodProblems.end) : undefined}
                value={inputs.end}
                max={localDateInput(nowSeconds())}
                onChange={(e) => setInputs((v) => ({ ...v, end: e.target.value }))}
                required
              />
            </fieldset>
            <div>
              <Button type="submit" variant="primary" label={previewing ? t("teacher.reportCards.previewing") : t("teacher.reportCards.preview")} loading={previewing} />
            </div>
          </form>

          {error ? <FormError message={t(error, { max: 1000 })} /> : null}

          {preview ? (
            <section style={sectionStyle} aria-labelledby="preview-title">
              <h2 id="preview-title" ref={previewRef} tabIndex={-1} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
                {t("teacher.reportCards.previewTitle")}
              </h2>
              {stale ? <p role="alert" style={{ margin: 0, color: "var(--color-danger)" }}>{t("teacher.reportCards.previewStale")}</p> : null}
              <p style={{ margin: 0 }}>{t("teacher.reportCards.previewCount", { count: preview.cards.length })}</p>
              {preview.cards.length === 0 ? <p style={{ margin: 0 }}>{t("teacher.reportCards.previewEmpty")}</p> : null}

              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-4)" }}>
                {preview.cards.map((card, i) => (
                  <li key={card.studentRef} style={{ display: "grid", gap: "var(--space-2)", minWidth: 0 }}>
                    <ReportCardView
                      view={cardView({ ...card, comment: null }, { t, locale })}
                      t={t}
                      headingLevel={3}
                      compact
                      idBase={`preview-${i}`}
                    />
                    <CommentField
                      id={`comment-${i}`}
                      value={comments[card.studentRef] ?? ""}
                      onChange={(text) => setComments((c) => ({ ...c, [card.studentRef]: text }))}
                      t={t}
                    />
                    {supersedes[card.studentRef] ? (
                      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "var(--space-2)" }}>
                        <p style={{ margin: 0 }}>
                          <span aria-hidden="true">↺ </span>
                          {t("teacher.reportCards.correcting")}
                        </p>
                        <Button
                          variant="ghost"
                          label={t("teacher.reportCards.correctUndo")}
                          disabled={previewing}
                          onClick={() => setCorrection(card.studentRef, null)}
                        />
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>

              {skippedList.length > 0 ? (
                <div style={{ display: "grid", gap: "var(--space-1)" }}>
                  <h3 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{t("teacher.reportCards.skippedTitle")}</h3>
                  <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)", display: "grid", gap: "var(--space-1)" }}>
                    {skippedList.map((s) => (
                      <li key={s.studentRef} data-skip-reason={s.reason} style={{ display: "grid", gap: "var(--space-1)", justifyItems: "start" }}>
                        <span>
                          <bdi>{s.learnerName || t("teacher.reportCards.unnamedLearner")}</bdi>
                          {" — "}
                          {t(s.reasonKey)}
                        </span>
                        {s.canCorrect && s.cardId ? (
                          <>
                            <span style={{ fontSize: "var(--font-size-body-min)" }}>{t("teacher.reportCards.correctItHint")}</span>
                            <Button
                              variant="ghost"
                              label={t("teacher.reportCards.correctIt")}
                              disabled={previewing}
                              onClick={() => setCorrection(s.studentRef, s.cardId)}
                            />
                          </>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {preview.cards.length > 0 ? (
                <div ref={issueRef} tabIndex={-1} style={{ display: "grid", gap: "var(--space-2)" }}>
                  {!confirming ? (
                    <div>
                      <Button variant="brand" label={t("teacher.reportCards.issue")} onClick={askToIssue} />
                    </div>
                  ) : (
                    <div
                      role="group"
                      aria-labelledby="confirm-title"
                      style={{ display: "grid", gap: "var(--space-2)", padding: "var(--space-3)", border: "2px solid var(--color-brand)", borderRadius: "var(--radius-md)" }}
                    >
                      <h3 id="confirm-title" ref={confirmRef} tabIndex={-1} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
                        {t("teacher.reportCards.confirmTitle", { count: preview.cards.length })}
                      </h3>
                      <p style={{ margin: 0 }}>{t("teacher.reportCards.confirmBody")}</p>
                      {corrections > 0 ? <p style={{ margin: 0 }}>{t("teacher.reportCards.confirmCorrections", { count: corrections })}</p> : null}
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
                        <Button
                          variant="brand"
                          label={issuing ? t("teacher.reportCards.issuing") : t("teacher.reportCards.confirmYes")}
                          loading={issuing}
                          onClick={() => void issue()}
                        />
                        <Button variant="ghost" label={t("teacher.reportCards.confirmNo")} onClick={cancelIssue} disabled={issuing} />
                      </div>
                    </div>
                  )}
                </div>
              ) : null}
            </section>
          ) : null}
        </>
      ) : null}
    </TeacherShell>
  );
}

export default function GuardedReportCardsPage() {
  return (
    <RequireSession role="teacher" signInPath="/teacher/signin">
      <ReportCardsPage />
    </RequireSession>
  );
}
