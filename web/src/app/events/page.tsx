"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { DirectionBadge } from "@/components/DirectionBadge";

export default function EventsPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["events"],
    queryFn: () => api.listEvents(),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">
        Loading events...
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
        <p className="font-semibold">Failed to load events</p>
        <p className="mt-1 text-sm">
          {error instanceof Error ? error.message : "Unknown error"}
        </p>
        <p className="mt-2 text-xs text-red-500">
          Make sure the backend is running at{" "}
          {process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}
        </p>
      </div>
    );
  }

  const events = data ?? [];

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Market Events</h1>
        <span className="text-sm text-gray-500">{events.length} events</span>
      </div>

      {events.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center text-gray-500">
          No events found. Run the pipeline to ingest disclosures.
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Ticker
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Instrument
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Event Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Direction
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Confidence
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Published
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {events.map((event) => (
                <tr
                  key={event.id}
                  className="transition-colors hover:bg-gray-50"
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/events/${event.id}`}
                      className="font-mono text-sm font-semibold text-indigo-600 hover:text-indigo-800"
                    >
                      {event.primary_ticker}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">
                    <Link href={`/events/${event.id}`} className="hover:underline">
                      {event.instrument_name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {event.event_type}
                  </td>
                  <td className="px-4 py-3">
                    <DirectionBadge direction={event.direction} />
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {(event.confidence * 100).toFixed(1)}%
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {new Date(event.published_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
