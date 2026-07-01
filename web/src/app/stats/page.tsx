"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { DirectionBadge } from "@/components/DirectionBadge";
import type {
  EventTypeStat,
  EventContribution,
  BacktestResult,
  BacktestModel,
} from "@/types/api";

function formatPct(v: number | null): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(2)}%`;
}

function formatIc(v: number | null): string {
  if (v == null) return "—";
  return v.toFixed(2);
}

export default function StatsPage() {
  const { t, locale } = useI18n();
  // A statistic is one (event_type, horizon) row; select that exact bucket.
  const [selected, setSelected] = useState<{
    type: string;
    horizon: number;
  } | null>(null);
  const [model, setModel] = useState<BacktestModel>("event_type_history");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["event-type-stats"],
    queryFn: () => api.getEventTypeStats(),
  });

  // Task 2: fetch every event's per-horizon abnormal return once, then filter
  // to the selected (event_type, horizon) so the stat's mean is auditable.
  const { data: contribData } = useQuery({
    queryKey: ["event-type-contributions"],
    queryFn: () => api.getEventTypeContributions(),
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
  const allContribs: EventContribution[] = contribData ?? [];
  const related: EventContribution[] = selected
    ? allContribs
        .filter(
          (c) =>
            c.event_type === selected.type &&
            c.horizon_days === selected.horizon
        )
        .sort(
          (a, b) => (b.abnormal_return ?? -Infinity) - (a.abnormal_return ?? -Infinity)
        )
    : [];
  // Mean of the contributions the user is looking at — reconstructs the stat row.
  const relatedValues = related
    .map((c) => c.abnormal_return)
    .filter((v): v is number => v != null);
  const relatedMean = relatedValues.length
    ? relatedValues.reduce((sum, v) => sum + v, 0) / relatedValues.length
    : null;

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
        <>
          <p className="text-xs text-gray-500">{t("stats.relatedHint")}</p>
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
                  const active =
                    selected?.type === s.event_type &&
                    selected?.horizon === s.horizon_days;
                  return (
                    <tr
                      key={`${s.event_type}-${s.horizon_days}`}
                      className={`border-b border-gray-100 last:border-0 ${
                        active ? "bg-indigo-50" : "hover:bg-gray-50"
                      }`}
                    >
                      <td className="px-1 py-1">
                        <button
                          type="button"
                          onClick={() =>
                            setSelected(
                              active
                                ? null
                                : { type: s.event_type, horizon: s.horizon_days }
                            )
                          }
                          aria-pressed={active}
                          className={`w-full rounded px-3 py-2 text-left font-medium transition-colors ${
                            active
                              ? "text-indigo-700"
                              : "text-gray-900 hover:text-indigo-600"
                          }`}
                        >
                          {s.event_type}
                        </button>
                      </td>
                      <td className="px-4 py-3 font-mono text-gray-600">
                        D+{s.horizon_days}
                      </td>
                      <td className="px-4 py-3 text-right text-gray-600">
                        {s.count}
                      </td>
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

          {selected && (
            <div className="rounded-lg border border-indigo-200 bg-indigo-50/40 p-4 shadow-sm">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-sm font-semibold text-gray-900">
                  {t("stats.relatedTitle", {
                    type: selected.type,
                    horizon: selected.horizon,
                  })}
                </h2>
                <span className="text-xs text-gray-500">
                  {t("stats.relatedCount", { n: related.length })}
                </span>
              </div>

              {related.length === 0 ? (
                <p className="mt-3 text-sm text-gray-500">
                  {t("stats.relatedEmpty")}
                </p>
              ) : (
                <>
                  <p className="mt-1 text-sm text-gray-700">
                    {t("stats.relatedSummary", {
                      n: relatedValues.length,
                      mean: formatPct(relatedMean),
                    })}
                  </p>
                  <ul className="mt-3 divide-y divide-indigo-100">
                    {related.map((c) => {
                      const positive = (c.abnormal_return ?? 0) >= 0;
                      return (
                        <li key={c.event_id} className="py-2">
                          <Link
                            href={`/events/${c.event_id}`}
                            className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded px-2 py-1 hover:bg-white"
                          >
                            <span className="font-mono text-sm font-semibold text-gray-900">
                              {c.primary_ticker}
                            </span>
                            <span className="text-sm text-gray-700">
                              {c.instrument_name}
                            </span>
                            <DirectionBadge direction={c.direction} />
                            <span className="ml-auto text-xs text-gray-500">
                              {new Date(c.published_at).toLocaleDateString(locale)}
                            </span>
                            <span
                              className={`w-20 text-right font-mono text-sm font-medium ${
                                positive ? "text-emerald-600" : "text-red-600"
                              }`}
                              title={t("stats.relatedReturn")}
                            >
                              {formatPct(c.abnormal_return)}
                            </span>
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </>
              )}
            </div>
          )}
        </>
      )}

      <BacktestSection model={model} setModel={setModel} />
    </div>
  );
}

function BacktestSection({
  model,
  setModel,
}: {
  model: BacktestModel;
  setModel: (m: BacktestModel) => void;
}) {
  const { t } = useI18n();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["backtest", model],
    queryFn: () => api.getBacktest(model),
  });

  const rows: BacktestResult[] = data ?? [];
  const isEmpty =
    rows.length === 0 || rows.every((r) => (r.n_predictions ?? 0) === 0);

  const modelOptions: { value: BacktestModel; label: string }[] = [
    {
      value: "event_type_history",
      label: t("stats.backtest.model.event_type_history"),
    },
    { value: "llm_direction", label: t("stats.backtest.model.llm_direction") },
  ];

  return (
    <section className="space-y-4 pt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-xl font-bold text-gray-900">
            {t("stats.backtest.title")}
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            {t("stats.backtest.subtitle")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-500">
            {t("stats.backtest.modelLabel")}
          </span>
          <div
            role="group"
            aria-label={t("stats.backtest.modelLabel")}
            className="inline-flex rounded-md border border-gray-200 bg-gray-50 p-0.5 text-xs font-medium"
          >
            {modelOptions.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setModel(opt.value)}
                aria-pressed={model === opt.value}
                className={`rounded px-2.5 py-1 transition-colors ${
                  model === opt.value
                    ? "bg-white text-indigo-600 shadow-sm"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-gray-300 text-sm text-gray-500">
          {t("stats.backtest.loading")}
        </div>
      ) : isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
          <p className="font-semibold">{t("stats.backtest.failTitle")}</p>
        </div>
      ) : isEmpty ? (
        <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-gray-300 text-sm text-gray-500">
          {t("stats.backtest.empty")}
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                <th className="px-4 py-3">{t("stats.backtest.th.horizon")}</th>
                <th className="px-4 py-3 text-right">
                  {t("stats.backtest.th.predictions")}
                </th>
                <th className="px-4 py-3 text-right">
                  {t("stats.backtest.th.hitRate")}
                </th>
                <th className="px-4 py-3 text-right">
                  {t("stats.backtest.th.gross")}
                </th>
                <th className="px-4 py-3 text-right">
                  {t("stats.backtest.th.net")}
                </th>
                <th className="px-4 py-3 text-right">
                  {t("stats.backtest.th.ic")}
                </th>
                <th className="px-4 py-3 text-right">
                  {t("stats.backtest.th.coverage")}
                  <span className="block font-normal normal-case tracking-normal text-gray-400">
                    {t("stats.backtest.coverageHint")}
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const grossPositive = (r.mean_strategy_return ?? 0) >= 0;
                const netPositive = (r.mean_strategy_return_net ?? 0) >= 0;
                return (
                  <tr
                    key={`${r.model}-${r.horizon_days}`}
                    className="border-b border-gray-100 last:border-0 hover:bg-gray-50"
                  >
                    <td className="px-4 py-3 font-mono text-gray-600">
                      D+{r.horizon_days}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600">
                      {r.n_predictions}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-600">
                      {formatPct(r.hit_rate)}
                    </td>
                    <td
                      className={`px-4 py-3 text-right font-mono font-medium ${
                        grossPositive ? "text-emerald-600" : "text-red-600"
                      }`}
                    >
                      {formatPct(r.mean_strategy_return)}
                    </td>
                    <td
                      className={`px-4 py-3 text-right font-mono font-medium ${
                        netPositive ? "text-emerald-600" : "text-red-600"
                      }`}
                    >
                      {formatPct(r.mean_strategy_return_net)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-500">
                      {formatIc(r.information_coefficient)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-500">
                      {r.n_events} / {r.n_dropped_no_outcome}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
