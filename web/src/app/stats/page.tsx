"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { EventTypeStat } from "@/types/api";

function formatPct(v: number | null): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(2)}%`;
}

export default function StatsPage() {
  const { t } = useI18n();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["event-type-stats"],
    queryFn: () => api.getEventTypeStats(),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">
        {t("stats.loading")}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
        <p className="font-semibold">{t("stats.failTitle")}</p>
        <p className="mt-1 text-sm">
          {error instanceof Error ? error.message : t("common.unknownError")}
        </p>
      </div>
    );
  }

  const stats: EventTypeStat[] = data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-bold text-gray-900">{t("stats.title")}</h1>
        <span className="text-sm text-gray-500">
          {t("stats.buckets", { n: stats.length })}
        </span>
      </div>
      <p className="text-sm text-gray-500">{t("stats.subtitle")}</p>

      {stats.length === 0 ? (
        <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-gray-300 text-sm text-gray-500">
          {t("stats.empty")}
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                <th className="px-4 py-3">{t("stats.th.eventType")}</th>
                <th className="px-4 py-3">{t("stats.th.horizon")}</th>
                <th className="px-4 py-3 text-right">{t("stats.th.samples")}</th>
                <th className="px-4 py-3 text-right">{t("stats.th.mean")}</th>
                <th className="px-4 py-3 text-right">{t("stats.th.std")}</th>
              </tr>
            </thead>
            <tbody>
              {stats.map((s) => {
                const positive = (s.mean_abnormal_return ?? 0) >= 0;
                return (
                  <tr
                    key={`${s.event_type}-${s.horizon_days}`}
                    className="border-b border-gray-100 last:border-0 hover:bg-gray-50"
                  >
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {s.event_type}
                    </td>
                    <td className="px-4 py-3 font-mono text-gray-600">
                      D+{s.horizon_days}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600">{s.count}</td>
                    <td
                      className={`px-4 py-3 text-right font-mono font-medium ${
                        positive ? "text-emerald-600" : "text-red-600"
                      }`}
                    >
                      {formatPct(s.mean_abnormal_return)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-500">
                      {formatPct(s.std_abnormal_return)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
