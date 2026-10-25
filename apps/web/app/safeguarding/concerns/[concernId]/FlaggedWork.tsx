"use client";
// "What the child wrote": the homework answer a concern points to (a disclosure-screen or teacher
// concern names a submission). Never auto-loaded: the lead presses a button, and every read is an
// audited server-side event (concern.context_viewed — who, when, which concern; never the text).
import { useId, useState } from "react";

import { Button } from "@/design-system/Button";
import { formatDateTime } from "@/lib/guardian/format";
import type { Locale } from "@/lib/i18n/config";
import type { MessageKey } from "@/lib/i18n/messages";
import type { Translator } from "@/lib/i18n/translate";
import {
  flaggedWorkErrorKey,
  flaggedWorkView,
  type ConcernContextWire,
  type FlaggedWorkView,
} from "@/lib/safeguarding/triage";

type T = Translator;

const box = {
  border: "2px solid var(--color-danger)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-3)",
  display: "grid",
  gap: "var(--space-2)",
} as const;

/** The loaded answer. Pure presentation (rendered to static markup in the node test suite). */
export function FlaggedWorkBody({ view, t, locale }: { view: FlaggedWorkView; t: T; locale: Locale }) {
  return (
    <div style={{ display: "grid", gap: "var(--space-2)" }}>
      {view.resubmitted ? (
        <p role="note" style={{ margin: 0, fontWeight: 600 }}>
          {t("safeguarding.console.detail.flagged.resubmitted")}
        </p>
      ) : null}
      <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "max-content 1fr", gap: "var(--space-1) var(--space-3)" }}>
        <dt>{t("safeguarding.console.detail.flagged.lesson")}</dt>
        <dd dir="auto" style={{ margin: 0 }}>
          {view.lessonTitle ?? t("safeguarding.console.detail.flagged.unknown")}
        </dd>
        <dt>{t("safeguarding.console.detail.flagged.prompt")}</dt>
        <dd dir="auto" style={{ margin: 0 }}>
          {view.prompt ?? t("safeguarding.console.detail.flagged.unknown")}
        </dd>
        <dt>{t("safeguarding.console.detail.flagged.submittedAt")}</dt>
        <dd style={{ margin: 0 }}>
          {formatDateTime(view.submittedAt, locale)} · {t("safeguarding.console.detail.flagged.attempt", { n: view.attempt })}
        </dd>
      </dl>
      <h3 style={{ margin: 0 }}>{t("safeguarding.console.detail.flagged.answer")}</h3>
      <blockquote dir="auto" style={{ margin: 0, whiteSpace: "pre-wrap", paddingInlineStart: "var(--space-3)", borderInlineStart: "4px solid var(--color-danger)" }}>
        {view.text}
      </blockquote>
      <h3 style={{ margin: 0 }}>{t("safeguarding.console.detail.flagged.matched")}</h3>
      {view.matched.length === 0 ? (
        <p style={{ margin: 0 }}>{t("safeguarding.console.detail.flagged.noMatch")}</p>
      ) : (
        <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)" }}>
          {view.matched.map((m) => (
            <li key={m.id}>
              <bdi dir="ltr">{m.id}</bdi> · <span lang={m.lang || undefined} dir="auto">{m.phrase}</span>
            </li>
          ))}
        </ul>
      )}
      <p role="status" style={{ margin: 0 }}>
        {t("safeguarding.console.detail.flagged.readRecorded")}
      </p>
    </div>
  );
}

export function FlaggedWork({
  concernId,
  t,
  locale,
  read,
  onRead,
}: {
  concernId: string;
  t: T;
  locale: Locale;
  read: (concernId: string) => Promise<ConcernContextWire>;
  onRead?: () => void;
}) {
  const headingId = useId();
  const [view, setView] = useState<FlaggedWorkView | null>(null);
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);

  async function open() {
    setBusy(true);
    setError(null);
    try {
      setView(flaggedWorkView(await read(concernId), locale));
      onRead?.();
    } catch (e) {
      setError(flaggedWorkErrorKey(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={box} aria-labelledby={headingId}>
      <h2 id={headingId} style={{ margin: 0 }}>
        {t("safeguarding.console.detail.flagged.heading")}
      </h2>
      <p style={{ margin: 0 }}>{t("safeguarding.console.detail.flagged.intro")}</p>
      <p style={{ margin: 0 }}>
        <strong>{t("safeguarding.console.detail.flagged.recorded")}</strong>
      </p>
      <div aria-live="polite">
        {error ? (
          <p role="alert" style={{ margin: 0, color: "var(--color-danger)" }}>
            {t(error)}
          </p>
        ) : null}
        {busy && !view ? <p role="status">{t("safeguarding.console.detail.flagged.loading")}</p> : null}
      </div>
      {view ? (
        <FlaggedWorkBody view={view} t={t} locale={locale} />
      ) : (
        <div>
          <Button variant="primary" label={t("safeguarding.console.detail.flagged.show")} loading={busy} onClick={() => void open()} />
        </div>
      )}
    </section>
  );
}
