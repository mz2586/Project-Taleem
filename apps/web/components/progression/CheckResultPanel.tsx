// The finish screen of a unit check (§2): score, pass or "not yet", the per-idea breakdown and
// what to practise next — encouraging, never shaming, and always labelled "Taleem unit check — not
// a certificate". Presentational and server-safe; the words are lib/progression/view.ts `resultView`.
import { ButtonLink } from "@/design-system/ButtonLink";
import type { Translator } from "@/lib/i18n/translate";
import type { ResultView } from "@/lib/progression/view";

import { ClaimLine, LocalText } from "./parts";

export function CheckResultPanel({ view, t }: { view: ResultView; t: Translator }) {
  return (
    <section aria-labelledby="check-result" data-outcome={view.outcome} style={{ display: "grid", gap: "var(--space-4)", minWidth: 0 }}>
      <div
        style={{
          display: "grid",
          gap: "var(--space-2)",
          padding: "var(--space-4)",
          border: view.outcome === "passed" ? "3px solid var(--color-brand)" : "2px solid var(--color-action-primary)",
          borderRadius: "var(--radius-md)",
          textAlign: "center",
          justifyItems: "center",
        }}
      >
        <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t("progression.result.title")}</p>
        <h2 id="check-result" style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
          <span aria-hidden="true">{view.outcome === "passed" ? "★ " : "🌱 "}</span>
          {view.title}
        </h2>
        <p style={{ margin: 0, fontWeight: 700 }}>{view.score}</p>
        <p style={{ margin: 0 }}>{view.passMark}</p>
        <p style={{ margin: 0 }}>{view.body}</p>
      </div>

      {view.breakdown.length > 0 ? (
        <section aria-labelledby="check-breakdown" style={{ display: "grid", gap: "var(--space-2)" }}>
          <h3 id="check-breakdown" style={{ margin: 0 }}>
            {t("progression.result.breakdownTitle")}
          </h3>
          <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)", display: "grid", gap: "var(--space-1)" }}>
            {view.breakdown.map((row, i) => (
              <li key={row.code || i}>
                <LocalText value={row.title} />
                {" — "}
                <span>
                  <span aria-hidden="true">{row.allRight ? "✓ " : "◐ "}</span>
                  {row.line}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {view.remediation.length > 0 ? (
        <section aria-labelledby="check-remediation" style={{ display: "grid", gap: "var(--space-2)" }}>
          <h3 id="check-remediation" style={{ margin: 0 }}>
            {t("progression.result.remediationTitle")}
          </h3>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-2)" }}>
            {view.remediation.map((r, i) => (
              <li key={r.code || i} style={{ display: "grid", gap: "var(--space-1)", justifyItems: "start" }}>
                <strong>
                  <LocalText value={r.title} />
                </strong>
                <ButtonLink href={r.href} variant="primary" label={r.action} icon={<span aria-hidden="true">▶</span>} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {view.retake ? <p style={{ margin: 0 }}>{view.retake}</p> : null}
      <ClaimLine text={view.claim} />
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
        <ButtonLink href="/student/subjects" variant="ghost" label={t("progression.check.backToLearn")} />
        <ButtonLink href="/student/record" variant="ghost" label={t("progression.result.viewRecord")} />
      </div>
    </section>
  );
}
