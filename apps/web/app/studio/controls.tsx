// Small studio form controls (token-only styling, real labels, ≥44px targets).
import type { ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

const control = {
  minHeight: "var(--size-touch-min)",
  padding: "var(--space-2) var(--space-3)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-focus-ring)",
  background: "var(--color-bg-canvas)",
  color: "var(--color-text-primary)",
  font: "inherit",
} as const;

export function SelectField({
  id,
  label,
  error,
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { id: string; label: string; error?: string; children: ReactNode }) {
  return (
    <div style={{ display: "grid", gap: "var(--space-1)" }}>
      <label htmlFor={id}>{label}</label>
      <select
        {...rest}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        style={control}
      >
        {children}
      </select>
      {error ? (
        <span id={`${id}-error`} role="alert" style={{ color: "var(--color-danger)" }}>
          {error}
        </span>
      ) : null}
    </div>
  );
}

export function TextAreaField({
  id,
  label,
  hint,
  error,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { id: string; label: string; hint?: string; error?: string }) {
  const described = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean).join(" ");
  return (
    <div style={{ display: "grid", gap: "var(--space-1)" }}>
      <label htmlFor={id}>{label}</label>
      {hint ? <span id={`${id}-hint`}>{hint}</span> : null}
      <textarea
        {...rest}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={described || undefined}
        style={{ ...control, minHeight: 88, width: "100%", boxSizing: "border-box" }}
      />
      {error ? (
        <span id={`${id}-error`} role="alert" style={{ color: "var(--color-danger)" }}>
          {error}
        </span>
      ) : null}
    </div>
  );
}

/** The prominent provisional banner. Text + shape, never colour alone. */
export function ProvisionalBadge({ label }: { label: string }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--space-1)",
        padding: "var(--space-1) var(--space-2)",
        borderRadius: "var(--radius-md)",
        background: "var(--color-reward-fill)",
        color: "var(--color-on-reward)",
        fontWeight: 700,
      }}
    >
      <span aria-hidden="true">⚠</span>
      <span>{label}</span>
    </span>
  );
}
