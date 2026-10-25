"use client";
// The one screen on which a guardian ever sees their recovery codes (after registration, and after
// "make new codes" in Family settings). The server keeps only digests, so the instructions are
// explicit that this is the only chance, and the guardian must tick "I have saved them" before
// moving on. Copy puts a plain-text sheet on the clipboard; Print prints only the sheet (the rest of
// the page is hidden by the print stylesheet below).
//
// Takes `t` rather than calling useLocale(), so the node test suite can render it to static markup.
import { useId, useState } from "react";

import { FormNotice } from "@/components/form";
import { Button } from "@/design-system/Button";
import { recoverySheetText } from "@/lib/guardian/recovery";
import type { Translator } from "@/lib/i18n/translate";

const PRINT_CSS = `@media print {
  body * { visibility: hidden !important; }
  [data-recovery-sheet], [data-recovery-sheet] * { visibility: visible !important; }
  [data-recovery-sheet] { position: absolute; inset: 0; padding: 24px; }
  [data-recovery-sheet] [data-screen-only] { display: none !important; }
}`;

export interface RecoveryCodesPanelProps {
  codes: readonly string[];
  t: Translator;
  /** The account the codes belong to, printed on the sheet. */
  email?: string;
  /** Already formatted for the guardian's locale. */
  madeAt?: string;
  /** Shown once the guardian confirms they saved the codes. */
  doneLabel: string;
  onDone: () => void;
}

export function RecoveryCodesPanel({ codes, t, email, madeAt, doneLabel, onDone }: RecoveryCodesPanelProps) {
  const headingId = useId();
  const listId = useId();
  const ackId = useId();
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState<"yes" | "failed" | null>(null);

  async function copy() {
    try {
      await navigator.clipboard.writeText(recoverySheetText(codes, t, { email, madeAt }));
      setCopied("yes");
    } catch {
      setCopied("failed");
    }
  }

  return (
    <section
      data-recovery-sheet=""
      aria-labelledby={headingId}
      style={{
        border: "2px solid var(--color-brand)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-4)",
        display: "grid",
        gap: "var(--space-3)",
      }}
    >
      <style>{PRINT_CSS}</style>
      <h2 id={headingId} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
        {t("guardian.recovery.sheetTitle")}
      </h2>
      <p role="note" style={{ margin: 0 }}>
        <strong>{t("guardian.recovery.instructionsOnce")}</strong>
      </p>
      <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)", display: "grid", gap: "var(--space-1)" }}>
        <li>{t("guardian.recovery.instructionsUse")}</li>
        <li>{t("guardian.recovery.instructionsSafe")}</li>
        <li>{t("guardian.recovery.instructionsNew")}</li>
      </ul>
      <ol
        id={listId}
        aria-label={t("guardian.recovery.listLabel")}
        // LTR + Latin: the codes are Latin letters and digits whose groups must read in order.
        dir="ltr"
        lang="en"
        style={{
          margin: 0,
          paddingInlineStart: "var(--space-6, 2.5rem)",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(11rem, 1fr))",
          gap: "var(--space-2)",
          fontFamily: "var(--font-mono, ui-monospace, monospace)",
          fontSize: "20px",
          letterSpacing: "0.08em",
        }}
      >
        {codes.map((code) => (
          <li key={code}>
            <code>{code}</code>
          </li>
        ))}
      </ol>
      {email ? <p style={{ margin: 0 }}>{t("guardian.recovery.sheetEmail", { email })}</p> : null}
      {madeAt ? <p style={{ margin: 0 }}>{t("guardian.recovery.sheetMadeAt", { date: madeAt })}</p> : null}

      <div data-screen-only="" style={{ display: "grid", gap: "var(--space-3)" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
          <Button type="button" variant="ghost" label={t("guardian.recovery.copy")} aria-controls={listId} onClick={() => void copy()} />
          <Button type="button" variant="ghost" label={t("guardian.recovery.print")} onClick={() => window.print()} />
        </div>
        <div aria-live="polite">
          {copied === "yes" ? <FormNotice message={t("guardian.recovery.copied")} /> : null}
          {copied === "failed" ? <FormNotice message={t("guardian.recovery.copyFailed")} /> : null}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", minHeight: "var(--size-touch-min)" }}>
          <input id={ackId} type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} />
          <label htmlFor={ackId}>{t("guardian.recovery.ack")}</label>
        </div>
        <div>
          <Button type="button" variant="brand" label={doneLabel} disabled={!saved} aria-describedby={saved ? undefined : `${ackId}-why`} onClick={onDone} />
          {saved ? null : (
            <span id={`${ackId}-why`} style={{ display: "block", fontSize: "var(--font-size-body-min)" }}>
              {t("guardian.recovery.ackFirst")}
            </span>
          )}
        </div>
      </div>
    </section>
  );
}
