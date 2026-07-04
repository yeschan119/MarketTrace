"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { describeEventType } from "@/lib/eventTypes";
import { DirectionBadge } from "@/components/DirectionBadge";
import { InstrumentSignalCard } from "@/components/InstrumentSignalCard";

export default function InstrumentTimelinePage() {
  const { t, locale, lang } = useI18n();
  const params = useParams();
  const id = params.id as string;

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["instrument-timeline", id],
    queryFn: () => api.getInstrumentTimeline(id),
    enabled: Boolean(id),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">
        {t("instrument.loading")}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
        <p className="font-semibold">{t("instrument.failTitle")}</p>
        <p className="mt-1 text-sm">
          {error instanceof Error ? error.message : t("common.unknownError")}
        </p>
      </div>
    );
  }

  if (!data) {
    return null;
  }

  const { instrument, events } = data;

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-gray-500">
        <Link href="/events" className="hover:text-gray-700 hover:underline">
          {t("nav.events")}
        </Link>
        <span>/</span>
        <span className="text-gray-900">
          {instrument.ticker} — {instrument.name}
        </span>
      </nav>

      {/* Instrument Header */}
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100 font-mono text-sm font-bold text-indigo-700">
            {instrument.ticker.slice(0, 4)}
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{instrument.name}</h1>
            <p className="font-mono text-sm text-gray-500">{instrument.ticker}</p>
          </div>
        </div>
      </div>

      {/* Aggregate buy-decision signal for this instrument */}
      <InstrumentSignalCard events={events} />

      {/* Timeline */}
      <div>
        <h2 className="mb-4 text-lg font-semibold text-gray-800">
          {t("instrument.timeline")}
          <span className="ml-2 text-sm font-normal text-gray-500">
            {t("instrument.eventsCount", { n: events.length })}
          </span>
        </h2>

        {events.length === 0 ? (
          <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center text-gray-500">
            {t("instrument.empty")}
          </div>
        ) : (
          <div className="relative space-y-4 pl-6">
            {/* Timeline line */}
            <div className="absolute left-2 top-2 h-full w-0.5 bg-gray-200" />

            {events.map((event) => {
              const info = describeEventType(event.event_type, lang);
              return (
              <div key={event.id} className="relative">
                {/* Dot */}
                <div
                  className={`absolute -left-4 mt-1.5 h-3 w-3 rounded-full border-2 border-white shadow ${
                    event.direction === "positive"
                      ? "bg-emerald-400"
                      : event.direction === "negative"
                      ? "bg-red-400"
                      : "bg-gray-400"
                  }`}
                />

                <Link
                  href={`/events/${event.id}`}
                  className="block rounded-lg border border-gray-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="font-medium text-gray-900">
                        {info.label}
                      </p>
                      {info.desc && (
                        <p className="text-xs text-gray-500">{info.desc}</p>
                      )}
                      <p className="font-mono text-[10px] text-gray-400">
                        {event.event_type}
                      </p>
                      <p className="mt-0.5 text-xs text-gray-500">
                        {new Date(event.published_at).toLocaleDateString(locale, {
                          year: "numeric",
                          month: "short",
                          day: "numeric",
                        })}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <DirectionBadge direction={event.direction} />
                      <span className="text-xs text-gray-500">
                        {(event.confidence * 100).toFixed(0)}% {t("instrument.conf")}
                      </span>
                    </div>
                  </div>
                </Link>
              </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
