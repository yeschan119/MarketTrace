"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { DirectionBadge } from "@/components/DirectionBadge";
import type { EventSummary } from "@/types/api";

type Market = "KR" | "US";

interface CompanyGroup {
  ticker: string;
  name: string;
  events: EventSummary[];
}

export default function EventsPage() {
  const { t, locale } = useI18n();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["events"],
    queryFn: () => api.listEvents(),
  });

  const [market, setMarket] = useState<Market>("KR");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const events = useMemo(() => data ?? [], [data]);

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
    const byTicker = new Map<string, CompanyGroup>();
    for (const event of events) {
      if (event.market !== market) continue;
      const key = event.primary_ticker;
      let group = byTicker.get(key);
      if (!group) {
        group = {
          ticker: event.primary_ticker,
          name: event.instrument_name,
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
  }, [events, market]);

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

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">{t("events.title")}</h1>
        <span className="text-sm text-gray-500">
          {t("events.count", { n: events.length })}
        </span>
      </div>
      <p className="mb-6 text-sm text-gray-500">{t("events.expandHint")}</p>

      <div className="mb-6 inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1">
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

      {groups.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center text-gray-500">
          {t("events.noneInMarket")}
        </div>
      ) : (
        <div className="space-y-3">
          {groups.map((group) => {
            const isOpen = expanded.has(group.ticker);
            return (
              <div
                key={group.ticker}
                className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm"
              >
                <button
                  type="button"
                  onClick={() => toggle(group.ticker)}
                  aria-expanded={isOpen}
                  className="flex w-full items-center justify-between gap-4 px-4 py-4 text-left transition-colors hover:bg-gray-50"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="font-mono text-sm font-semibold text-indigo-600">
                      {group.ticker}
                    </span>
                    <span className="truncate text-base font-medium text-gray-900">
                      {group.name}
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

                {isOpen && (
                  <div className="divide-y divide-gray-100 border-t border-gray-200">
                    {group.events.map((event) => (
                      <div
                        key={event.id}
                        className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 transition-colors hover:bg-gray-50"
                      >
                        <div className="flex min-w-0 items-center gap-3">
                          <Link
                            href={`/events/${event.id}`}
                            className="text-sm font-medium text-indigo-600 hover:text-indigo-800 hover:underline"
                          >
                            {event.event_type}
                          </Link>
                          <DirectionBadge direction={event.direction} />
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
                    ))}
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
