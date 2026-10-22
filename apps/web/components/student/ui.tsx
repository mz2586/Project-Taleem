// Presentational student-portal primitives (no hooks -> server-safe). Token-only styling, RTL-first,
// WCAG 2.2 AA: state is conveyed by label + shape + text, never colour alone.
//
// No visible copy is hard-coded here: callers pass translated strings (see lib/i18n). Optional props
// keep these signatures compatible with the guardian pages that share them.
import type { ReactNode } from "react";

export function Card({
  children,
  onPress,
  ariaLabel,
}: {
  children: ReactNode;
  onPress?: () => void;
  ariaLabel?: string;
}) {
  const style = {
    display: "block",
    width: "100%",
    textAlign: "start" as const,
    background: "var(--color-bg-canvas)",
    color: "var(--color-text-primary)",
    border: "1px solid var(--color-focus-ring)",
    borderRadius: "var(--radius-md)",
    padding: "var(--space-4)",
    font: "inherit",
  };
  if (onPress) {
    return (
      <button type="button" onClick={onPress} aria-label={ariaLabel} style={{ ...style, cursor: "pointer" }}>
        {children}
      </button>
    );
  }
  return <section style={style}>{children}</section>;
}

// Circular progress with a MANDATORY text percentage (never colour-only). `formatPercent` lets the
// caller render the number in the interface locale; without it, a plain "NN%".
export function ProgressRing({
  value,
  label,
  formatPercent,
}: {
  value: number;
  label: string;
  formatPercent?: (ratio: number) => string;
}) {
  const ratio = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
  const pct = Math.round(ratio * 100);
  const text = formatPercent ? formatPercent(ratio) : `${pct}%`;
  const size = 72;
  const stroke = 8;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div role="img" aria-label={`${label}: ${text}`} style={{ display: "inline-flex", flexDirection: "column", alignItems: "center", gap: "var(--space-1)" }}>
      <svg width={size} height={size} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-focus-ring)" strokeOpacity={0.2} strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--color-brand)"
          strokeWidth={stroke}
          strokeDasharray={c}
          strokeDashoffset={c * (1 - pct / 100)}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <strong aria-hidden="true">{text}</strong>
      <span aria-hidden="true" style={{ fontSize: "var(--font-size-body-min)" }}>{label}</span>
    </div>
  );
}

// Mastery state -> symbol + tone. The symbol distinguishes states without relying on colour; the
// label is the caller's translated text (lib/student/journey.ts `masteryStateKey`).
const STATE_META: Record<string, { symbol: string; tone: string }> = {
  not_started: { symbol: "○", tone: "var(--color-text-primary)" },
  in_progress: { symbol: "◐", tone: "var(--color-action-primary)" },
  mastered: { symbol: "●", tone: "var(--color-brand)" },
  needs_review: { symbol: "◑", tone: "var(--color-action-primary)" },
  at_risk: { symbol: "◔", tone: "var(--color-danger)" },
};

export function StateBadge({ state, label }: { state: string; label: string }) {
  const meta = STATE_META[state] ?? STATE_META["not_started"]!;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-1)", color: meta.tone }}>
      <span aria-hidden="true">{meta.symbol}</span>
      <span>{label}</span>
    </span>
  );
}

// A loading placeholder. `label` is announced to assistive technology (the bars are decorative).
export function Skeleton({ lines = 3, label }: { lines?: number; label?: string }) {
  return (
    <div role="status" aria-busy="true" aria-live="polite" style={{ display: "grid", gap: "var(--space-2)" }}>
      {label ? <span className="visually-hidden">{label}</span> : null}
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          aria-hidden="true"
          style={{ height: "var(--space-6)", background: "var(--color-focus-ring)", opacity: 0.15, borderRadius: "var(--radius-md)" }}
        />
      ))}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <section style={{ display: "grid", gap: "var(--space-2)", padding: "var(--space-6) var(--space-4)", textAlign: "center", justifyItems: "center" }}>
      <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{title}</h2>
      <p style={{ margin: 0 }}>{body}</p>
      {action}
    </section>
  );
}

export function ErrorBanner({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div
      role="alert"
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "var(--space-3)",
        alignItems: "center",
        justifyContent: "space-between",
        background: "var(--color-danger)",
        color: "var(--color-on-danger)",
        padding: "var(--space-3) var(--space-4)",
        borderRadius: "var(--radius-md)",
      }}
    >
      <span>{message}</span>
      {action}
    </div>
  );
}
