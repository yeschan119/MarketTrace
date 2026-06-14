"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { EventTypeStat } from "@/types/api";

function formatPct(v: number | null): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(2)}%`;
}

export default function StatsPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["event-type-stats"],
    queryFn: () => api.getEventTypeStats(),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">
        Loading statistics...
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
        <p className="font-semibold">Failed to load statistics</p>
        <p className="mt-1 text-sm">
          {error instanceof Error ? error.message : "Unknown error"}
        </p>
      </div>
    );
  }

  const stats: EventTypeStat[] = data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Event-Type Reaction Stats</h1>
        <span className="text-sm text-gray-500">{stats.length} buckets</span>
      </div>
      <p className="text-sm text-gray-500">
        Mean and dispersion of market-adjusted abnormal returns, grouped by event
        type and post-announcement horizon (trading days).
      </p>

      {stats.length === 0 ? (
        <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-gray-300 text-sm text-gray-500">
          No statistics yet — ingest some events first.
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                <th className="px-4 py-3">Event Type</th>
                <th className="px-4 py-3">Horizon</th>
                <th className="px-4 py-3 text-right">Samples</th>
                <th className="px-4 py-3 text-right">Mean Abnormal Return</th>
                <th className="px-4 py-3 text-right">Std Dev</th>
              </tr>
            </thead>
            <tbody>
              {stats.map((s) => {
                const positive = (s.mean_abnormal_return ?? 0) >= 0;
                return (
                  <tr
                    key={`${s.event_type}-${s.horizon_days}`}
                    className="border-b border-gray-100 last:border-0 hover:bg-gray-50"
                  >
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {s.event_type}
                    </td>
                    <td className="px-4 py-3 font-mono text-gray-600">
                      D+{s.horizon_days}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600">{s.count}</td>
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
      )}
    </div>
  );
}
