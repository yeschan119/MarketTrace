"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { assessSignal, type SignalVerdict } from "@/lib/validatedSignal";

interface Props {
  eventType: string;
  direction: string;
  horizonDays: number;
}

function formatPct(v: number | null): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(2)}%`;
}

function formatP(v: number | null): string {
  if (v == null) return "—";
  if (v < 0.001) return "<0.001";
  return v.toFixed(3);
}

function formatT(v: number | null): string {
  if (v == null) return "—";
  return v.toFixed(2);
}

const verdictStyles: Record<SignalVerdict, string> = {
  conflict: "border-amber-300 bg-amber-50 text-amber-800",
  agree: "border-emerald-200 bg-emerald-50 text-emerald-800",
  info: "border-indigo-200 bg-indigo-50 text-indigo-800",
  none: "border-gray-200 bg-gray-50 text-gray-600",
};

export function ValidatedSignalCard({ eventType, direction, horizonDays }: Props) {
  const { t } = useI18n();

  const { data, isLoading } = useQuery({
    queryKey: ["significance"],
    queryFn: () => api.getEventTypeSignificance(),
  });

  if (isLoading || !data) {
    return null;
  }

  const { verdict, rows, headline, histDirection: hd } = assessSignal(
    data,
    eventType,
    direction,
    horizonDays,
  );

  const llmLabel = ["positive", "negative", "neutral"].includes(
    direction.toLowerCase(),
  )
    ? t(`direction.${direction.toLowerCase()}`)
    : direction;
  const histLabel = hd ? t(`eventDetail.signal.${hd}`) : "—";

  const verdictText =
    verdict === "none"
      ? t("eventDetail.signal.none")
      : t(`eventDetail.signal.${verdict}`, { llm: llmLabel, hist: histLabel });

  return (
    <div className="rounded-lg border border-gray-200 bg-surface p-4 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-700">
          {t("eventDetail.signal.title")}
        </h3>
        {headline && (
          <span className="text-xs text-gray-400">
            {t("eventDetail.signal.verdictLabel")}
          </span>
        )}
      </div>
      <p className="mt-1 text-xs leading-relaxed text-gray-500">
        {t("eventDetail.signal.subtitle")}
      </p>

      <div
        className={`mt-3 rounded-md border px-3 py-2.5 text-sm leading-relaxed ${verdictStyles[verdict]}`}
      >
        {verdictText}
      </div>

      {rows.length > 0 && (
        <div className="mt-3 overflow-auto rounded-md border border-gray-100">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                <th className="px-3 py-2">{t("stats.signals.th.horizon")}</th>
                <th className="px-3 py-2 text-right">
                  {t("stats.signals.th.mean")}
                </th>
                <th className="px-3 py-2 text-right">
                  {t("stats.signals.th.t")}
                </th>
                <th className="px-3 py-2 text-right">
                  {t("stats.signals.th.p")}
                </th>
                <th className="px-3 py-2 text-right">
                  {t("stats.signals.th.n")}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const positive = (r.mean_abnormal_return ?? 0) >= 0;
                const isHeadline = r.horizon_days === headline?.horizon_days;
                return (
                  <tr
                    key={r.horizon_days}
                    className={`border-b border-gray-100 last:border-0 ${
                      isHeadline ? "bg-indigo-50/40" : ""
                    }`}
                  >
                    <td className="px-3 py-2 font-mono text-gray-600">
                      D+{r.horizon_days}
                    </td>
                    <td
                      className={`px-3 py-2 text-right font-mono font-medium ${
                        positive ? "text-emerald-600" : "text-red-600"
                      }`}
                    >
                      {formatPct(r.mean_abnormal_return)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-gray-500">
                      {formatT(r.t_stat)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-gray-500">
                      {formatP(r.p_value)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-gray-500">
                      {r.count}
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
