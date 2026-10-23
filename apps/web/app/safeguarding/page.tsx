"use client";
// The safeguarding queue: open concerns by priority, then by how long they have waited. The SLA
// banner says "SLA not set — owner decision FD-06" until every tier has a configured threshold; no
// concern is ever called overdue against a number the server did not send. Free text is not shown
// here — only in a concern's own page, where opening it is audited.
import Link from "next/link";
import { useCallback, useEffect, useId, useState } from "react";

import { useLocale } from "@/lib/i18n/useLocale";
import { leadApi } from "@/lib/safeguarding/api";
import { categoryOption } from "@/lib/safeguarding/categories";
import {
  actionErrorKey,
  ageLabel,
  overdueKey,
  slaBanner,
  sortQueue,
  statusKey,
  thresholdText,
  type QueueWire,
} from "@/lib/safeguarding/triage";
import type { MessageKey } from "@/lib/i18n/messages";

const cell = { padding: "var(--space-2)", borderBottom: "1px solid var(--color-focus-ring)", textAlign: "start" } as const;

export default function SafeguardingQueuePage() {
  const { t } = useLocale();
  const resolvedId = useId();
  const [includeResolved, setIncludeResolved] = useState(false);
  const [queue, setQueue] = useState<QueueWire | null>(null);
  const [error, setError] = useState<MessageKey | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setQueue(await leadApi.queue(includeResolved));
    } catch (e) {
      setError(actionErrorKey(e) === "safeguarding.console.detail.refused" ? "safeguarding.console.loadError" : actionErrorKey(e));
    }
  }, [includeResolved]);

  useEffect(() => {
    void load();
  }, [load]);

  const banner = queue ? slaBanner(queue.sla) : null;
  const concerns = queue ? sortQueue(queue.concerns) : [];

  return (
    <main style={{ display: "grid", gap: "var(--space-4)" }}>
      <h1 style={{ margin: 0 }}>{t("safeguarding.console.queueHeading")}</h1>

      {banner && banner.kind !== "set" ? (
        <section
          aria-label={t(banner.key)}
          style={{ padding: "var(--space-3)", border: "2px solid var(--color-danger)", borderRadius: "var(--radius-md)" }}
        >
          <strong>{t(banner.key)}</strong>
          <p style={{ margin: "var(--space-1) 0 0" }}>
            {banner.kind === "partial" ? t(banner.bodyKey, { thresholds: thresholdText(banner, t) }) : t(banner.bodyKey)}
          </p>
        </section>
      ) : null}
      {banner && banner.kind === "set" ? (
        <p style={{ margin: 0 }}>{t("safeguarding.console.slaSet", { thresholds: thresholdText(banner, t) })}</p>
      ) : null}

      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", minHeight: "var(--size-touch-min)" }}>
        <input
          id={resolvedId}
          type="checkbox"
          checked={includeResolved}
          onChange={(e) => setIncludeResolved(e.target.checked)}
          style={{ width: 24, height: 24 }}
        />
        <label htmlFor={resolvedId}>{t("safeguarding.console.showResolved")}</label>
      </div>

      <div aria-live="polite">
        {error ? (
          <p role="alert" style={{ color: "var(--color-danger)", margin: 0 }}>
            {t(error)}
          </p>
        ) : null}
        {!queue && !error ? (
          <p role="status" aria-busy="true">
            {t("common.loading")}
          </p>
        ) : null}
      </div>

      {queue && concerns.length === 0 ? <p style={{ margin: 0 }}>{t("safeguarding.console.empty")}</p> : null}

      {concerns.length > 0 ? (
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <caption className="visually-hidden">{t("safeguarding.console.queueHeading")}</caption>
            <thead>
              <tr>
                <th scope="col" style={cell}>{t("safeguarding.console.columns.priority")}</th>
                <th scope="col" style={cell}>{t("safeguarding.console.columns.category")}</th>
                <th scope="col" style={cell}>{t("safeguarding.console.columns.raisedBy")}</th>
                <th scope="col" style={cell}>{t("safeguarding.console.columns.age")}</th>
                <th scope="col" style={cell}>{t("safeguarding.console.columns.status")}</th>
                <th scope="col" style={cell}>{t("safeguarding.console.columns.overdue")}</th>
                <th scope="col" style={cell}>{t("safeguarding.console.columns.open")}</th>
              </tr>
            </thead>
            <tbody>
              {concerns.map((c, index) => {
                const age = ageLabel(c.age_seconds);
                const option = categoryOption(c.category);
                return (
                  <tr key={c.concern_id}>
                    <td style={{ ...cell, fontWeight: c.priority === "T1" ? 700 : 400 }}>{c.priority}</td>
                    <td style={cell}>{option ? t(option.adultKey) : c.category}</td>
                    <td style={cell}>{t(`safeguarding.console.raisedBy.${c.raised_by_role}`)}</td>
                    <td style={cell}>{t(age.key, age.params)}</td>
                    <td style={cell}>{t(statusKey(c.status))}</td>
                    <td style={{ ...cell, fontWeight: c.overdue ? 700 : 400 }}>{t(overdueKey(c.overdue))}</td>
                    <td style={cell}>
                      <Link
                        href={`/safeguarding/concerns/${encodeURIComponent(c.concern_id)}`}
                        style={{ display: "inline-flex", minHeight: "var(--size-touch-min)", alignItems: "center", color: "var(--color-action-primary)" }}
                      >
                        {t("safeguarding.console.openConcern", { n: index + 1 })}
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </main>
  );
}
