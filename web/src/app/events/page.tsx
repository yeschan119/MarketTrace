"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { useI18n, type Lang } from "@/lib/i18n";
import { describeEventType } from "@/lib/eventTypes";
import { DirectionBadge } from "@/components/DirectionBadge";
import { KoreanName } from "@/components/KoreanName";
import { WatchButton } from "@/components/WatchButton";
import { ValidatedSignalBadge } from "@/components/ValidatedSignalBadge";
import { koreanName } from "@/lib/instrumentNames";
import { assessSignal, type SignalVerdict } from "@/lib/validatedSignal";
import type { EventSummary } from "@/types/api";

type Market = "KR" | "US";
type SignalFilter = "all" | "conflict" | "needsReview" | "validated";

interface CompanyGroup {
  ticker: string;
  name: string;
  instrumentId: number | null;
  events: EventSummary[];
}

export default function EventsPage() {
  const { t, locale, lang } = useI18n();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["events"],
    queryFn: () => api.listEvents(),
  });

  const { data: significance } = useQuery({
    queryKey: ["significance"],
    queryFn: () => api.getEventTypeSignificance(),
  });

  const [market, setMarket] = useState<Market>("KR");
  const [signalFilter, setSignalFilter] = useState<SignalFilter>("all");
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const events = useMemo(() => data ?? [], [data]);

  // Validated-signal verdict per event, cached by (event_type, direction)
  // since those two fully determine the verdict at list granularity.
  const verdictFor = useMemo(() => {
    const cache = new Map<string, SignalVerdict>();
    return (event: EventSummary): SignalVerdict => {
      if (!significance) return "none";
      const key = `${event.event_type}|${event.direction}`;
      let v = cache.get(key);
      if (v === undefined) {
        v = assessSignal(significance, event.event_type, event.direction)
          .verdict;
        cache.set(key, v);
      }
      return v;
    };
  }, [significance]);

  const counts = useMemo(() => {
    let kr = 0;
    let us = 0;
    for (const event of events) {
      if (event.market === "KR") kr += 1;
      else if (event.market === "US") us += 1;
    }
    return { KR: kr, US: us };
  }, [events]);

  const groups = useMemo<CompanyGroup[]>(() => {
    const normalizedQuery = normalizeSearch(query);
    const byTicker = new Map<string, CompanyGroup>();
    for (const event of events) {
      if (event.market !== market) continue;
      if (signalFilter === "conflict" && verdictFor(event) !== "conflict")
        continue;
      // Review queue: conflicts a human hasn't corrected/confirmed yet.
      if (
        signalFilter === "needsReview" &&
        !(verdictFor(event) === "conflict" && !event.reviewed_at)
      )
        continue;
      if (signalFilter === "validated" && verdictFor(event) === "none")
        continue;
      if (
        normalizedQuery &&
        !eventMatchesQuery(event, normalizedQuery, lang)
      )
        continue;
      const key = event.primary_ticker ?? `event-${event.id}`;
      let group = byTicker.get(key);
      if (!group) {
        group = {
          ticker: event.primary_ticker ?? "N/A",
          name:
            event.instrument_name ??
            event.primary_ticker ??
            t("eventDetail.unknownInstrument"),
          instrumentId: event.primary_instrument_id,
          events: [],
        };
        byTicker.set(key, group);
      }
      group.events.push(event);
    }
    const result = Array.from(byTicker.values());
    for (const group of result) {
      group.events.sort(
        (a, b) =>
          new Date(b.published_at).getTime() -
          new Date(a.published_at).getTime(),
      );
    }
    result.sort((a, b) => b.events.length - a.events.length);
    return result;
  }, [events, lang, market, query, signalFilter, t, verdictFor]);

  const visibleEventCount = useMemo(
    () => groups.reduce((total, group) => total + group.events.length, 0),
    [groups],
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">
        {t("events.loading")}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
        <p className="font-semibold">{t("events.failTitle")}</p>
        <p className="mt-1 text-sm">
          {error instanceof Error ? error.message : t("common.unknownError")}
        </p>
        <p className="mt-2 text-xs text-red-500">
          {t("events.backendHint", {
            url:
              process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
          })}
        </p>
      </div>
    );
  }

  const toggle = (ticker: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  };

  const tabs: { key: Market; label: string; count: number }[] = [
    { key: "KR", label: t("events.tab.domestic"), count: counts.KR },
    { key: "US", label: t("events.tab.overseas"), count: counts.US },
  ];
  const hasSearchQuery = query.trim() !== "";
  const emptyMessageKey = hasSearchQuery
    ? "events.noneSearchResults"
    : signalFilter === "all"
      ? "events.noneInMarket"
      : "events.noneMatchFilter";

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">{t("events.title")}</h1>
        <span className="text-sm text-gray-500">
          {t("events.count", { n: events.length })}
        </span>
      </div>
      <p className="mb-6 text-sm text-gray-500">{t("events.expandHint")}</p>

      <div className="mb-4 max-w-xl">
        <label className="sr-only" htmlFor="event-search">
          {t("events.searchLabel")}
        </label>
        <input
          id="event-search"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("events.searchPlaceholder")}
          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
        <p className="mt-2 text-xs text-gray-400">
          {query.trim()
            ? t("events.searchCount", { n: visibleEventCount })
            : t("events.searchHint")}
        </p>
      </div>

      <div className="mb-6 flex flex-wrap gap-3">
        <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setMarket(tab.key)}
              className={`rounded-md px-4 py-2 text-sm font-semibold transition-colors ${
                market === tab.key
                  ? "bg-white text-indigo-600 shadow-sm"
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

        <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1">
          {(
            ["all", "conflict", "needsReview", "validated"] as SignalFilter[]
          ).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setSignalFilter(f)}
              className={`rounded-md px-3 py-2 text-sm font-semibold transition-colors ${
                signalFilter === f
                  ? "bg-white text-indigo-600 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {t(`events.signalFilter.${f}`)}
            </button>
          ))}
        </div>
      </div>

      {groups.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center text-gray-500">
          {t(emptyMessageKey)}
        </div>
      ) : (
        <div className="max-h-[70vh] space-y-3 overflow-y-auto pr-1">
          {groups.map((group) => {
            // Under an active filter/search, open groups so matches are visible.
            const isOpen =
              hasSearchQuery ||
              signalFilter !== "all" ||
              expanded.has(group.ticker);
            return (
              <div
                key={group.ticker}
                className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm"
              >
                <div className="flex items-center">
                  <button
                    type="button"
                    onClick={() => toggle(group.ticker)}
                    aria-expanded={isOpen}
                    className="flex min-w-0 flex-1 items-center justify-between gap-4 px-4 py-4 text-left transition-colors hover:bg-gray-50"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="font-mono text-sm font-semibold text-indigo-600">
                        {group.ticker}
                      </span>
                      <span className="truncate text-base font-medium text-gray-900">
                        {group.name}
                        <KoreanName ticker={group.ticker} className="ml-1.5" />
                      </span>
                    </div>
                    <div className="flex flex-shrink-0 items-center gap-3">
                      <span className="text-sm text-gray-500">
                        {t("events.companyEvents", { n: group.events.length })}
                      </span>
                      <svg
                        className={`h-5 w-5 text-gray-400 transition-transform ${
                          isOpen ? "rotate-180" : ""
                        }`}
                        fill="none"
                        viewBox="0 0 24 24"
                        strokeWidth={2}
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M19.5 8.25l-7.5 7.5-7.5-7.5"
                        />
                      </svg>
                    </div>
                  </button>
                  {group.instrumentId != null && (
                    <div className="flex-shrink-0 pr-3">
                      <WatchButton instrumentId={group.instrumentId} compact />
                    </div>
                  )}
                </div>

                {isOpen && (
                  <div className="max-h-96 divide-y divide-gray-100 overflow-y-auto border-t border-gray-200">
                    {group.events.map((event) => {
                      const info = describeEventType(event.event_type, lang);
                      return (
                      <div
                        key={event.id}
                        className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 transition-colors hover:bg-gray-50"
                      >
                        <div className="flex min-w-0 items-center gap-3">
                          <Link
                            href={`/events/${event.id}`}
                            className="min-w-0"
                            title={info.desc || undefined}
                          >
                            <span className="block text-sm font-medium text-indigo-600 hover:text-indigo-800 hover:underline">
                              {info.label}
                            </span>
                            {info.desc && (
                              <span className="block text-xs text-gray-500">
                                {info.desc}
                              </span>
                            )}
                            <span className="block font-mono text-[10px] text-gray-400">
                              {event.event_type}
                            </span>
                          </Link>
                          <DirectionBadge direction={event.direction} />
                          <ValidatedSignalBadge verdict={verdictFor(event)} />
                          {event.reviewed_at && (
                            <span
                              className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700"
                              title={t("events.reviewedMark")}
                            >
                              ✓ {t("events.reviewedMark")}
                            </span>
                          )}
                        </div>
                        <div className="flex flex-shrink-0 items-center gap-4 text-sm text-gray-500">
                          <span className="text-gray-600">
                            {(event.confidence * 100).toFixed(1)}%
                          </span>
                          <span>
                            {new Date(event.published_at).toLocaleDateString(
                              locale,
                            )}
                          </span>
                          <Link
                            href={`/events/${event.id}`}
                            className="font-mono text-xs text-indigo-600 hover:text-indigo-800"
                          >
                            {event.primary_ticker}
                          </Link>
                        </div>
                      </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function normalizeSearch(value: string): string {
  return value.trim().toLocaleLowerCase();
}

function eventMatchesQuery(
  event: EventSummary,
  normalizedQuery: string,
  lang: Lang,
): boolean {
  const typeInfo = describeEventType(event.event_type, lang);
  const fields = [
    event.primary_ticker,
    event.instrument_name,
    event.primary_ticker ? koreanName(event.primary_ticker) : null,
    event.event_type,
    typeInfo.label,
    typeInfo.desc,
    event.direction,
  ];
  return fields.some((field) =>
    field?.toLocaleLowerCase().includes(normalizedQuery),
  );
}
