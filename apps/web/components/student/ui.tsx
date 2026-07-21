// Presentational student-portal primitives (no hooks -> server-safe). Token-only styling, RTL-first,
// WCAG 2.2 AA: state is conveyed by label + shape + text, never colour alone.
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

// Circular progress with a MANDATORY text percentage (never colour-only).
export function ProgressRing({ value, label }: { value: number; label: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const size = 72;
  const stroke = 8;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div role="img" aria-label={`${label}: ${pct}%`} style={{ display: "inline-flex", flexDirection: "column", alignItems: "center", gap: "var(--space-1)" }}>
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
      <strong>{pct}%</strong>
      <span style={{ fontSize: "var(--font-size-body-min)" }}>{label}</span>
    </div>
  );
}

// Mastery state -> label + symbol + tone. Symbol distinguishes states without relying on colour.
const STATE_META: Record<string, { label: string; symbol: string; tone: string }> = {
  not_started: { label: "Not started", symbol: "○", tone: "var(--color-text-primary)" },
  in_progress: { label: "Learning", symbol: "◐", tone: "var(--color-action-primary)" },
  mastered: { label: "Mastered", symbol: "●", tone: "var(--color-brand)" },
  needs_review: { label: "Review soon", symbol: "◑", tone: "var(--color-action-primary)" },
  at_risk: { label: "Needs review", symbol: "◔", tone: "var(--color-danger)" },
};

export function StateBadge({ state }: { state: string }) {
  const meta = STATE_META[state] ?? STATE_META["not_started"]!;
  return (
    <span
      style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-1)", color: meta.tone }}
      aria-label={meta.label}
    >
      <span aria-hidden="true">{meta.symbol}</span>
      <span>{meta.label}</span>
    </span>
  );
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div aria-busy="true" aria-live="polite" style={{ display: "grid", gap: "var(--space-2)" }}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          style={{ height: "var(--space-6)", background: "var(--color-focus-ring)", opacity: 0.15, borderRadius: "var(--radius-md)" }}
        />
      ))}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <section style={{ display: "grid", gap: "var(--space-2)", padding: "var(--space-6) var(--space-4)", textAlign: "center" }}>
      <strong style={{ fontSize: "var(--font-size-body-min-urdu)" }}>{title}</strong>
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
