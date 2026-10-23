// Safeguarding console: the safeguarding lead's triage queue. Internal, staff sign-in only, and
// separate from the student PWA and the Curriculum Studio.
import type { ReactNode } from "react";

import { SafeguardingShell } from "./SafeguardingShell";

export const metadata = {
  title: "Safeguarding",
  description: "Safeguarding concern triage — restricted to safeguarding leads.",
  robots: { index: false, follow: false },
};

export default function SafeguardingLayout({ children }: { children: ReactNode }) {
  return <SafeguardingShell>{children}</SafeguardingShell>;
}
