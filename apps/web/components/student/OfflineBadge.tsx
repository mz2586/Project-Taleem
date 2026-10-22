"use client";
// Persistent, calm sync indicator: one line from lib/student/syncView.ts (saved on this phone /
// sending / sent / waiting for a grown-up). Never alarming; the learner is never blocked or
// scolded for being offline, and held work is never called lost. Presentational — the live data
// comes from SyncStatusBadge. The text is a polite live region so a change is announced.
import { useLocale } from "../../lib/i18n/useLocale";
import type { SyncView } from "../../lib/student/syncView";

const TONE_COLOR: Record<SyncView["tone"], string> = {
  calm: "var(--color-text-primary)",
  busy: "var(--color-action-primary)",
  attention: "var(--color-danger)",
};

export function OfflineBadge({ view }: { view: SyncView }) {
  const { t } = useLocale();
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--space-1)",
        fontSize: "var(--font-size-body-min)",
        color: TONE_COLOR[view.tone],
      }}
    >
      {/* The symbol is decoration; the words carry the state (never colour or shape alone). */}
      <span aria-hidden="true">{view.symbol}</span>
      <span aria-live="polite">{t(view.headline.key, view.headline.params)}</span>
    </span>
  );
}
