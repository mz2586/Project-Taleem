"use client";
// Field-by-field comparison of two published versions, from their bodies
// (GET /v1/studio/lessons/{id}/versions/{n}); the diff itself is lib/studio/diff.ts.
import { useEffect, useId, useState } from "react";

import { contentAttrs } from "@/lib/i18n/content";
import { useLocale } from "@/lib/i18n/useLocale";
import { studioApi, type VersionView } from "@/lib/studio-api";
import { diffBodies, leafLocale, type DiffEntry } from "@/lib/studio/diff";

import { SelectField } from "./controls";

const cell = { padding: "var(--space-2)", borderBottom: "1px solid var(--color-focus-ring)", textAlign: "start" as const, verticalAlign: "top" as const };

export function VersionDiff({ lessonId, versions }: { lessonId: string; versions: VersionView[] }) {
  const { t } = useLocale();
  const ids = { from: useId(), to: useId() };
  const sorted = [...versions].sort((a, b) => a.version - b.version);
  const [from, setFrom] = useState<number | null>(sorted.at(-2)?.version ?? null);
  const [to, setTo] = useState<number | null>(sorted.at(-1)?.version ?? null);
  const [state, setState] = useState<{ status: "idle" | "loading" | "ready" | "error"; entries: DiffEntry[] }>({ status: "idle", entries: [] });

  useEffect(() => {
    if (from === null || to === null || from === to) return;
    let alive = true;
    setState({ status: "loading", entries: [] });
    Promise.all([studioApi.version(lessonId, from), studioApi.version(lessonId, to)])
      .then(([a, b]) => alive && setState({ status: "ready", entries: diffBodies(a.body, b.body) }))
      .catch(() => alive && setState({ status: "error", entries: [] }));
    return () => {
      alive = false;
    };
  }, [lessonId, from, to]);

  if (sorted.length < 2) return <p style={{ margin: 0 }}>{t("studio.lesson.diffNeedTwo")}</p>;

  const kind = (k: DiffEntry["kind"]) =>
    t(k === "added" ? "studio.lesson.diffAdded" : k === "removed" ? "studio.lesson.diffRemoved" : "studio.lesson.diffChanged");
  const show = (v: DiffEntry["before"]) => (v === undefined || v === "" ? "—" : String(v));

  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }}>
      <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <SelectField id={ids.from} label={t("studio.lesson.diffFrom")} value={from ?? ""} onChange={(e) => setFrom(Number(e.target.value))}>
          {sorted.map((v) => (
            <option key={v.version} value={v.version}>
              v{v.version}
            </option>
          ))}
        </SelectField>
        <SelectField id={ids.to} label={t("studio.lesson.diffTo")} value={to ?? ""} onChange={(e) => setTo(Number(e.target.value))}>
          {sorted.map((v) => (
            <option key={v.version} value={v.version}>
              v{v.version}
            </option>
          ))}
        </SelectField>
      </div>
      <div aria-live="polite">
        {state.status === "loading" ? <p role="status">{t("studio.lesson.diffLoading")}</p> : null}
        {state.status === "error" ? <p role="alert">{t("studio.lesson.diffError")}</p> : null}
        {state.status === "ready" && state.entries.length === 0 ? <p style={{ margin: 0 }}>{t("studio.lesson.diffNone")}</p> : null}
      </div>
      {state.status === "ready" && state.entries.length > 0 ? (
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>
                <th scope="col" style={cell}>{t("studio.lesson.diffPath")}</th>
                <th scope="col" style={cell}>{t("studio.lesson.diffChange")}</th>
                <th scope="col" style={cell}>{t("studio.lesson.diffBefore")}</th>
                <th scope="col" style={cell}>{t("studio.lesson.diffAfter")}</th>
              </tr>
            </thead>
            <tbody>
              {state.entries.map((d) => {
                const locale = leafLocale(d.path);
                const attrs = locale ? contentAttrs({ locale }) : { dir: "auto" as const };
                return (
                  <tr key={d.path}>
                    <th scope="row" style={cell}>
                      <code>{d.path}</code>
                    </th>
                    <td style={cell}>{kind(d.kind)}</td>
                    <td style={cell} {...attrs}>
                      {show(d.before)}
                    </td>
                    <td style={cell} {...attrs}>
                      {show(d.after)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
