"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { describeEventType } from "@/lib/eventTypes";
import { KoreanName } from "@/components/KoreanName";
import { WatchButton } from "@/components/WatchButton";
import type { InstrumentRanking } from "@/types/api";

const HALF_LIFE_DAYS = 180;

const leanStyles: Record<InstrumentRanking["lean"], string> = {
  bearish: "border-amber-300 bg-amber-50 text-amber-800",
  bullish: "border-emerald-200 bg-emerald-50 text-emerald-800",
  neutral: "border-gray-200 bg-gray-50 text-gray-600",
};

function pct(value: number): string {
  return `${value > 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

function scoreColor(value: number): string {
  if (value < -0.005) return "text-amber-700";
  if (value > 0.005) return "text-emerald-700";
  return "text-gray-600";
}

export default function RankingsPage() {
  const { t, lang } = useI18n();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["instrument-ranking"],
    queryFn: () => api.getInstrumentRanking(50, HALF_LIFE_DAYS),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">
        {t("rankings.loading")}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
        <p className="font-semibold">{t("rankings.failTitle")}</p>
        <p className="mt-1 text-sm">
          {error instanceof Error ? error.message : t("common.unknownError")}
        </p>
      </div>
    );
  }

  const rows = data ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{t("rankings.title")}</h1>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-gray-600">
          {t("rankings.subtitle")}
        </p>
        <p className="mt-2 text-xs text-gray-400">
          {t("rankings.weightingNote", { halfLife: HALF_LIFE_DAYS })}
        </p>
      </div>

      {rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center text-gray-500">
          {t("rankings.empty")}
        </div>
      ) : (
        <div className="max-h-[70vh] overflow-auto rounded-lg border border-gray-200 bg-white shadow-sm">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="sticky top-0 z-10 bg-white">
              <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
                <th className="px-4 py-3 font-medium">{t("rankings.col.rank")}</th>
                <th className="px-4 py-3 font-medium">
                  {t("rankings.col.instrument")}
                </th>
                <th className="px-4 py-3 font-medium">{t("rankings.col.lean")}</th>
                <th className="px-4 py-3 text-right font-medium">
                  {t("rankings.col.score")}
                </th>
                <th className="px-4 py-3 text-right font-medium">
                  {t("rankings.col.simpleMean")}
                </th>
                <th className="px-4 py-3 text-right font-medium">
                  {t("rankings.col.validated")}
                </th>
                <th className="px-4 py-3 text-right font-medium">
                  {t("rankings.col.conflicts")}
                </th>
                <th className="px-4 py-3 font-medium">
                  {t("rankings.col.topFactor")}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const factor = r.top_factor;
                const factorLabel = factor
                  ? t("rankings.factor", {
                      label: describeEventType(factor.event_type, lang).label,
                      drift: pct(factor.drift),
                      count: factor.count,
                    })
                  : "—";
                return (
                  <tr
                    key={r.instrument_id}
                    className="border-b border-gray-100 last:border-0 hover:bg-gray-50"
                  >
                    <td className="px-4 py-3 font-mono text-gray-400">{i + 1}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <WatchButton instrumentId={r.instrument_id} compact />
                        <Link
                          href={`/instruments/${r.instrument_id}`}
                          className="font-medium text-indigo-600 hover:underline"
                        >
                          {r.ticker}
                        </Link>
                      </div>
                      <div className="text-xs text-gray-500">
                        {r.name}
                        <KoreanName ticker={r.ticker} className="ml-1" />
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-semibold ${leanStyles[r.lean]}`}
                      >
                        {t(`rankings.lean.${r.lean}`)}
                      </span>
                    </td>
                    <td
                      className={`px-4 py-3 text-right font-mono font-semibold ${scoreColor(r.weighted_score)}`}
                    >
                      {pct(r.weighted_score)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-500">
                      {pct(r.simple_mean)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-700">
                      {r.validated_count}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-700">
                      {r.conflict_count === 0
                        ? "—"
                        : t("rankings.conflictsCell", {
                            total: r.conflict_count,
                            unreviewed: r.unreviewed_conflict_count,
                          })}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-600">
                      {factorLabel}
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
