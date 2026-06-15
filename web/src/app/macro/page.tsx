"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { MacroObservation } from "@/types/api";

function formatNum(v: number | null, locale: string): string {
  if (v == null) return "—";
  return v.toLocaleString(locale, { maximumFractionDigits: 3 });
}

function formatSigma(v: number | null): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}σ`;
}

export default function MacroPage() {
  const { t, locale } = useI18n();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["macro-observations"],
    queryFn: () => api.getMacroObservations(),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">
        {t("macro.loading")}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
        <p className="font-semibold">{t("macro.failTitle")}</p>
        <p className="mt-1 text-sm">
          {error instanceof Error ? error.message : t("common.unknownError")}
        </p>
      </div>
    );
  }

  const observations: MacroObservation[] = data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-bold text-gray-900">{t("macro.title")}</h1>
        <span className="text-sm text-gray-500">
          {t("macro.count", { n: observations.length })}
        </span>
      </div>
      <p className="text-sm text-gray-500">{t("macro.subtitle")}</p>

      {observations.length === 0 ? (
        <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-gray-300 text-sm text-gray-500">
          {t("macro.empty")}
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                <th className="px-4 py-3">{t("macro.th.series")}</th>
                <th className="px-4 py-3">{t("macro.th.reference")}</th>
                <th className="px-4 py-3 text-right">{t("macro.th.released")}</th>
                <th className="px-4 py-3 text-right">{t("macro.th.expected")}</th>
                <th className="px-4 py-3 text-right">{t("macro.th.surprise")}</th>
              </tr>
            </thead>
            <tbody>
              {observations.map((o) => {
                const positive = (o.surprise_score ?? 0) >= 0;
                return (
                  <tr
                    key={o.series_id}
                    className="border-b border-gray-100 last:border-0 hover:bg-gray-50"
                  >
                    <td className="px-4 py-3 font-mono font-medium text-gray-900">
                      {o.series_id}
                    </td>
                    <td className="px-4 py-3 text-gray-600">{o.reference_date}</td>
                    <td className="px-4 py-3 text-right font-mono text-gray-700">
                      {formatNum(o.released_value, locale)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-500">
                      {formatNum(o.expected_value, locale)}
                      {o.expected_source && (
                        <span className="ml-1.5 rounded-full bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-500">
                          {o.expected_source === "consensus"
                            ? t("macro.consensus")
                            : t("macro.baseline")}
                        </span>
                      )}
                    </td>
                    <td
                      className={`px-4 py-3 text-right font-mono font-medium ${
                        o.surprise_score == null
                          ? "text-gray-400"
                          : positive
                            ? "text-emerald-600"
                            : "text-red-600"
                      }`}
                    >
                      {formatSigma(o.surprise_score)}
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
