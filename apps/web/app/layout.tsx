// Root layout. No child data.
//
// `lang`/`dir` come from the interface locale, not a literal. The server renders the deployment
// default (NEXT_PUBLIC_DEFAULT_LOCALE, else Urdu — so the SSR default is still `ur`/`rtl`), and
// `HtmlLocaleSync` corrects them after mount once the person's own choice is known.
import type { ReactNode } from "react";
import "../design-system/tokens.css";
import "../design-system/a11y.css";
import "../design-system/fonts.css";
import { ServiceWorkerRegister } from "../components/ServiceWorkerRegister";
import { defaultLocale, directionOf } from "../lib/i18n/config";
import { HtmlLocaleSync } from "../lib/i18n/HtmlLocaleSync";

export const metadata = {
  title: "Taleem",
  description: "A real school for every child.",
  manifest: "/manifest.webmanifest",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  const locale = defaultLocale();
  return (
    <html lang={locale} dir={directionOf(locale)}>
      <body
        style={{
          margin: 0,
          background: "var(--color-bg-canvas)",
          color: "var(--color-text-primary)",
          fontFamily: "var(--font-body)",
          fontSize: "var(--font-size-body-min-urdu)",
        }}
      >
        <HtmlLocaleSync />
        <ServiceWorkerRegister />
        {children}
      </body>
    </html>
  );
}
