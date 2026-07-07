"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { KoreanName } from "@/components/KoreanName";

export default function InstrumentSearchPage() {
  const { t } = useI18n();
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");

  // Debounce the input so we don't fire a request on every keystroke.
  useEffect(() => {
    const handle = setTimeout(() => setQ(input.trim()), 250);
    return () => clearTimeout(handle);
  }, [input]);

  const { data, isFetching, isError, error } = useQuery({
    queryKey: ["instrument-search", q],
    queryFn: () => api.searchInstruments(q),
    enabled: q.length > 0,
  });

  const results = q.length > 0 ? data ?? [] : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{t("search.title")}</h1>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-gray-600">
          {t("search.subtitle")}
        </p>
      </div>

      <input
        type="search"
        autoFocus
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder={t("search.placeholder")}
        className="w-full max-w-xl rounded-lg border border-gray-300 px-4 py-2.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
      />

      {isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error instanceof Error ? error.message : t("common.unknownError")}
        </div>
      ) : q.length === 0 ? (
        <p className="text-sm text-gray-400">{t("search.hint")}</p>
      ) : isFetching && results.length === 0 ? (
        <p className="text-sm text-gray-500">{t("search.searching")}</p>
      ) : results.length === 0 ? (
        <p className="text-sm text-gray-500">{t("search.noResults", { q })}</p>
      ) : (
        <ul className="divide-y divide-gray-100 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
          {results.map((r) => (
            <li key={r.id}>
              <Link
                href={`/instruments/${r.id}`}
                className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-gray-50"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-medium text-indigo-600">
                      {r.ticker}
                    </span>
                    <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-xs text-gray-500">
                      {r.market}
                    </span>
                  </div>
                  <div className="truncate text-xs text-gray-500">
                    {r.name}
                    <KoreanName ticker={r.ticker} className="ml-1" />
                    {r.industry ? (
                      <span className="ml-2 text-gray-400">· {r.industry}</span>
                    ) : null}
                  </div>
                </div>
                <span className="shrink-0 text-xs text-gray-400">
                  {r.event_count > 0
                    ? t("search.eventsCount", { count: r.event_count })
                    : t("search.noEvents")}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
