// Button — design-system primitive. Token-only styling; all interaction states; ≥44px target.
// Icon+text (never icon-only) for low-literacy access (docs/19-component-library.md §2).
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "brand" | "danger" | "ghost";

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
      style={{
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
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.6 : 1,
      }}
    >
      {icon}
      <span>{loading ? "…" : label}</span>
    </button>
  );
}
