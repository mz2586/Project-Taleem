"use client";
// Lessons on this phone — the offline library. Lists the published packages, saves one with
// progress, installs it ONLY after its Ed25519 signature and content hash verify (a package that
// fails is refused and nothing is written), shows the space used, and removes lessons. The rules
// are lib/student/offlineLibrary.ts, tested; this page renders `libraryModel`.
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/student/AppShell";
import { Card, EmptyState, ErrorBanner, Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { ButtonLink } from "@/design-system/ButtonLink";
import { contentAttrs } from "@/lib/i18n/content";
import { useLocale } from "@/lib/i18n/useLocale";
import { createStore } from "@/lib/offline/kv";
import { browserEstimate, requestPersistentStorage } from "@/lib/offline/packages";
import type { OfflineContent, StoredPackage } from "@/lib/offline/types";
import { withSession } from "@/lib/session/store";
import { useLearner } from "@/lib/session/useLearner";
import { offlineApi } from "@/lib/student/api";
import {
  classifyDownloadError,
  configuredSigningKeys,
  createLibrary,
  DOWNLOAD_FAILURE_COPY,
  formatBytes,
  libraryModel,
  type DownloadState,
  type LibraryEntry,
  type ListRequest,
  type OfflineLibrary,
} from "@/lib/student/offlineLibrary";

function buildLibrary(): OfflineLibrary {
  return createLibrary({
    store: createStore(),
    listPackages: () => withSession(() => offlineApi.listPackages()),
    fetchPackage: (id) => withSession(() => offlineApi.fetchPackage(id)),
    signingKeys: () => withSession(() => offlineApi.signingKeys()),
    configuredKeys: configuredSigningKeys(),
    estimate: browserEstimate,
  });
}

function EntryCard({
  entry,
  onSave,
  onRemove,
}: {
  entry: LibraryEntry;
  onSave: () => void;
  onRemove: () => void;
}) {
  const { t, locale, formatPercent } = useLocale();
  const s = entry.status;
  const installed = s.kind === "installed" || (s.kind === "failed" && s.installed);
  const heading = entry.title?.text ?? t("student.offline.lessonFallback", { code: entry.objectiveCode });
  return (
    <Card>
      <div style={{ display: "grid", gap: "var(--space-2)" }}>
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: "var(--space-2)" }}>
          <h2
            {...(entry.title ? contentAttrs({ locale: entry.title.locale, text: entry.title.text }) : {})}
            style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}
          >
            {heading}
          </h2>
          {installed ? (
            <span style={{ color: "var(--color-brand)" }}>
              <span aria-hidden="true">✓ </span>
              {t("student.offline.saved")}
            </span>
          ) : null}
        </div>
        <span style={{ fontSize: "var(--font-size-body-min)" }}>{t("student.offline.size", { size: formatBytes(entry.bytes, locale) })}</span>

        {s.kind === "downloading" ? (
          <div style={{ display: "grid", gap: "var(--space-1)" }}>
            <progress value={s.fraction} max={1} aria-label={t("student.offline.saving", { value: formatPercent(s.fraction) })} style={{ width: "100%" }} />
            <span>{t("student.offline.saving", { value: formatPercent(s.fraction) })}</span>
          </div>
        ) : null}
        {s.kind === "failed" ? <ErrorBanner message={t(DOWNLOAD_FAILURE_COPY[s.reason])} /> : null}
        {s.kind === "installed" && s.updateAvailable ? <p style={{ margin: 0 }}>{t("student.offline.updateAvailable")}</p> : null}

        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
          {installed ? (
            <ButtonLink href={`/student/offline/play?lesson=${encodeURIComponent(entry.lessonId)}`} variant="brand" label={t("student.offline.open")} />
          ) : null}
          {s.kind === "available" ? <Button variant="brand" label={t("student.offline.save")} onClick={onSave} /> : null}
          {s.kind === "failed" ? <Button variant="ghost" label={t("student.offline.tryAgain")} onClick={onSave} /> : null}
          {s.kind === "installed" && s.updateAvailable ? <Button variant="primary" label={t("student.offline.update")} onClick={onSave} /> : null}
          {installed ? <Button variant="ghost" label={t("student.offline.remove")} onClick={onRemove} /> : null}
        </div>
      </div>
    </Card>
  );
}

