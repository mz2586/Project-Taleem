// A learner's report cards, newest first (lib/reporting/view.ts `cardListView`). Presentational.
// Each row is one link named by its dates; a replaced card says so in words (and a ⚠ shape), and —
// for a guardian — whether they have marked it as seen.
import Link from "next/link";

import type { CardListItem } from "@/lib/reporting/view";

export function ReportCardList({
  items,
  hrefFor,
  label,
  newestLabel,
  supersededLabel,
  seenLabels,
  unverifiedLabel,
}: {
  items: CardListItem[];
  hrefFor: (cardId: string) => string;
  label: string;
  newestLabel: string;
  supersededLabel: string;
  /** Guardian only: [seen, not seen]. */
  seenLabels?: [string, string];
  /** Shown on a card that failed the server's hash re-check. */
  unverifiedLabel?: string;
}) {
  const newest = items.find((i) => !i.superseded)?.cardId ?? null;
  return (
    <ul aria-label={label} style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-2)" }}>
      {items.map((item) => (
        <li
          key={item.cardId}
          data-superseded={item.superseded ? "" : undefined}
          style={{
            display: "grid",
            gap: "var(--space-1)",
            padding: "var(--space-3)",
            border: item.superseded ? "1px dashed var(--color-focus-ring)" : "1px solid var(--color-focus-ring)",
            borderRadius: "var(--radius-md)",
            minWidth: 0,
          }}
        >
          <Link
            href={hrefFor(item.cardId)}
            style={{
              color: "var(--color-action-primary)",
              display: "inline-flex",
              alignItems: "center",
              minHeight: "var(--size-touch-min)",
              fontWeight: 700,
              textDecoration: item.superseded ? "line-through" : "underline",
            }}
          >
            {item.period}
          </Link>
          {item.issued ? <span style={{ fontSize: "var(--font-size-body-min)" }}>{item.issued}</span> : null}
          <span style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)", fontSize: "var(--font-size-body-min)" }}>
            {item.cardId === newest ? (
              <span>
                <span aria-hidden="true">★ </span>
                {newestLabel}
              </span>
            ) : null}
            {item.superseded ? (
              <span>
                <span aria-hidden="true">⚠ </span>
                {supersededLabel}
              </span>
            ) : null}
            {item.unverified && unverifiedLabel ? (
              <strong data-integrity="failed">
                <span aria-hidden="true">⚠ </span>
                {unverifiedLabel}
              </strong>
            ) : null}
            {seenLabels && !item.superseded ? (
              <span>
                <span aria-hidden="true">{item.seen ? "✓ " : "○ "}</span>
                {item.seen ? seenLabels[0] : seenLabels[1]}
              </span>
            ) : null}
          </span>
        </li>
      ))}
    </ul>
  );
}
