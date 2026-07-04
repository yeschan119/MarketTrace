"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { describeEventType } from "@/lib/eventTypes";
import type { EventSummary } from "@/types/api";

interface Factor {
  eventType: string;
  drift: number; // validated mean abnormal return (headline horizon)
  horizonDays: number;
  count: number; // occurrences of this type for this instrument
  latest: string; // most recent published_at
}

// Breaks a stock's events into upside vs. downside factors, grounded in the
// validated (statistically significant) drift of each event type it has seen.
export function InstrumentFactorsCard({ events }: { events: EventSummary[] }) {
  const { t, lang, locale } = useI18n();

  const { data: significance } = useQuery({
    queryKey: ["significance"],
    queryFn: () => api.getEventTypeSignificance(),
  });

  const { upside, downside } = useMemo(() => {
    const up: Factor[] = [];
    const down: Factor[] = [];
    if (!significance) return { upside: up, downside: down };

    // Group this instrument's events by type.
    const byType = new Map<string, EventSummary[]>();
    for (const e of events) {
      const arr = byType.get(e.event_type) ?? [];
      arr.push(e);
      byType.set(e.event_type, arr);
    }

    for (const [eventType, group] of byType) {
      // Validated headline for this type: significant + sufficient, lowest p.
      const headline = significance
        .filter(
          (r) =>
            r.event_type === eventType &&
            r.significant_5pct &&
            r.sufficient_sample,
        )
        .sort((a, b) => (a.p_value ?? 1) - (b.p_value ?? 1))[0];
      if (!headline || headline.mean_abnormal_return == null) continue;

      const latest = group
        .map((e) => e.published_at)
        .sort()
        .slice(-1)[0];
      const factor: Factor = {
        eventType,
        drift: headline.mean_abnormal_return,
        horizonDays: headline.horizon_days,
        count: group.length,
        latest,
      };
      (factor.drift < 0 ? down : up).push(factor);
    }

    up.sort((a, b) => b.drift - a.drift);
    down.sort((a, b) => a.drift - b.drift); // most negative first
    return { upside: up, downside: down };
  }, [significance, events]);

  if (upside.length === 0 && downside.length === 0) return null;

  const renderColumn = (factors: Factor[], positive: boolean) => (
    <div>
      <h3
        className={`mb-2 text-xs font-semibold uppercase tracking-wide ${
          positive ? "text-emerald-700" : "text-red-700"
        }`}
      >
        {t(positive ? "instrument.factors.upside" : "instrument.factors.downside")}
      </h3>
      {factors.length === 0 ? (
        <p className="rounded-md border border-dashed border-gray-200 px-3 py-4 text-center text-xs text-gray-400">
          {t("instrument.factors.none")}
        </p>
      ) : (
        <ul className="space-y-2">
          {factors.map((f) => (
            <li
              key={f.eventType}
              className="rounded-md border border-gray-100 bg-gray-50 px-3 py-2"
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-medium text-gray-900">
                  {describeEventType(f.eventType, lang).label}
                </span>
                <span
                  className={`font-mono text-sm font-semibold ${
                    positive ? "text-emerald-600" : "text-red-600"
                  }`}
                >
                  {(f.drift * 100).toFixed(1)}%
                </span>
              </div>
              <div className="mt-0.5 text-[11px] text-gray-500">
                {t("instrument.factors.detail", {
                  horizon: f.horizonDays,
                  count: f.count,
                  date: new Date(f.latest).toLocaleDateString(locale),
                })}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-bold text-gray-900">
        {t("instrument.factors.title")}
      </h2>
      <p className="mt-1 text-sm leading-relaxed text-gray-600">
        {t("instrument.factors.subtitle")}
      </p>
      <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {renderColumn(downside, false)}
        {renderColumn(upside, true)}
      </div>
    </div>
  );
}
