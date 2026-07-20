// Root layout — Urdu-first, RTL by default (docs/16, 17). No child data.
import type { ReactNode } from "react";
import "../design-system/tokens.css";

export const metadata = {
  title: "Taleem",
  description: "A real school for every child.",
  manifest: "/manifest.webmanifest",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ur" dir="rtl">
      <body
        style={{
          margin: 0,
          background: "var(--color-bg-canvas)",
          color: "var(--color-text-primary)",
          fontFamily: "var(--font-body)",
          fontSize: "var(--font-size-body-min-urdu)",
        }}
      >
        {children}
      </body>
    </html>
  );
}
