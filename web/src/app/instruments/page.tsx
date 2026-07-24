"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { api, isApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { KoreanName } from "@/components/KoreanName";
import type { InstrumentAnalyzeRequest, InstrumentSearchResult } from "@/types/api";

type Market = "KR" | "US";

export default function InstrumentSearchPage() {
  const { t } = useI18n();
  const { token, logout } = useAuth();
  const queryClient = useQueryClient();
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [market, setMarket] = useState<Market>("KR");
  const [ticker, setTicker] = useState("");
  const [name, setName] = useState("");
  const [notice, setNotice] = useState("");

  // Debounce the input so we don't fire a request on every keystroke.
  useEffect(() => {
    const handle = setTimeout(() => setQ(input.trim()), 250);
    return () => clearTimeout(handle);
  }, [input]);

  useEffect(() => {
    if (!q) return;
    const inferred = inferTicker(q, market);
    setTicker(inferred);
    if (!inferred) setName(q);
  }, [q, market]);

  const { data, isFetching, isError, error } = useQuery({
    queryKey: ["instrument-search", q],
    queryFn: () => api.searchInstruments(q),
    enabled: q.length > 0,
  });

  const results = q.length > 0 ? data ?? [] : [];

  const analyzeMutation = useMutation({
    mutationFn: (request: InstrumentAnalyzeRequest) => {
      if (!token) throw new Error(t("search.loginRequired"));
      return api.analyzeInstrument(request, token);
    },
    onSuccess: (response) => {
      setNotice(t("search.analyzeStarted", { ticker: response.ticker }));
      queryClient.invalidateQueries({ queryKey: ["instrument-search"] });
      queryClient.invalidateQueries({ queryKey: ["events"] });
    },
    onError: (error) => {
      if (isApiError(error) && error.status === 401) {
        logout();
      }
    },
  });

  const startAnalyze = (request: InstrumentAnalyzeRequest) => {
    const cleanTicker = request.ticker?.trim() || undefined;
    const cleanName = request.name?.trim() || undefined;
    if (!cleanTicker && !cleanName) return;
    setNotice("");
    analyzeMutation.mutate({
      ...request,
      ticker: cleanTicker,
      name: cleanName,
      max_filings: request.max_filings ?? 10,
    });
  };

  const startAnalyzeForResult = (result: InstrumentSearchResult) => {
    startAnalyze({
      market: result.market === "US" ? "US" : "KR",
      ticker: result.ticker,
      name: result.name,
      industry: result.industry,
    });
  };

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
        <div className="space-y-4">
          <p className="text-sm text-gray-500">{t("search.noResults", { q })}</p>
          <AnalyzePanel
            market={market}
            setMarket={setMarket}
            ticker={ticker}
            setTicker={setTicker}
            name={name}
            setName={setName}
            disabled={
              !token || analyzeMutation.isPending || !(ticker.trim() || name.trim())
            }
            pending={analyzeMutation.isPending}
            onSubmit={() =>
              startAnalyze({
                market,
                ticker,
                name,
              })
            }
            t={t}
          />
        </div>
      ) : (
        <ul className="divide-y divide-gray-100 overflow-hidden rounded-lg border border-gray-200 bg-surface shadow-sm">
          {results.map((r) => (
            <li key={r.id}>
              <div className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-gray-50">
                <Link href={`/instruments/${r.id}`} className="min-w-0 flex-1">
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
                </Link>
                <div className="flex shrink-0 items-center gap-3">
                  <span className="text-xs text-gray-400">
                    {r.event_count > 0
                      ? t("search.eventsCount", { count: r.event_count })
                      : t("search.noEvents")}
                  </span>
                  <button
                    type="button"
                    disabled={!token || analyzeMutation.isPending}
                    onClick={() => startAnalyzeForResult(r)}
                    className="rounded-md border border-indigo-200 px-3 py-1.5 text-xs font-semibold text-indigo-600 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:border-gray-200 disabled:text-gray-300"
                    title={!token ? t("search.loginRequired") : undefined}
                  >
                    {analyzeMutation.isPending
                      ? t("search.analyzing")
                      : t("search.analyzeButton")}
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {notice && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700">
          {notice}
        </div>
      )}
      {analyzeMutation.isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {formatAnalyzeError(analyzeMutation.error, t)}
        </div>
      )}
    </div>
  );
}

function AnalyzePanel({
  market,
  setMarket,
  ticker,
  setTicker,
  name,
  setName,
  disabled,
  pending,
  onSubmit,
  t,
}: {
  market: Market;
  setMarket: (market: Market) => void;
  ticker: string;
  setTicker: (ticker: string) => void;
  name: string;
  setName: (name: string) => void;
  disabled: boolean;
  pending: boolean;
  onSubmit: () => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}) {
  return (
    <div className="max-w-xl rounded-lg border border-gray-200 bg-surface p-4 shadow-sm">
      <div className="mb-3 flex rounded-lg border border-gray-200 bg-gray-50 p-1">
        {(["KR", "US"] as Market[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMarket(m)}
            className={`flex-1 rounded-md px-3 py-2 text-sm font-semibold ${
              market === m
                ? "bg-surface text-indigo-600 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {m}
          </button>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-xs font-medium text-gray-500">
          {t("search.tickerLabel")}
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </label>
        <label className="text-xs font-medium text-gray-500">
          {t("search.nameLabel")}
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("search.namePlaceholder")}
            className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </label>
      </div>
      <button
        type="button"
        disabled={disabled}
        onClick={onSubmit}
        className="mt-4 rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-gray-300"
        title={disabled ? t("search.loginRequired") : undefined}
      >
        {pending ? t("search.analyzing") : t("search.analyzeButton")}
      </button>
    </div>
  );
}

function inferTicker(query: string, market: Market): string {
  const trimmed = query.trim();
  if (market === "KR") {
    return /^\d{1,6}$/.test(trimmed) ? trimmed.padStart(6, "0") : "";
  }
  return /^[A-Za-z.]{1,10}$/.test(trimmed) ? trimmed.toUpperCase() : "";
}

function formatAnalyzeError(
  error: unknown,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  if (isApiError(error)) {
    if (error.status === 401) return t("search.sessionExpired");
    if (error.status === 404) return t("search.noListedCompany");
    if (error.status === 503) return t("search.providerUnavailable");
  }
  return error instanceof Error ? error.message : t("search.analyzeFailed");
}
