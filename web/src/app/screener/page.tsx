"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { describeEventType } from "@/lib/eventTypes";
import { KoreanName } from "@/components/KoreanName";
import { WatchButton } from "@/components/WatchButton";
import type { DropDiagnosis, DrawdownScreenerRow } from "@/types/api";

const THRESHOLD = -0.15;

const diagnosisStyles: Record<DropDiagnosis, string> = {
  persistent_risk: "border-amber-300 bg-amber-50 text-amber-800",
  unexplained_drop: "border-gray-200 bg-gray-50 text-gray-600",
  // Blue, not green: a candidate — never imply an assured rise.
  possible_overreaction: "border-sky-200 bg-sky-50 text-sky-800",
};

function pct(value: number): string {
  return `${value > 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

export default function ScreenerPage() {
  const { t, lang } = useI18n();
  const [includeStale, setIncludeStale] = useState(false);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["drawdown-screener", includeStale],
    queryFn: () => api.getDrawdownScreener(THRESHOLD, includeStale),
  });

  const rows: DrawdownScreenerRow[] = data ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{t("screener.title")}</h1>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-gray-600">
          {t("screener.subtitle")}
        </p>
      </div>

      {/* Honesty banner — the system has no validated bullish signal. */}
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm leading-relaxed text-amber-900">
        {t("screener.disclaimer")}
      </div>

      <label className="inline-flex items-center gap-2 text-sm text-gray-600">
        <input
          type="checkbox"
          checked={includeStale}
          onChange={(e) => setIncludeStale(e.target.checked)}
          className="h-4 w-4 rounded border-gray-300"
        />
        {t("screener.includeStale")}
      </label>

      {isLoading ? (
        <div className="py-16 text-center text-gray-500">{t("screener.loading")}</div>
      ) : isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
          <p className="font-semibold">{t("screener.failTitle")}</p>
          <p className="mt-1 text-sm">
            {error instanceof Error ? error.message : t("common.unknownError")}
          </p>
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center text-gray-500">
          {t("screener.empty")}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
          <table className="w-full min-w-[820px] text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
                <th className="px-4 py-3 font-medium">{t("screener.col.instrument")}</th>
                <th className="px-4 py-3 text-right font-medium">
                  {t("screener.col.drawdown")}
                </th>
                <th className="px-4 py-3 text-right font-medium">
                  {t("screener.col.priceRange")}
                </th>
                <th className="px-4 py-3 font-medium">{t("screener.col.diagnosis")}</th>
                <th className="px-4 py-3 text-right font-medium">
                  {t("screener.col.recentEvents")}
                </th>
                <th className="px-4 py-3 font-medium">{t("screener.col.topFactor")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const factor = r.top_factor;
                const factorLabel = factor
                  ? `${describeEventType(factor.event_type, lang).label} ${pct(factor.drift)}`
                  : "—";
                return (
                  <tr
                    key={r.instrument_id}
                    className="border-b border-gray-100 last:border-0 hover:bg-gray-50"
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <WatchButton instrumentId={r.instrument_id} compact />
                        <Link
                          href={`/instruments/${r.instrument_id}`}
                          className="font-mono font-medium text-indigo-600 hover:underline"
                        >
                          {r.ticker}
                        </Link>
                        {r.is_stale ? (
                          <span className="rounded-full border border-gray-300 bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">
                            {t("screener.staleTag")}
                          </span>
                        ) : null}
                      </div>
                      <div className="text-xs text-gray-500">
                        {r.name}
                        <KoreanName ticker={r.ticker} className="ml-1" />
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-semibold text-amber-700">
                      {pct(r.drawdown)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-gray-600">
                      {r.current_price.toLocaleString()} /{" "}
                      {r.high_price.toLocaleString()}
                      <div className="text-[10px] text-gray-400">
                        {t("screener.asOf", { date: r.latest_date })}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        title={t(`screener.diagnosis.${r.diagnosis}Desc`)}
                        className={`inline-block cursor-help rounded-full border px-2.5 py-0.5 text-xs font-semibold ${diagnosisStyles[r.diagnosis]}`}
                      >
                        {t(`screener.diagnosis.${r.diagnosis}`)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-700">
                      {r.recent_event_count > 0
                        ? t("screener.eventsInWindow", { count: r.recent_event_count })
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-600">{factorLabel}</td>
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
