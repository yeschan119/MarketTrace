"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { describeEventType } from "@/lib/eventTypes";
import { KoreanName } from "@/components/KoreanName";
import type { Alert } from "@/types/api";

const kindStyles: Record<Alert["kind"], string> = {
  conflict: "border-amber-300 bg-amber-50 text-amber-800",
  significant: "border-indigo-200 bg-indigo-50 text-indigo-700",
};

type AlertGroup = {
  label: string;
  alerts: Alert[];
};

function groupAlertsByDate(alerts: Alert[], locale: string): AlertGroup[] {
  const dateFormatter = new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  const groups: AlertGroup[] = [];
  const indexByLabel = new Map<string, number>();

  [...alerts]
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    )
    .forEach((alert) => {
      const label = dateFormatter.format(new Date(alert.created_at));
      const existingIndex = indexByLabel.get(label);
      if (existingIndex == null) {
        indexByLabel.set(label, groups.length);
        groups.push({ label, alerts: [alert] });
      } else {
        groups[existingIndex].alerts.push(alert);
      }
    });

  return groups;
}

export default function AlertsPage() {
  const { t, lang } = useI18n();
  const { token } = useAuth();
  const qc = useQueryClient();
  const locale = lang === "ko" ? "ko-KR" : "en-US";

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["alerts", "list"],
    queryFn: () => api.listAlerts(),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["alerts"] });
  };

  const markRead = useMutation({
    mutationFn: (id: number) => api.markAlertRead(id, token!),
    onSuccess: invalidate,
  });
  const markAll = useMutation({
    mutationFn: () => api.markAllAlertsRead(token!),
    onSuccess: invalidate,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">
        {t("alerts.title")}…
      </div>
    );
  }
  if (isError) {
    return (
      <div className="py-20 text-center text-red-600">
        {(error as Error)?.message ?? t("common.unknownError")}
      </div>
    );
  }

  const alerts = data ?? [];
  const hasUnread = alerts.some((a) => a.read_at === null);
  const groupedAlerts = groupAlertsByDate(alerts, locale);
  const timeFormatter = new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t("alerts.title")}</h1>
          <p className="text-sm text-gray-500">{t("alerts.subtitle")}</p>
        </div>
        {token && hasUnread && (
          <button
            type="button"
            onClick={() => markAll.mutate()}
            disabled={markAll.isPending}
            className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
          >
            {t("alerts.markAllRead")}
          </button>
        )}
      </div>

      {alerts.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 px-6 py-12 text-center text-gray-500">
          {t("alerts.empty")}
        </div>
      ) : (
        <div className="max-h-[70vh] overflow-y-auto rounded-lg border border-gray-200 bg-white">
          {groupedAlerts.map((group) => (
            <section key={group.label} aria-label={group.label}>
              <div className="sticky top-0 z-10 flex items-center justify-between border-b border-gray-100 bg-gray-50/95 px-4 py-2 backdrop-blur">
                <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                  {group.label}
                </h2>
                <span className="text-xs text-gray-400">
                  {t("alerts.groupCount", { count: group.alerts.length })}
                </span>
              </div>
              <ul className="divide-y divide-gray-100">
                {group.alerts.map((a) => {
                  const unread = a.read_at === null;
                  const info = describeEventType(a.event_type, lang);
                  return (
                    <li
                      key={a.id}
                      className={`flex items-center gap-3 px-4 py-3 ${
                        unread ? "bg-indigo-50/40" : ""
                      }`}
                    >
                      {unread && (
                        <span
                          className="h-2 w-2 flex-shrink-0 rounded-full bg-indigo-500"
                          aria-hidden
                        />
                      )}
                      <Link
                        href={`/events/${a.event_id}`}
                        onClick={() => token && unread && markRead.mutate(a.id)}
                        className="min-w-0 flex-1"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-sm font-semibold text-indigo-600">
                            {a.primary_ticker}
                          </span>
                          <span className="truncate text-sm text-gray-900">
                            {a.instrument_name}
                            <KoreanName ticker={a.primary_ticker} className="ml-1.5" />
                          </span>
                          <span
                            className={`rounded border px-1.5 py-0.5 text-xs font-semibold ${kindStyles[a.kind]}`}
                          >
                            {a.kind === "conflict"
                              ? t("alerts.kindConflict")
                              : t("alerts.kindSignificant")}
                          </span>
                        </div>
                        <div className="mt-0.5 text-xs text-gray-500">
                          {info.label} ·{" "}
                          {a.kind === "conflict"
                            ? t("alerts.conflictDesc")
                            : t("alerts.significantDesc")}
                        </div>
                      </Link>
                      <span className="flex-shrink-0 text-xs text-gray-400">
                        {timeFormatter.format(new Date(a.created_at))}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
