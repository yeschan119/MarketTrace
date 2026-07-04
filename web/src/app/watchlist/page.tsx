"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { KoreanName } from "@/components/KoreanName";

export default function WatchlistPage() {
  const { t } = useI18n();
  const { token } = useAuth();
  const qc = useQueryClient();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api.listWatchlist(),
  });

  const remove = useMutation({
    mutationFn: (instrumentId: number) => api.removeWatchlist(instrumentId, token!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      qc.invalidateQueries({ queryKey: ["alerts"] });
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">
        {t("watchlist.title")}…
      </div>
    );
  }
  if (isError) {
    return (
      <div className="py-20 text-center text-red-600">
        {(error as Error)?.message ?? t("common.unknownError")}
      </div>
    );
  }

  const items = data ?? [];

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{t("watchlist.title")}</h1>
        <p className="text-sm text-gray-500">{t("watchlist.subtitle")}</p>
      </div>

      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 px-6 py-12 text-center text-gray-500">
          <p>{t("watchlist.empty")}</p>
          <p className="mt-2 text-sm">{t("watchlist.howToAdd")}</p>
          <Link
            href="/events"
            className="mt-4 inline-block rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            {t("watchlist.events")}
          </Link>
        </div>
      ) : (
        <ul className="divide-y divide-gray-100 overflow-hidden rounded-lg border border-gray-200 bg-white">
          {items.map((w) => (
            <li key={w.instrument_id} className="flex items-center gap-3 px-4 py-3">
              <Link
                href={`/instruments/${w.instrument_id}`}
                className="min-w-0 flex-1"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-semibold text-indigo-600">
                    {w.ticker}
                  </span>
                  <span className="truncate text-sm text-gray-900">
                    {w.name}
                    <KoreanName ticker={w.ticker} className="ml-1.5" />
                  </span>
                </div>
              </Link>
              {token && (
                <button
                  type="button"
                  onClick={() => remove.mutate(w.instrument_id)}
                  disabled={remove.isPending}
                  title={t("watch.watching")}
                  aria-label={t("watch.watching")}
                  className="flex-shrink-0 text-lg text-amber-500 transition-colors hover:text-amber-600 disabled:opacity-50"
                >
                  ★
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
