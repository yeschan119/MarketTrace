"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { DirectionBadge } from "@/components/DirectionBadge";
import { AbnormalReturnChart } from "@/components/AbnormalReturnChart";
import { ScoreBars } from "@/components/ScoreBars";

export default function EventDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const { data: event, isLoading, isError, error } = useQuery({
    queryKey: ["event", id],
    queryFn: () => api.getEvent(id),
    enabled: Boolean(id),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">
        Loading event...
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
        <p className="font-semibold">Failed to load event</p>
        <p className="mt-1 text-sm">
          {error instanceof Error ? error.message : "Unknown error"}
        </p>
      </div>
    );
  }

  if (!event) {
    return null;
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-gray-500">
        <Link href="/events" className="hover:text-gray-700 hover:underline">
          Events
        </Link>
        <span>/</span>
        <span className="text-gray-900">{event.id}</span>
      </nav>

      {/* Header */}
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900">
                {event.entities[0] ?? "Unknown Instrument"}
              </h1>
              <DirectionBadge direction={event.direction} />
            </div>
            <p className="mt-1 text-sm text-gray-500">
              {event.event_type} &middot;{" "}
              {new Date(event.document.published_at).toLocaleDateString("en-US", {
                year: "numeric",
                month: "long",
                day: "numeric",
              })}
            </p>
            {event.entities.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {event.entities.map((e, idx) => (
                  <span
                    key={`${e}-${idx}`}
                    className="rounded-full bg-indigo-50 px-2.5 py-0.5 font-mono text-xs text-indigo-700"
                  >
                    {e}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="text-right text-sm text-gray-500">
            <p>Model: <span className="font-mono text-gray-700">{event.model}</span></p>
            <p>Version: <span className="font-mono text-gray-700">{event.model_version}</span></p>
          </div>
        </div>

        {/* Source document */}
        <div className="mt-4 rounded-md bg-gray-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            Source Document
          </p>
          <a
            href={event.document.url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-1 block text-sm font-medium text-indigo-600 hover:underline"
          >
            {event.document.title}
          </a>
          <p className="mt-0.5 text-xs text-gray-400">
            {event.document.source}
          </p>
        </div>
      </div>

      {/* Score Components */}
      <ScoreBars
        confidence={event.confidence}
        surprise_score={event.surprise_score}
        novelty_score={event.novelty_score}
        source_reliability={event.source_reliability}
      />

      {/* Abnormal Returns Chart */}
      <AbnormalReturnChart outcomes={event.outcomes} />

      {/* Evidence */}
      {event.evidence.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold text-gray-700">
            Supporting Evidence
          </h3>
          <ul className="space-y-3">
            {event.evidence.map((ev, idx) => (
              <li key={idx} className="rounded-md bg-gray-50 p-3 text-sm">
                <p className="text-gray-700">{ev}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Industries & Channels */}
      {(event.industries.length > 0 || event.channels.length > 0) && (
        <div className="grid grid-cols-2 gap-4">
          {event.industries.length > 0 && (
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
                Industries
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {event.industries.map((ind) => (
                  <span
                    key={ind}
                    className="rounded-full bg-blue-50 px-2.5 py-0.5 text-xs text-blue-700"
                  >
                    {ind}
                  </span>
                ))}
              </div>
            </div>
          )}
          {event.channels.length > 0 && (
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
                Channels
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {event.channels.map((ch) => (
                  <span
                    key={ch}
                    className="rounded-full bg-purple-50 px-2.5 py-0.5 text-xs text-purple-700"
                  >
                    {ch}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
