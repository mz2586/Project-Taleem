// Button — design-system primitive. Token-only styling; all interaction states; ≥44px target.
// Icon+text (never icon-only) for low-literacy access (docs/19-component-library.md §2).
import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";

export type Variant = "primary" | "brand" | "danger" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  icon?: ReactNode;
  label: string; // always visible text — no icon-only buttons
  loading?: boolean;
}

const BG: Record<Variant, string> = {
  primary: "var(--color-action-primary)",
  brand: "var(--color-brand)",
  danger: "var(--color-danger)",
  ghost: "transparent",
};

const FG: Record<Variant, string> = {
  primary: "var(--color-on-action)",
  brand: "var(--color-on-brand)",
  danger: "var(--color-on-danger)",
  ghost: "var(--color-text-primary)",
};

/** The visual style of a button, shared with `ButtonLink` so a link that acts as a button looks like one. */
export function buttonStyle(variant: Variant, disabled = false): CSSProperties {
  return {
    minHeight: "var(--size-touch-min)",
    minWidth: "var(--size-touch-min)",
    display: "inline-flex",
    alignItems: "center",
    gap: "var(--space-2)",
    padding: "var(--space-2) var(--space-4)",
    borderRadius: "var(--radius-md)",
    background: BG[variant],
    color: FG[variant],
    border: variant === "ghost" ? "1px solid var(--color-focus-ring)" : "none",
    font: "inherit",
    textDecoration: "none",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.6 : 1,
  };
}

export function Button({
  variant = "primary",
  icon,
  label,
  loading = false,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading}
      aria-label={label}
      style={buttonStyle(variant, disabled)}
    >
      {icon}
      <span>{loading ? "…" : label}</span>
    </button>
  );
}
