// Curriculum Studio: the internal authoring and review tool, separate from the student PWA. The
// chrome follows the interface locale (StudioShell); lesson content inside keeps its own lang/dir.
import type { ReactNode } from "react";

import { StudioShell } from "./StudioShell";

export const metadata = {
  title: "Curriculum Studio",
  description: "Internal curriculum authoring and review — no child data.",
};

export default function StudioLayout({ children }: { children: ReactNode }) {
  return <StudioShell>{children}</StudioShell>;
}
