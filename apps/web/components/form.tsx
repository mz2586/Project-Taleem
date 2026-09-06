// Form primitives shared by the sign-in, join, and consent screens.
//
// Accessibility decisions that are not defaults and are easy to lose:
//
// - Every input has a real `<label>` bound by id. Placeholders are not labels — they vanish on focus
//   and screen readers treat them inconsistently.
// - Errors are wired with `aria-describedby` and announced through `role="alert"`, so a person who
//   cannot see the red text still learns what went wrong.
// - `--font-size-body-min-urdu` (18px) is the floor. Urdu Nastaliq is unreadable below it, and these
//   are the screens a low-literacy parent has to get through.
// - Touch targets are `--size-touch-min` (44px), because these screens are used on a phone.

import type { InputHTMLAttributes, ReactNode } from "react";

const fieldStyle = {
  display: "grid",
  gap: "var(--space-1)",
} as const;

const inputStyle = {
  minHeight: "var(--size-touch-min)",
  padding: "var(--space-2) var(--space-3)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-focus-ring)",
  background: "var(--color-bg-canvas)",
  color: "var(--color-text-primary)",
  font: "inherit",
  fontSize: "var(--font-size-body-min-urdu)",
  width: "100%",
  boxSizing: "border-box" as const,
};

export function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div style={fieldStyle}>
      <label htmlFor={id} style={{ fontSize: "var(--font-size-body-min-urdu)" }}>
        {label}
      </label>
      {hint ? (
        <span id={`${id}-hint`} style={{ fontSize: "var(--font-size-body-min)", opacity: 0.85 }}>
          {hint}
        </span>
      ) : null}
      {children}
      {error ? (
        <span
          id={`${id}-error`}
          role="alert"
          style={{ color: "var(--color-danger)", fontSize: "var(--font-size-body-min)" }}
        >
          {error}
        </span>
      ) : null}
    </div>
  );
}

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  id: string;
  label: string;
  hint?: string;
  error?: string;
}

export function TextField({ id, label, hint, error, ...rest }: TextFieldProps) {
  const described = [hint ? `${id}-hint` : null, error ? `${id}-error` : null]
    .filter(Boolean)
    .join(" ");
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <input
        {...rest}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={described || undefined}
        style={inputStyle}
      />
    </Field>
  );
}

/**
 * A PIN entry.
 *
 * `inputMode="numeric"` raises the number pad on a phone without the spinner and scroll-to-change
 * misbehaviour of `type="number"`. `type="password"` keeps the digits off the screen, which matters
 * when a child types their PIN in a room with other children.
 */
export function PinField({ id, label, hint, error, ...rest }: TextFieldProps) {
  return (
    <TextField
      {...rest}
      id={id}
      label={label}
      hint={hint}
      error={error}
      type="password"
      inputMode="numeric"
      autoComplete="off"
      pattern="[0-9]*"
      maxLength={6}
      style={{ ...inputStyle, letterSpacing: "0.35em", textAlign: "center" }}
    />
  );
}

/** A page-level error. `role="alert"` so it is announced the moment it appears. */
export function FormError({ message }: { message: string }) {
  return (
    <p
      role="alert"
      style={{
        margin: 0,
        padding: "var(--space-3)",
        borderRadius: "var(--radius-md)",
        border: "1px solid var(--color-danger)",
        color: "var(--color-danger)",
        fontSize: "var(--font-size-body-min-urdu)",
      }}
    >
      {message}
    </p>
  );
}

/** A confirmation. Polite rather than assertive: success should not interrupt. */
export function FormNotice({ message }: { message: string }) {
  return (
    <p
      role="status"
      aria-live="polite"
      style={{
        margin: 0,
        padding: "var(--space-3)",
        borderRadius: "var(--radius-md)",
        border: "1px solid var(--color-brand)",
        color: "var(--color-brand)",
        fontSize: "var(--font-size-body-min-urdu)",
      }}
    >
      {message}
    </p>
  );
}

/** A centred single-purpose page, used by every unauthenticated screen. */
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main
      style={{
        maxWidth: 460,
        margin: "0 auto",
        padding: "var(--space-6) var(--space-4)",
        display: "grid",
        gap: "var(--space-4)",
        alignContent: "start",
        minHeight: "100vh",
      }}
    >
      <header style={{ display: "grid", gap: "var(--space-1)" }}>
        <h1 style={{ margin: 0, color: "var(--color-brand)" }}>{title}</h1>
        {subtitle ? <p style={{ margin: 0 }}>{subtitle}</p> : null}
      </header>
      {children}
      {footer ? <footer style={{ marginTop: "var(--space-4)" }}>{footer}</footer> : null}
    </main>
  );
}
