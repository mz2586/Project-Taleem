"use client";
// The explained recommendations for a teacher or guardian: what is recommended, why (each reason
// in the reader's language), how sure the AI teacher is, and the answers behind it. The words come
// from lib/learning/rationale.ts (pure, tested); this only lays them out. Curriculum codes keep their
// own direction inside the interface text.
import { contentAttrs } from "@/lib/i18n/content";
import { useLocale } from "@/lib/i18n/useLocale";
import type { RecommendationView } from "@/lib/learning/rationale";

export function RecommendationList({ items, empty }: { items: RecommendationView[]; empty: string }) {
  const { t } = useLocale();
  if (items.length === 0) return <p style={{ margin: 0 }}>{empty}</p>;
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-3)" }}>
      {items.map((rec, i) => (
        <li
          key={`${rec.objective ?? "none"}-${i}`}
          style={{ display: "grid", gap: "var(--space-1)", paddingBottom: "var(--space-2)", borderBottom: "1px solid var(--color-focus-ring)" }}
        >
          <strong>
            {rec.isNext ? `${t("common.rationale.nextLabel")}: ` : null}
            {t(rec.kind)}
            {rec.objective ? (
              <>
                {" · "}
                <bdi {...contentAttrs({ text: rec.objective })}>{rec.objective}</bdi>
              </>
            ) : null}
          </strong>
          {rec.reasons.length > 0 ? (
            <>
              <span>{t("common.rationale.whyLabel")}</span>
              <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)" }}>
                {rec.reasons.map((r, j) => (
                  <li key={`${r.key}-${j}`}>{t(r.key, r.params)}</li>
                ))}
              </ul>
            </>
          ) : null}
          <span style={{ fontSize: "var(--font-size-body-min)" }}>
            {t(rec.confidence)}
            {rec.uncertainty ? ` · ${t(rec.uncertainty.key, rec.uncertainty.params)}` : null}
          </span>
          <span style={{ fontSize: "var(--font-size-body-min)" }}>
            {t(rec.evidence.key, rec.evidence.params)} {t(rec.source)}
          </span>
        </li>
      ))}
    </ul>
  );
}
