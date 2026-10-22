// ButtonLink — navigation that looks like a Button. Additive design-system primitive.
//
// Replaces the `<Link><Button/></Link>` pattern, which nests a <button> inside an <a>: two
// interactive elements in one, announced twice by screen readers and with undefined keyboard
// behaviour. Navigation is a link; it just wears the button's style (same tokens, same ≥44px target).
import Link from "next/link";
import type { ReactNode } from "react";

import { buttonStyle, type Variant } from "./Button";

export function ButtonLink({
  href,
  label,
  icon,
  variant = "primary",
}: {
  href: string;
  label: string; // always visible text — no icon-only links
  icon?: ReactNode;
  variant?: Variant;
}) {
  return (
    <Link href={href} style={buttonStyle(variant)}>
      {icon}
      <span>{label}</span>
    </Link>
  );
}
