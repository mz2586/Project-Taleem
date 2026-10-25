"use client";
// One concern: the raiser's own words, where it came from, the household caution for a concern a
// child raised, notes, and the audit trail — and the actions its status allows. Opening this page is
// itself audited server-side (concern.viewed). A concern that names a homework submission offers
// "What the child wrote", loaded only when the lead asks (each read audited: concern.context_viewed). "External referral needed" records a decision for a
// person to act on; this software contacts nobody (FD-04).
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useId, useState, type FormEvent } from "react";

import { Button } from "@/design-system/Button";
import { formatDateTime } from "@/lib/guardian/format";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import { leadApi } from "@/lib/safeguarding/api";
import { categoryOption } from "@/lib/safeguarding/categories";
import {
  actionErrorKey,
  hasFlaggedWork,
  ageLabel,
  allowedActions,
  outcomeKey,
  outcomeOptions,
  overdueKey,
  statusKey,
  type ConcernDetailWire,
  type Outcome,
} from "@/lib/safeguarding/triage";

import { FlaggedWork } from "./FlaggedWork";

const box = {
  border: "1px solid var(--color-focus-ring)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-3)",
  display: "grid",
  gap: "var(--space-2)",
} as const;

const control = {
  font: "inherit",
  padding: "var(--space-2)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-focus-ring)",
  background: "var(--color-bg-canvas)",
  color: "var(--color-text-primary)",
  width: "100%",
  boxSizing: "border-box",
  minHeight: "var(--size-touch-min)",
} as const;

