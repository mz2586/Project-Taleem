"use client";
// /studio/signin — staff passphrase sign-in for the Curriculum Studio. The studio layout's
// StudioShell renders the sign-in form for anyone signed out (on every studio route), so this page
// is only ever reached signed in: it forwards to the review queue.
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useLocale } from "@/lib/i18n/useLocale";

export default function StudioSignInPage() {
  const router = useRouter();
  const { t } = useLocale();
  useEffect(() => {
    router.replace("/studio");
  }, [router]);
  return (
    <p role="status" aria-busy="true">
      {t("common.loading")}
    </p>
  );
}
