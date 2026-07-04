"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { assessSignal } from "@/lib/validatedSignal";
import type { EventSummary } from "@/types/api";

// Empirical "lean" for the instrument, aggregated from the validated drift of
// its events' types. Not a price prediction — a summary of what has
// historically followed this kind of news.
type Lean = "bearish" | "bullish" | "neutral" | "none";

const NEUTRAL_BAND = 0.005; // ±0.5% net drift counts as neutral

const leanStyles: Record<Lean, string> = {
  bearish: "border-amber-300 bg-amber-50 text-amber-800",
  bullish: "border-emerald-200 bg-emerald-50 text-emerald-800",
  neutral: "border-gray-200 bg-gray-50 text-gray-600",
  none: "border-gray-200 bg-gray-50 text-gray-500",
};

export function InstrumentSignalCard({ events }: { events: EventSummary[] }) {
  const { t } = useI18n();

  const { data: significance } = useQuery({
    queryKey: ["significance"],
    queryFn: () => api.getEventTypeSignificance(),
  });

  const agg = useMemo(() => {
    if (!significance) return null;
    let validated = 0;
    let conflicts = 0;
    let unreviewedConflicts = 0;
    const drifts: number[] = [];

    for (const e of events) {
      const a = assessSignal(significance, e.event_type, e.direction);
      if (a.verdict === "none" || !a.headline) continue;
      validated += 1;
      if (a.headline.mean_abnormal_return != null) {
        drifts.push(a.headline.mean_abnormal_return);
      }
      if (a.verdict === "conflict") {
        conflicts += 1;
        if (!e.reviewed_at) unreviewedConflicts += 1;
      }
    }

    const netDrift = drifts.length
      ? drifts.reduce((s, v) => s + v, 0) / drifts.length
      : null;
    const lean: Lean =
      netDrift == null
        ? "none"
        : netDrift < -NEUTRAL_BAND
          ? "bearish"
          : netDrift > NEUTRAL_BAND
            ? "bullish"
            : "neutral";

    return { validated, conflicts, unreviewedConflicts, netDrift, lean };
  }, [significance, events]);

  if (!agg) return null;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-bold text-gray-900">
          {t("instrument.signal.title")}
        </h2>
        <span className="text-xs text-gray-500">
          {t("instrument.signal.basis", { n: agg.validated })}
        </span>
      </div>
      <p className="mt-1 text-sm leading-relaxed text-gray-600">
        {t("instrument.signal.subtitle")}
      </p>

      {agg.validated === 0 ? (
        <div className="mt-3 flex h-20 items-center justify-center rounded-md border border-dashed border-gray-200 text-sm text-gray-500">
          {t("instrument.signal.none")}
        </div>
      ) : (
        <>
          <div
            className={`mt-3 rounded-md border px-4 py-3 text-sm font-semibold ${leanStyles[agg.lean]}`}
          >
            {t(`instrument.signal.lean.${agg.lean}`)}
          </div>

          <div className="mt-3 grid grid-cols-3 gap-3 text-center">
            <div className="rounded-md bg-gray-50 px-2 py-2.5">
              <div className="font-mono text-lg font-semibold text-gray-900">
                {agg.netDrift == null
                  ? "—"
                  : `${(agg.netDrift * 100).toFixed(1)}%`}
              </div>
              <div className="mt-0.5 text-[11px] text-gray-500">
                {t("instrument.signal.netDrift")}
              </div>
            </div>
            <div className="rounded-md bg-gray-50 px-2 py-2.5">
              <div className="font-mono text-lg font-semibold text-gray-900">
                {agg.validated}
              </div>
              <div className="mt-0.5 text-[11px] text-gray-500">
                {t("instrument.signal.validatedEvents")}
              </div>
            </div>
            <div className="rounded-md bg-gray-50 px-2 py-2.5">
              <div className="font-mono text-lg font-semibold text-gray-900">
                {agg.conflicts}
                {agg.unreviewedConflicts > 0 && (
                  <span className="ml-1 text-xs font-normal text-amber-600">
                    ({agg.unreviewedConflicts})
                  </span>
                )}
              </div>
              <div className="mt-0.5 text-[11px] text-gray-500">
                {t("instrument.signal.conflicts")}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