export default function ConcernDetailPage() {
  const params = useParams<{ concernId: string }>();
  const concernId = decodeURIComponent(params.concernId ?? "");
  const { t, locale } = useLocale();
  const noteId = useId();
  const reasonId = useId();
  const outcomeId = useId();
  const closingId = useId();
  const [concern, setConcern] = useState<ConcernDetailWire | null>(null);
  const [loadError, setLoadError] = useState<MessageKey | null>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; key: MessageKey } | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [outcome, setOutcome] = useState<Outcome | "">("");
  const [closing, setClosing] = useState("");

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      setConcern(await leadApi.detail(concernId));
    } catch (e) {
      const status = (e as { status?: number }).status;
      setLoadError(status === 404 ? "safeguarding.console.detail.notFound" : actionErrorKey(e));
    }
  }, [concernId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(run: () => Promise<ConcernDetailWire>, after?: () => void) {
    setBusy(true);
    setMessage(null);
    try {
      setConcern(await run());
      after?.();
      setMessage({ kind: "ok", key: "safeguarding.console.detail.done" });
    } catch (e) {
      setMessage({ kind: "error", key: actionErrorKey(e) });
    } finally {
      setBusy(false);
    }
  }

  const back = (
    <Link href="/safeguarding" style={{ color: "var(--color-action-primary)", minHeight: "var(--size-touch-min)", display: "inline-flex", alignItems: "center" }}>
      {t("safeguarding.console.detail.back")}
    </Link>
  );

  if (!concern) {
    return (
      <main style={{ display: "grid", gap: "var(--space-3)" }}>
        <h1 style={{ margin: 0 }}>{t("safeguarding.console.detail.heading")}</h1>
        {back}
        {loadError ? (
          <p role="alert" style={{ color: "var(--color-danger)", margin: 0 }}>
            {t(loadError)}
          </p>
        ) : (
          <p role="status" aria-busy="true">
            {t("common.loading")}
          </p>
        )}
      </main>
    );
  }

  const allowed = allowedActions(concern.status);
  const option = categoryOption(concern.category);
  const age = ageLabel(concern.age_seconds);
  const submitNote = (e: FormEvent) => {
    e.preventDefault();
    if (note.trim()) void act(() => leadApi.addNote(concern.concern_id, note.trim()), () => setNote(""));
  };
  const submitEscalation = (e: FormEvent) => {
    e.preventDefault();
    if (reason.trim()) void act(() => leadApi.escalate(concern.concern_id, reason.trim()), () => setReason(""));
  };
  const submitResolve = (e: FormEvent) => {
    e.preventDefault();
    if (outcome) {
      void act(
        () => leadApi.resolve(concern.concern_id, outcome, closing.trim() || undefined),
        () => setClosing(""),
      );
    }
  };

  return (
    <main style={{ display: "grid", gap: "var(--space-4)" }}>
      <h1 style={{ margin: 0 }}>
        {t("safeguarding.console.detail.heading")} · {concern.priority} · {option ? t(option.adultKey) : concern.category}
      </h1>
      {back}

      <div aria-live="polite">
        {message ? (
          <p role={message.kind === "error" ? "alert" : "status"} style={{ margin: 0, color: message.kind === "error" ? "var(--color-danger)" : "var(--color-brand)" }}>
            {t(message.key)}
          </p>
        ) : null}
      </div>

      <section style={{ ...box, border: concern.household_caution ? "2px solid var(--color-danger)" : box.border }} aria-label={t("safeguarding.console.columns.raisedBy")}>
        <strong>{t(`safeguarding.console.raisedBy.${concern.raised_by_role}`)}</strong>
        <p style={{ margin: 0 }}>
          {concern.household_caution ? t("safeguarding.console.detail.household") : t("safeguarding.console.detail.guardianRaised")}
        </p>
        <p style={{ margin: 0 }}>
          <bdi dir="ltr">{t("safeguarding.console.detail.subject", { ref: concern.subject_ref })}</bdi>
        </p>
      </section>

      <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "max-content 1fr", gap: "var(--space-1) var(--space-3)" }}>
        <dt>{t("safeguarding.console.columns.status")}</dt>
        <dd style={{ margin: 0 }}>{t(statusKey(concern.status))}</dd>
        <dt>{t("safeguarding.console.columns.age")}</dt>
        <dd style={{ margin: 0 }}>{t(age.key, age.params)}</dd>
        <dt>{t("safeguarding.console.columns.overdue")}</dt>
        <dd style={{ margin: 0 }}>{t(overdueKey(concern.overdue))}</dd>
        <dt>{t("safeguarding.console.detail.where")}</dt>
        <dd style={{ margin: 0 }}>
          {concern.context.screen ? t("safeguarding.console.detail.screen", { screen: concern.context.screen }) : t("safeguarding.console.detail.noContext")}
          {concern.context.lesson_id ? ` · ${t("safeguarding.console.detail.lesson", { id: concern.context.lesson_id })}` : null}
        </dd>
        {concern.outcome ? (
          <>
            <dt>{t("safeguarding.console.detail.outcomeLabel")}</dt>
            <dd style={{ margin: 0 }}>{t(outcomeKey(concern.outcome))}</dd>
          </>
        ) : null}
      </dl>

      <section style={box} aria-labelledby="concern-words">
        <h2 id="concern-words" style={{ margin: 0 }}>{t("safeguarding.console.detail.words")}</h2>
        {concern.text ? (
          <p dir="auto" style={{ margin: 0, whiteSpace: "pre-wrap" }}>
            {concern.text}
          </p>
        ) : (
          <p style={{ margin: 0 }}>{t("safeguarding.console.detail.noWords")}</p>
        )}
      </section>

      {hasFlaggedWork(concern) ? (
        <FlaggedWork concernId={concern.concern_id} t={t} locale={locale} read={leadApi.context} />
      ) : null}

      <p style={{ margin: 0 }}>{t("safeguarding.console.detail.contactedNobody")}</p>

      {allowed.acknowledge ? (
        <div>
          <Button
            variant="brand"
            label={t("safeguarding.console.detail.acknowledge")}
            loading={busy}
            onClick={() => void act(() => leadApi.acknowledge(concern.concern_id))}
          />
        </div>
      ) : null}

      <section style={box} aria-labelledby="concern-notes">
        <h2 id="concern-notes" style={{ margin: 0 }}>{t("safeguarding.console.detail.notes")}</h2>
        {concern.notes.length === 0 ? <p style={{ margin: 0 }}>{t("safeguarding.console.detail.noNotes")}</p> : null}
        <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)", display: "grid", gap: "var(--space-2)" }}>
          {concern.notes.map((n) => (
            <li key={n.note_id}>
              <p dir="auto" style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                {n.body}
              </p>
              <small>
                <bdi dir="ltr">{n.author_ref}</bdi> · {formatDateTime(n.created_at, locale)}
              </small>
            </li>
          ))}
        </ul>
        {allowed.note ? (
          <form onSubmit={submitNote} style={{ display: "grid", gap: "var(--space-2)" }}>
            <label htmlFor={noteId}>{t("safeguarding.console.detail.noteLabel")}</label>
            <textarea id={noteId} dir="auto" rows={3} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} style={control} />
            <div>
              <Button type="submit" variant="primary" label={t("safeguarding.console.detail.saveNote")} loading={busy} disabled={!note.trim()} />
            </div>
          </form>
        ) : null}
      </section>

      {allowed.escalate ? (
        <form onSubmit={submitEscalation} style={box} aria-labelledby="concern-escalate">
          <h2 id="concern-escalate" style={{ margin: 0 }}>{t("safeguarding.console.detail.escalateHeading")}</h2>
          <p style={{ margin: 0 }}>{t("safeguarding.console.notApproved")}</p>
          <label htmlFor={reasonId}>{t("safeguarding.console.detail.escalateLabel")}</label>
          <textarea id={reasonId} dir="auto" rows={3} maxLength={2000} required value={reason} onChange={(e) => setReason(e.target.value)} style={control} />
          <div>
            <Button type="submit" variant="danger" label={t("safeguarding.console.detail.escalate")} loading={busy} disabled={!reason.trim()} />
          </div>
        </form>
      ) : null}

      {allowed.resolve ? (
        <form onSubmit={submitResolve} style={box} aria-labelledby="concern-resolve">
          <h2 id="concern-resolve" style={{ margin: 0 }}>{t("safeguarding.console.detail.resolveHeading")}</h2>
          <label htmlFor={outcomeId}>{t("safeguarding.console.detail.outcomeLabel")}</label>
          <select id={outcomeId} required value={outcome} onChange={(e) => setOutcome(e.target.value as Outcome | "")} style={control}>
            <option value="">—</option>
            {outcomeOptions(concern.status).map((o) => (
              <option key={o} value={o}>
                {t(outcomeKey(o))}
              </option>
            ))}
          </select>
          <label htmlFor={closingId}>{t("safeguarding.console.detail.resolveNote")}</label>
          <textarea id={closingId} dir="auto" rows={2} maxLength={2000} value={closing} onChange={(e) => setClosing(e.target.value)} style={control} />
          <div>
            <Button type="submit" variant="primary" label={t("safeguarding.console.detail.resolve")} loading={busy} disabled={!outcome} />
          </div>
        </form>
      ) : null}

      <section style={box} aria-labelledby="concern-audit">
        <h2 id="concern-audit" style={{ margin: 0 }}>{t("safeguarding.console.detail.audit")}</h2>
        <ol style={{ margin: 0, paddingInlineStart: "var(--space-4)" }}>
          {concern.audit.map((a, i) => (
            <li key={`${a.at}-${i}`}>
              <bdi dir="ltr">
                {a.action} · {a.actor_role} {a.actor_ref}
              </bdi>{" "}
              · {formatDateTime(a.at, locale)}
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