export default function OfflineLibraryPage() {
  const { band } = useLearner();
  const { t, locale } = useLocale();
  const router = useRouter();
  const library = useMemo(() => (typeof window === "undefined" ? null : buildLibrary()), []);
  const [list, setList] = useState<ListRequest>({ status: "pending" });
  const [installed, setInstalled] = useState<StoredPackage[] | null>(null);
  const [titles, setTitles] = useState<Record<string, OfflineContent["title"]>>({});
  const [downloads, setDownloads] = useState<Record<string, DownloadState>>({});
  const [free, setFree] = useState<number | null>(null);
  const [notice, setNotice] = useState("");

  const refreshLocal = useCallback(async () => {
    if (!library) return;
    const recs = await library.installed();
    setInstalled(recs);
    setTitles(await library.titles(recs.map((r) => r.lesson_id)));
    const est = await browserEstimate();
    setFree(est.quota > 0 ? Math.max(0, est.quota - est.usage) : null);
  }, [library]);

  const load = useCallback(async () => {
    if (!library) return;
    setList({ status: "pending" });
    await refreshLocal();
    try {
      setList({ status: "ok", manifests: await library.list() });
    } catch (error) {
      setList({ status: "error", error });
    }
  }, [library, refreshLocal]);

  useEffect(() => {
    void load();
    // Fetch the player's code now, while online, so it opens later without a network.
    router.prefetch("/student/offline/play");
  }, [load, router]);

  const save = async (lessonId: string) => {
    if (!library) return;
    setNotice("");
    setDownloads((d) => ({ ...d, [lessonId]: { kind: "downloading", fraction: 0 } }));
    try {
      void requestPersistentStorage();
      await library.install(lessonId, (fraction) =>
        setDownloads((d) => ({ ...d, [lessonId]: { kind: "downloading", fraction } })),
      );
      setDownloads((d) => ({ ...d, [lessonId]: { kind: "idle" } }));
      await refreshLocal();
    } catch (error) {
      setDownloads((d) => ({ ...d, [lessonId]: { kind: "failed", reason: classifyDownloadError(error) } }));
    }
  };

  const remove = async (lessonId: string) => {
    if (!library) return;
    await library.remove(lessonId);
    setDownloads((d) => ({ ...d, [lessonId]: { kind: "idle" } }));
    setNotice(t("student.offline.removed"));
    await refreshLocal();
  };

  const model = libraryModel({ list, installed, titles, downloads });

  return (
    <AppShell title={t("student.offline.title")} band={band}>
      <p style={{ margin: 0 }}>{t("student.offline.intro")}</p>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {notice ? <p role="status" style={{ margin: 0 }}>{notice}</p> : null}
        {model.kind === "loading" ? <Skeleton lines={4} label={t("student.offline.loading")} /> : null}
        {model.kind === "nothing-published" ? (
          <EmptyState
            title={t("student.offline.nothingTitle")}
            body={t("student.offline.nothingBody")}
            action={<ButtonLink href="/student/today" variant="ghost" label={t("common.backToToday")} />}
          />
        ) : null}
        {model.kind === "list" ? (
          <>
            {model.listUnavailable && list.status === "error" ? (
              <p style={{ margin: 0 }}>
                {classifyDownloadError(list.error) === "offline"
                  ? t("student.offline.listUnavailable")
                  : t("student.offline.failed.error")}
              </p>
            ) : null}
            <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>
              {t("student.offline.storageUsed", { size: formatBytes(model.installedBytes, locale) })}
              {free !== null ? ` ${t("student.offline.storageFree", { size: formatBytes(free, locale) })}` : ""}
            </p>
            {model.entries.map((entry) => (
              <EntryCard key={entry.lessonId} entry={entry} onSave={() => void save(entry.lessonId)} onRemove={() => void remove(entry.lessonId)} />
            ))}
          </>
        ) : null}
      </div>
    </AppShell>
  );
}
