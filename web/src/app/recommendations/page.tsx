"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { describeEventType } from "@/lib/eventTypes";
import { useI18n, type Lang } from "@/lib/i18n";
import { KoreanName } from "@/components/KoreanName";
import { WatchButton } from "@/components/WatchButton";
import type { DrawdownScreenerRow } from "@/types/api";

const TRUE_DROP_THRESHOLD = -0.15;
const RELATIVE_DROP_THRESHOLD = 0;
const FETCH_LIMIT = 200;
const MAX_RELATIVE_ROWS = 5;

type RecommendationLevel = "first_pick" | "check" | "avoid";

type Recommendation = DrawdownScreenerRow & {
  level: RecommendationLevel;
  reasons: string[];
  isRelativeFallback: boolean;
};

type RecommendationMarket = "domestic" | "overseas";

const levelStyles: Record<RecommendationLevel, string> = {
  first_pick: "border-emerald-200 bg-emerald-50 text-emerald-800",
  check: "border-sky-200 bg-sky-50 text-sky-800",
  avoid: "border-amber-200 bg-amber-50 text-amber-800",
};

function pct(value: number): string {
  return `${Math.abs(value * 100).toFixed(1)}`;
}

function price(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function plainEventLabel(eventType: string, lang: Lang): string {
  return describeEventType(eventType, lang).label
    .replace(/어닝\s*서프라이즈/g, "예상보다 좋은 실적")
    .replace(/서프라이즈/g, "예상 밖 변화")
    .replace(/Surprise/gi, "Unexpected result")
    .replace(/Weighted drift/gi, "past pattern");
}

function recommendationLevel(row: DrawdownScreenerRow): RecommendationLevel {
  if (row.is_stale || row.diagnosis === "persistent_risk") return "avoid";
  if (row.diagnosis === "possible_overreaction") return "first_pick";
  return "check";
}

function buildReasons(
  row: DrawdownScreenerRow,
  lang: Lang,
  t: (key: string, vars?: Record<string, string | number>) => string,
  isRelativeFallback: boolean
): string[] {
  const reasons = [
    t(
      isRelativeFallback
        ? "recommendations.reason.relativeDrop"
        : "recommendations.reason.deepDrop",
      { drop: pct(row.drawdown) }
    ),
    row.is_stale
      ? t("recommendations.reason.stalePrice")
      : t("recommendations.reason.freshPrice"),
  ];

  if (row.diagnosis === "possible_overreaction") {
    reasons.push(t("recommendations.reason.possibleOverreaction"));
  } else if (row.diagnosis === "persistent_risk") {
    reasons.push(t("recommendations.reason.persistentRisk"));
  } else {
    reasons.push(t("recommendations.reason.unexplained"));
  }

  if (row.recent_event_count > 0) {
    reasons.push(
      t("recommendations.reason.recentEvents", { count: row.recent_event_count })
    );
  }

  if (row.top_factor) {
    const label = plainEventLabel(row.top_factor.event_type, lang);
    reasons.push(
      row.top_factor.drift < 0
        ? t("recommendations.reason.factorBad", { label })
        : t("recommendations.reason.factorGood", { label })
    );
  }

  return reasons;
}

function marketMatches(row: DrawdownScreenerRow, market: RecommendationMarket): boolean {
  return market === "domestic" ? row.market === "KR" : row.market !== "KR";
}

function recommendForMarket(
  sourceRows: DrawdownScreenerRow[],
  market: RecommendationMarket,
  lang: Lang,
  t: (key: string, vars?: Record<string, string | number>) => string
): Recommendation[] {
  const marketRows = sourceRows
    .filter((row) => marketMatches(row, market))
    .sort((a, b) => a.drawdown - b.drawdown || a.ticker.localeCompare(b.ticker));
  const trueDrops = marketRows.filter(
    (row) => row.drawdown <= TRUE_DROP_THRESHOLD
  );
  const selected = trueDrops.length > 0 ? trueDrops : marketRows.slice(0, MAX_RELATIVE_ROWS);
  const isRelativeFallback = trueDrops.length === 0;

  return selected.map((row) => ({
    ...row,
    level: recommendationLevel(row),
    reasons: buildReasons(row, lang, t, isRelativeFallback),
    isRelativeFallback,
  }));
}

function RecommendationCard({
  row,
  rank,
  t,
}: {
  row: Recommendation;
  rank: number;
  t: (key: string, vars?: Record<string, string | number>) => string;
}) {
  return (
    <article className="rounded-lg border border-gray-200 bg-surface p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-gray-400">#{rank}</span>
            <WatchButton instrumentId={row.instrument_id} compact />
            <Link
              href={`/instruments/${row.instrument_id}`}
              className="font-mono text-lg font-semibold text-indigo-600 hover:underline"
            >
              {row.ticker}
            </Link>
            <span
              className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${levelStyles[row.level]}`}
            >
              {t(`recommendations.level.${row.level}`)}
            </span>
          </div>
          <div className="mt-1 text-sm text-gray-600">
            {row.name}
            <KoreanName ticker={row.ticker} className="ml-1" />
          </div>
        </div>

        <div className="text-right text-sm">
          <div className="font-semibold text-amber-700">-{pct(row.drawdown)}%</div>
          <div className="mt-1 text-xs text-gray-500">
            {t("recommendations.priceLabel")}: {price(row.current_price)} /{" "}
            {price(row.high_price)}
          </div>
          <div className="text-xs text-gray-400">
            {t("recommendations.asOf", { date: row.latest_date })}
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-[1fr_160px]">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">
            {t("recommendations.reasonTitle")}
          </h3>
          <ul className="mt-2 space-y-1.5 text-sm leading-relaxed text-gray-700">
            {row.reasons.map((reason) => (
              <li key={reason} className="flex gap-2">
                <span className="mt-2 h-1.5 w-1.5 flex-none rounded-full bg-gray-400" />
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="flex flex-col items-start gap-3 md:items-end">
          <span className="rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs text-gray-600">
            {row.recent_event_count > 0
              ? t("recommendations.recentEvents", {
                  count: row.recent_event_count,
                })
              : t("recommendations.noRecentEvents")}
          </span>
          <Link
            href={`/instruments/${row.instrument_id}`}
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            {t("recommendations.viewStock")}
          </Link>
        </div>
      </div>
    </article>
  );
}

function RecommendationSection({
  market,
  rows,
  isActive,
  t,
}: {
  market: RecommendationMarket;
  rows: Recommendation[];
  isActive: boolean;
  t: (key: string, vars?: Record<string, string | number>) => string;
}) {
  const isRelativeFallback = rows[0]?.isRelativeFallback ?? true;

  return (
    <section className={`space-y-3 ${isActive ? "" : "hidden"}`}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            {t(`recommendations.section.${market}`)}
          </h2>
          <p className="text-xs text-gray-500">
            {t(`recommendations.section.${market}Desc`)}
          </p>
          <p className="mt-1 text-xs text-gray-400">
            {t(
              isRelativeFallback
                ? "recommendations.section.relativeMode"
                : "recommendations.section.trueDropMode"
            )}
          </p>
        </div>
        <span className="text-xs text-gray-400">
          {t("recommendations.section.count", { count: rows.length })}
        </span>
      </div>

      {rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-8 text-center text-sm text-gray-500">
          {t(`recommendations.section.${market}Empty`)}
        </div>
      ) : (
        <div className="space-y-3">
          {rows.map((row, index) => (
            <RecommendationCard
              key={row.instrument_id}
              row={row}
              rank={index + 1}
              t={t}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export default function RecommendationsPage() {
  const { t, lang } = useI18n();
  const [market, setMarket] = useState<RecommendationMarket>("domestic");
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["recommendations", RELATIVE_DROP_THRESHOLD, FETCH_LIMIT],
    queryFn: () =>
      api.getDrawdownScreener(RELATIVE_DROP_THRESHOLD, false, FETCH_LIMIT),
  });

  const rowsByMarket: Record<RecommendationMarket, Recommendation[]> = useMemo(() => {
    const rows = data ?? [];
    return {
      domestic: recommendForMarket(rows, "domestic", lang, t),
      overseas: recommendForMarket(rows, "overseas", lang, t),
    };
  }, [data, lang, t]);
  const totalRows = rowsByMarket.domestic.length + rowsByMarket.overseas.length;
  const tabs: { key: RecommendationMarket; label: string; count: number }[] = [
    {
      key: "domestic",
      label: t("recommendations.section.domestic"),
      count: rowsByMarket.domestic.length,
    },
    {
      key: "overseas",
      label: t("recommendations.section.overseas"),
      count: rowsByMarket.overseas.length,
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          {t("recommendations.title")}
        </h1>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-gray-600">
          {t("recommendations.subtitle")}
        </p>
        <p className="mt-2 text-xs text-gray-400">
          {t("recommendations.sourceNote")}
        </p>
      </div>

      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm leading-relaxed text-amber-900">
        {t("recommendations.disclaimer")}
      </div>

      {isLoading ? (
        <div className="py-16 text-center text-gray-500">
          {t("recommendations.loading")}
        </div>
      ) : isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
          <p className="font-semibold">{t("recommendations.failTitle")}</p>
          <p className="mt-1 text-sm">
            {error instanceof Error ? error.message : t("common.unknownError")}
          </p>
        </div>
      ) : totalRows === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center text-gray-500">
          {t("recommendations.empty")}
        </div>
      ) : (
        <div className="space-y-6">
          <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setMarket(tab.key)}
                className={`rounded-md px-4 py-2 text-sm font-semibold transition-colors ${
                  market === tab.key
                    ? "bg-surface text-indigo-600 shadow-sm"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                {tab.label}
                <span className="ml-2 text-xs font-normal text-gray-400">
                  {tab.count}
                </span>
              </button>
            ))}
          </div>
          <RecommendationSection
            market="domestic"
            rows={rowsByMarket.domestic}
            isActive={market === "domestic"}
            t={t}
          />
          <RecommendationSection
            market="overseas"
            rows={rowsByMarket.overseas}
            isActive={market === "overseas"}
            t={t}
          />
        </div>
      )}
    </div>
  );
}
