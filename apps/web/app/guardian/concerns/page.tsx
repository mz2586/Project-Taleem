"use client";
// Raise a safeguarding concern about one of your own children, and see the concerns you raised.
//
// The list shows ONLY concerns this guardian raised, with a coarse status (received / being looked
// at / closed) — never triage notes, escalation, or outcome. A concern a child raised never appears
// here or anywhere else in the portal: it may be about this household (server rule, contexts/
// safeguarding). No response time is promised; the SLA is undecided (FD-06).
import { useCallback, useEffect, useId, useState, type FormEvent } from "react";

import { FormError, FormNotice } from "@/components/form";
import { RequireSession } from "@/components/RequireSession";
import { Card, EmptyState, Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { familyApi } from "@/lib/guardian/api";
import { formatDate } from "@/lib/guardian/format";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import { guardianConcernApi } from "@/lib/safeguarding/api";
import { CATEGORY_OPTIONS, categoryOption, cleanText, MAX_TEXT, type Category } from "@/lib/safeguarding/categories";
import { guardianErrorKey, guardianStatusKey, type GuardianConcernWire } from "@/lib/safeguarding/triage";
import type { Learner } from "@/lib/session/types";
import { classifyLoadError, type LoadFailure } from "@/lib/student/journey";

import { GuardianLoadFailure } from "../GuardianLoadFailure";
import { GuardianShell } from "../GuardianShell";

const controlStyle = {
  minHeight: "var(--size-touch-min)",
  padding: "var(--space-2)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-focus-ring)",
  background: "var(--color-bg-canvas)",
  color: "var(--color-text-primary)",
  font: "inherit",
  fontSize: "var(--font-size-body-min-urdu)",
  width: "100%",
  boxSizing: "border-box",
} as const;

function ConcernsPage() {
  const { t, locale } = useLocale();
  const learnerId = useId();
  const textId = useId();
  const categoryName = useId();
  const [learners, setLearners] = useState<Learner[]>([]);
  const [concerns, setConcerns] = useState<GuardianConcernWire[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | LoadFailure>("loading");
  const [studentRef, setStudentRef] = useState("");
  const [category, setCategory] = useState<Category | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);
  const [sent, setSent] = useState(false);

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const [family, mine] = await Promise.all([familyApi.listLearners(), guardianConcernApi.mine()]);
      setLearners(family.learners);
      setConcerns(mine.concerns);
      setStudentRef((current) => current || family.learners[0]?.student_ref || "");
      setStatus("ready");
    } catch (e) {
      setStatus(classifyLoadError(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const cleaned = cleanText(text);
  const nameOf = (ref: string) => learners.find((l) => l.student_ref === ref)?.display_name ?? "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSent(false);
    if (!category || !studentRef || !cleaned.ok) return;
    setBusy(true);
    try {
      const created = await guardianConcernApi.raise({
        studentRef,
        category,
        ...(cleaned.text ? { text: cleaned.text } : {}),
      });
      setConcerns((list) => [created, ...list]);
      setCategory(null);
      setText("");
      setSent(true);
    } catch (e) {
      setError(guardianErrorKey(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <GuardianShell title={t("safeguarding.guardian.title")}>
      <p style={{ margin: 0 }}>{t("safeguarding.guardian.intro")}</p>
      <p style={{ margin: 0, fontWeight: 700 }}>{t("safeguarding.guardian.emergency")}</p>

      {status === "loading" ? <Skeleton lines={4} label={t("common.loading")} /> : null}
      {status !== "loading" && status !== "ready" ? (
        <GuardianLoadFailure
          failure={status}
          offlineTitle="guardian.dashboard.offlineTitle"
          offlineBody="safeguarding.guardian.errors.offline"
          errorMessage="safeguarding.guardian.errors.generic"
          onRetry={() => void load()}
        />
      ) : null}

      {status === "ready" ? (
        <>
          {learners.length === 0 ? (
            <EmptyState title={t("safeguarding.guardian.title")} body={t("safeguarding.guardian.noLearners")} />
          ) : (
            <form onSubmit={submit} style={{ display: "grid", gap: "var(--space-3)" }}>
              <div aria-live="polite">
                {error ? <FormError message={t(error)} /> : null}
                {sent ? <FormNotice message={t("safeguarding.guardian.sent")} /> : null}
              </div>
              <div style={{ display: "grid", gap: "var(--space-1)" }}>
                <label htmlFor={learnerId} style={{ fontSize: "var(--font-size-body-min-urdu)" }}>
                  {t("safeguarding.guardian.learner")}
                </label>
                <select id={learnerId} value={studentRef} onChange={(e) => setStudentRef(e.target.value)} style={controlStyle}>
                  {learners.map((l) => (
                    <option key={l.student_ref} value={l.student_ref}>
                      {l.display_name}
                    </option>
                  ))}
                </select>
              </div>
              <fieldset style={{ border: "1px solid var(--color-focus-ring)", borderRadius: "var(--radius-md)", padding: "var(--space-3)", display: "grid", gap: "var(--space-2)" }}>
                <legend style={{ fontSize: "var(--font-size-body-min-urdu)" }}>{t("safeguarding.guardian.category")}</legend>
                {CATEGORY_OPTIONS.map((option) => {
                  const id = `${categoryName}-${option.value}`;
                  return (
                    <div key={option.value} style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", minHeight: "var(--size-touch-min)" }}>
                      <input
                        id={id}
                        type="radio"
                        name={categoryName}
                        value={option.value}
                        checked={category === option.value}
                        onChange={() => setCategory(option.value)}
                        required
                        style={{ width: 24, height: 24 }}
                      />
                      <label htmlFor={id}>
                        <span aria-hidden="true">{option.symbol} </span>
                        {t(option.adultKey)}
                      </label>
                    </div>
                  );
                })}
              </fieldset>
              <div style={{ display: "grid", gap: "var(--space-1)" }}>
                <label htmlFor={textId} style={{ fontSize: "var(--font-size-body-min-urdu)" }}>
                  {t("safeguarding.guardian.text")}
                </label>
                <span id={`${textId}-hint`}>{t("safeguarding.guardian.textHint", { max: MAX_TEXT })}</span>
                <textarea
                  id={textId}
                  dir="auto"
                  rows={4}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  aria-describedby={`${textId}-hint${cleaned.ok ? "" : ` ${textId}-error`}`}
                  aria-invalid={!cleaned.ok || undefined}
                  style={controlStyle}
                />
                {!cleaned.ok ? (
                  <span id={`${textId}-error`} role="alert" style={{ color: "var(--color-danger)" }}>
                    {t("safeguarding.guardian.tooLong", { max: MAX_TEXT })}
                  </span>
                ) : null}
              </div>
              <div>
                <Button
                  type="submit"
                  variant="brand"
                  label={t("safeguarding.guardian.submit")}
                  loading={busy}
                  disabled={!category || !cleaned.ok}
                />
              </div>
            </form>
          )}

          <section aria-labelledby="my-concerns" style={{ display: "grid", gap: "var(--space-2)" }}>
            <h2 id="my-concerns" style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
              {t("safeguarding.guardian.listTitle")}
            </h2>
            <p style={{ margin: 0 }}>{t("safeguarding.guardian.listNote")}</p>
            {concerns.length === 0 ? (
              <p style={{ margin: 0 }}>{t("safeguarding.guardian.empty")}</p>
            ) : (
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-2)" }}>
                {concerns.map((c) => {
                  const option = categoryOption(c.category);
                  return (
                    <li key={c.concern_id}>
                      <Card>
                        <div style={{ display: "grid", gap: "var(--space-1)" }}>
                          <strong>{option ? t(option.adultKey) : c.category}</strong>
                          <span dir="auto">{nameOf(c.student_ref)}</span>
                          <span>{t("safeguarding.guardian.raisedOn", { date: formatDate(c.raised_at, locale) })}</span>
                          <span>{t(guardianStatusKey(c.status))}</span>
                          {c.text ? (
                            <p dir="auto" style={{ margin: 0 }}>
                              {c.text}
                            </p>
                          ) : null}
                        </div>
                      </Card>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </>
      ) : null}
    </GuardianShell>
  );
}

export default function GuardianConcernsPage() {
  return (
    <RequireSession role="guardian" signInPath="/guardian/signin">
      <ConcernsPage />
    </RequireSession>
  );
}
