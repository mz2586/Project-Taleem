// Under a card: "Print or save as PDF" for everyone, and — for a guardian, on a current card — the
// one-time "I have seen this". Presentational: state comes from lib/reporting/view.ts `ackReducer`.
// Buttons are left off the printed page; the "seen on" line is kept (it is part of the record).
import type { Ref } from "react";

import { FormError, FormNotice } from "@/components/form";
import { Button } from "@/design-system/Button";
import type { Translator } from "@/lib/i18n/translate";
import { canAcknowledge, type AckState } from "@/lib/reporting/view";

export function ReportCardActions({
  t,
  ack,
  seenDate,
  onAcknowledge,
  onPrint,
  statusRef,
}: {
  t: Translator;
  /** Absent: no acknowledge (a learner, a superseded card). */
  ack?: AckState | null;
  /** The acknowledged time, already formatted for the locale. */
  seenDate?: string | null;
  onAcknowledge?: () => void;
  onPrint: () => void;
  /** Focus lands here after acknowledging, so the result is read out. */
  statusRef?: Ref<HTMLDivElement>;
}) {
  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }}>
      {ack ? (
        <div ref={statusRef} tabIndex={-1} style={{ display: "grid", gap: "var(--space-2)" }}>
          {ack.status === "seen" ? (
            <>
              {ack.justNow ? <FormNotice message={t("common.reportCard.ackDone")} /> : null}
              {seenDate ? (
                <p style={{ margin: 0 }}>
                  <span aria-hidden="true">✓ </span>
                  {t("common.reportCard.seenOn", { date: seenDate })}
                </p>
              ) : null}
            </>
          ) : null}
          {ack.status === "failed" ? <FormError message={t(ack.error)} /> : null}
          {canAcknowledge(ack) || ack.status === "sending" ? (
            <div data-print="hide" style={{ display: "grid", gap: "var(--space-1)", justifyItems: "start" }}>
              <p id="ack-hint" style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>
                {t("common.reportCard.ackHint")}
              </p>
              <Button
                variant="brand"
                icon={<span aria-hidden="true">👁</span>}
                label={t("common.reportCard.acknowledge")}
                loading={ack.status === "sending"}
                aria-describedby="ack-hint"
                onClick={onAcknowledge}
              />
            </div>
          ) : null}
        </div>
      ) : null}
      <div data-print="hide" style={{ display: "grid", gap: "var(--space-1)", justifyItems: "start" }}>
        <Button variant="ghost" icon={<span aria-hidden="true">🖨</span>} label={t("common.reportCard.print")} onClick={onPrint} />
        <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t("common.reportCard.printHint")}</p>
      </div>
    </div>
  );
}
