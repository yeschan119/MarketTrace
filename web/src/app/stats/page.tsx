"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { describeEventType } from "@/lib/eventTypes";
import { DirectionBadge } from "@/components/DirectionBadge";
import type {
  EventTypeStat,
  EventTypeSignificance,
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

function formatP(v: number | null): string {
  if (v == null) return "—";
  if (v < 0.001) return "<0.001";
  return v.toFixed(3);
}

function formatT(v: number | null): string {
  if (v == null) return "—";
  return v.toFixed(2);
}

// The stats API returns one row per (event_type, horizon). We show fixed
// horizons as columns so each event type is a single, non-repeating row.
const HORIZONS = [1, 5, 20, 60] as const;

type TypeGroup = {
  event_type: string;
  total: number;
  cells: Map<number, EventTypeStat>;
};

// Collapse the flat (event_type × horizon) rows into one row per event type,
// then order by sample count so types with real evidence lead and n=1 noise
// sinks. This is what kills the "same thing over and over" feeling.
function groupByType(stats: EventTypeStat[]): TypeGroup[] {
  const byType = new Map<string, TypeGroup>();
  for (const s of stats) {
    let g = byType.get(s.event_type);
    if (!g) {
      g = { event_type: s.event_type, total: 0, cells: new Map() };
      byType.set(s.event_type, g);
    }
    g.cells.set(s.horizon_days, s);
    g.total += s.count;
  }
  return [...byType.values()].sort(
    (a, b) => b.total - a.total || a.event_type.localeCompare(b.event_type)
  );
}

export default function StatsPage() {
  const { t, locale, lang } = useI18n();
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

  // Which (event_type, horizon) buckets are statistically validated signals —
  // enough sample AND distinguishable from zero. This is the "what does the data
  // actually support" layer that turns the mean matrix into buy/avoid evidence.
  const { data: sigData } = useQuery({
    queryKey: ["event-type-significance"],
    queryFn: () => api.getEventTypeSignificance(),
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

  // Validated signals: sufficient sample AND significant at 5%, strongest
  // evidence (smallest p) first. `sigSet` lets the matrix flag the same cells.
  const sigRows: EventTypeSignificance[] = (sigData ?? [])
    .filter((s) => s.significant_5pct && s.sufficient_sample)
    .sort((a, b) => (a.p_value ?? 1) - (b.p_value ?? 1));
  const sigSet = new Set(
    sigRows.map((s) => `${s.event_type}|${s.horizon_days}`)
  );

  const groups = groupByType(stats);
  const selectedInfo = selected ? describeEventType(selected.type, lang) : null;
  const toggleCell = (type: string, horizon: number) =>
    setSelected((prev) =>
      prev?.type === type && prev?.horizon === horizon
        ? null
        : { type, horizon }
    );

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-bold text-gray-900">{t("stats.title")}</h1>
        <span className="text-sm text-gray-500">
          {t("stats.buckets", { n: stats.length })}
        </span>
      </div>
      <p className="text-sm text-gray-500">{t("stats.subtitle")}</p>

      <SignalsSection rows={sigRows} />

      {stats.length === 0 ? (
        <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-gray-300 text-sm text-gray-500">
          {t("stats.empty")}
        </div>
      ) : (
        <>
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
            <p className="text-sm font-semibold text-gray-900">
              {t("stats.howToRead")}
            </p>
            <p className="mt-1 text-sm leading-relaxed text-gray-600">
              {t("stats.howToReadBody")}
            </p>
          </div>
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-xs font-semibold uppercase tracking-wide text-gray-500">
                  <th rowSpan={2} className="px-4 py-3 text-left align-bottom">
                    {t("stats.th.eventType")}
                  </th>
                  <th rowSpan={2} className="px-4 py-3 text-right align-bottom">
                    {t("stats.th.total")}
                  </th>
                  <th
                    colSpan={HORIZONS.length}
                    className="border-b border-gray-100 px-4 py-2 text-center font-medium normal-case tracking-normal text-gray-400"
                  >
                    {t("stats.th.horizonGroup")}
                  </th>
                </tr>
                <tr className="border-b border-gray-200 text-xs font-semibold uppercase tracking-wide text-gray-500">
                  {HORIZONS.map((h) => (
                    <th key={h} className="px-3 py-2 text-right font-mono">
                      D+{h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {groups.map((g) => {
                  const info = describeEventType(g.event_type, lang);
                  return (
                  <tr
                    key={g.event_type}
                    className="border-b border-gray-100 last:border-0 hover:bg-gray-50/60"
                  >
                    <td className="px-4 py-2" title={info.desc || undefined}>
                      <span className="block font-medium text-gray-900">
                        {info.label}
                      </span>
                      {info.desc && (
                        <span className="block text-xs text-gray-500">
                          {info.desc}
                        </span>
                      )}
                      <span className="block font-mono text-[10px] text-gray-400">
                        {g.event_type}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right text-gray-500">
                      {g.total}
                    </td>
                    {HORIZONS.map((h) => {
                      const cell = g.cells.get(h);
                      const value = cell?.mean_abnormal_return ?? null;
                      const hasData =
                        cell != null && cell.count > 0 && value != null;
                      const active =
                        selected?.type === g.event_type &&
                        selected?.horizon === h;
                      if (!hasData) {
                        return (
                          <td
                            key={h}
                            className="px-3 py-2 text-right font-mono text-gray-300"
                            title={t("stats.noData")}
                          >
                            —
                          </td>
                        );
                      }
                      const positive = value >= 0;
                      const isSig = sigSet.has(`${g.event_type}|${h}`);
                      return (
                        <td key={h} className="p-1 text-right">
                          <button
                            type="button"
                            onClick={() => toggleCell(g.event_type, h)}
                            aria-pressed={active}
                            title={`${t("stats.th.std")}: ${formatPct(
                              cell.std_abnormal_return
                            )}${isSig ? ` · ${t("stats.signals.badge")}` : ""}`}
                            className={`w-full rounded px-2 py-1.5 text-right font-mono transition-colors ${
                              active
                                ? "bg-indigo-600 text-white shadow-sm"
                                : "hover:bg-indigo-50"
                            }`}
                          >
                            <span
                              className={`block font-medium ${
                                active
                                  ? "text-white"
                                  : positive
                                    ? "text-emerald-600"
                                    : "text-red-600"
                              }`}
                            >
                              {isSig && (
                                <span
                                  aria-hidden
                                  className={active ? "text-white" : "text-indigo-500"}
                                >
                                  ★{" "}
                                </span>
                              )}
                              {formatPct(value)}
                            </span>
                            <span
                              className={`block text-[10px] ${
                                active ? "text-indigo-100" : "text-gray-400"
                              }`}
                            >
                              n={cell.count}
                            </span>
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-gray-500">{t("stats.relatedHint")}</p>

          {selected && (
            <div className="rounded-lg border border-indigo-200 bg-indigo-50/40 p-4 shadow-sm">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-sm font-semibold text-gray-900">
                  {t("stats.relatedTitle", {
                    type: selectedInfo?.label ?? selected.type,
                    horizon: selected.horizon,
                  })}
                </h2>
                <span className="text-xs text-gray-500">
                  {t("stats.relatedCount", { n: related.length })}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-gray-500">
                {selectedInfo?.desc ? `${selectedInfo.desc} · ` : ""}
                <span className="font-mono">{selected.type}</span>
              </p>

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

// The validated-signals panel: the buckets the data actually supports. This is
// the "which events matter for a buy/avoid call" surface — the whole point of
// the measure-and-validate direction. It leads the page above the raw matrix.
function SignalsSection({ rows }: { rows: EventTypeSignificance[] }) {
  const { t, lang } = useI18n();
  const allNegative =
    rows.length > 0 && rows.every((r) => (r.mean_abnormal_return ?? 0) < 0);

  return (
    <section className="space-y-3 rounded-lg border border-indigo-200 bg-indigo-50/40 p-4 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-bold text-gray-900">
          {t("stats.signals.title")}
        </h2>
        {rows.length > 0 && (
          <span className="text-xs text-gray-500">
            {t("stats.signals.count", { n: rows.length })}
          </span>
        )}
      </div>
      <p className="text-sm leading-relaxed text-gray-600">
        {t("stats.signals.subtitle")}
      </p>

      {rows.length === 0 ? (
        <div className="flex h-24 items-center justify-center rounded-md border border-dashed border-indigo-200 text-sm text-gray-500">
          {t("stats.signals.empty")}
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-md border border-indigo-100 bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  <th className="px-4 py-2.5">
                    {t("stats.signals.th.eventType")}
                  </th>
                  <th className="px-3 py-2.5 text-right">
                    {t("stats.signals.th.horizon")}
                  </th>
                  <th className="px-3 py-2.5 text-right">
                    {t("stats.signals.th.mean")}
                  </th>
                  <th className="px-3 py-2.5 text-right">
                    {t("stats.signals.th.t")}
                  </th>
                  <th className="px-3 py-2.5 text-right">
                    {t("stats.signals.th.p")}
                  </th>
                  <th className="px-3 py-2.5 text-right">
                    {t("stats.signals.th.n")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const info = describeEventType(r.event_type, lang);
                  const positive = (r.mean_abnormal_return ?? 0) >= 0;
                  return (
                    <tr
                      key={`${r.event_type}-${r.horizon_days}`}
                      className="border-b border-gray-100 last:border-0 hover:bg-indigo-50/40"
                    >
                      <td className="px-4 py-2.5">
                        <span className="block font-medium text-gray-900">
                          {info.label}
                        </span>
                        <span className="block font-mono text-[10px] text-gray-400">
                          {r.event_type}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-gray-600">
                        D+{r.horizon_days}
                      </td>
                      <td
                        className={`px-3 py-2.5 text-right font-mono font-medium ${
                          positive ? "text-emerald-600" : "text-red-600"
                        }`}
                      >
                        {formatPct(r.mean_abnormal_return)}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-gray-500">
                        {formatT(r.t_stat)}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-gray-500">
                        {formatP(r.p_value)}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-gray-500">
                        {r.count}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {allNegative && (
            <p className="text-xs leading-relaxed text-amber-700">
              {t("stats.signals.negativeNote")}
            </p>
          )}
        </>
      )}
    </section>
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
    {
      value: "significant_event_type",
      label: t("stats.backtest.model.significant_event_type"),
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
