// "Get a report" for a guardian (lib/reporting/generate.ts). Presentational — no hooks — so it
// renders to static markup in the node suite; the page owns the state and the request.
// Each choice is a real radio with a visible label AND the exact dates it means; the custom dates
// are the last, "advanced" choice and only show their two fields once chosen. An answer that is not
// a card (not eligible, wait, no internet…) is a titled message in plain words, read out politely.
import type { FormEvent } from "react";

import { TextField } from "@/components/form";
import { Button } from "@/design-system/Button";
import type { MessageKey } from "@/lib/i18n/messages";
import type { Translator } from "@/lib/i18n/translate";
import type { PeriodChoice, PeriodOption } from "@/lib/reporting/generate";
import type { PeriodInputs } from "@/lib/reporting/teacher";

const radioLabel = {
  display: "flex",
  alignItems: "flex-start",
  gap: "var(--space-2)",
  minHeight: "var(--size-touch-min)",
  cursor: "pointer",
} as const;

export interface GenerateMessage {
  title: string;
  body: string;
}

export function GenerateReport({
  t,
  options,
  choice,
  onChoice,
  custom,
  onCustom,
  problems = {},
  maxDate,
  busy,
  message,
  onSubmit,
}: {
  t: Translator;
  options: PeriodOption[];
  choice: PeriodChoice;
  onChoice: (choice: PeriodChoice) => void;
  custom: PeriodInputs;
  onCustom: (inputs: PeriodInputs) => void;
  problems?: { start?: MessageKey; end?: MessageKey };
  /** Today, as a date-input value: the last day cannot be later. */
  maxDate: string;
  busy: boolean;
  /** The last attempt's answer, when it was not a card to open. */
  message: GenerateMessage | null;
  onSubmit: (event: FormEvent) => void;
}) {
  const presetProblem = choice !== "custom" ? problems.start : undefined;
  return (
    <section
      aria-labelledby="generate-title"
      data-print="hide"
      style={{
        display: "grid",
        gap: "var(--space-3)",
        padding: "var(--space-4)",
        border: "1px solid var(--color-focus-ring)",
        borderRadius: "var(--radius-md)",
        minWidth: 0,
      }}
    >
      <h2 id="generate-title" style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
        {t("guardian.reportCards.generate.title")}
      </h2>
      <p style={{ margin: 0 }}>{t("guardian.reportCards.generate.intro")}</p>
      <form onSubmit={onSubmit} noValidate style={{ display: "grid", gap: "var(--space-3)", minWidth: 0 }}>
        <fieldset style={{ border: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-1)", minWidth: 0 }}>
          <legend style={{ padding: 0, fontWeight: 700 }}>{t("guardian.reportCards.generate.legend")}</legend>
          {options.map((o) => (
            <label key={o.choice} style={{ ...radioLabel, opacity: o.available ? 1 : 0.6 }}>
              <input
                type="radio"
                name="report-period"
                value={o.choice}
                checked={choice === o.choice}
                disabled={!o.available || busy}
                onChange={() => onChoice(o.choice)}
              />
              <span style={{ display: "grid" }}>
                <strong>{o.label}</strong>
                {o.dates ? <span style={{ fontSize: "var(--font-size-body-min)" }}>{o.dates}</span> : null}
              </span>
            </label>
          ))}
        </fieldset>
        {choice === "custom" ? (
          <div data-custom-dates="" style={{ display: "grid", gap: "var(--space-2)", minWidth: 0 }}>
            <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t("guardian.reportCards.generate.customHint")}</p>
            <TextField
              id="generate-start"
              type="date"
              label={t("teacher.reportCards.startLabel")}
              error={problems.start ? t(problems.start) : undefined}
              value={custom.start}
              max={maxDate}
              onChange={(e) => onCustom({ ...custom, start: e.target.value })}
              required
            />
            <TextField
              id="generate-end"
              type="date"
              label={t("teacher.reportCards.endLabel")}
              error={problems.end ? t(problems.end) : undefined}
              value={custom.end}
              max={maxDate}
              onChange={(e) => onCustom({ ...custom, end: e.target.value })}
              required
            />
          </div>
        ) : null}
        {presetProblem ? (
          <p role="alert" style={{ margin: 0, color: "var(--color-danger)" }}>
            {t(presetProblem)}
          </p>
        ) : null}
        <div>
          <Button
            type="submit"
            variant="primary"
            icon={<span aria-hidden="true">📄</span>}
            label={busy ? t("guardian.reportCards.generate.working") : t("guardian.reportCards.generate.submit")}
            loading={busy}
          />
        </div>
      </form>
      <div aria-live="polite">
        {message ? (
          <div
            data-generate-message=""
            style={{ display: "grid", gap: "var(--space-1)", padding: "var(--space-3)", border: "2px solid var(--color-focus-ring)", borderRadius: "var(--radius-md)" }}
          >
            <strong>
              <span aria-hidden="true">ⓘ </span>
              {message.title}
            </strong>
            <span>{message.body}</span>
          </div>
        ) : null}
      </div>
    </section>
  );
}
