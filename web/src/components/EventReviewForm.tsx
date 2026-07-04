"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, isApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { describeEventType, EVENT_TYPE_CODES } from "@/lib/eventTypes";
import type { EventDetail, EventUpdate } from "@/types/api";

const DIRECTIONS = ["positive", "negative", "neutral"];

export function EventReviewForm({ event }: { event: EventDetail }) {
  const { t, lang, locale } = useI18n();
  const { token, logout } = useAuth();
  const queryClient = useQueryClient();

  const [direction, setDirection] = useState(event.direction);
  const [eventType, setEventType] = useState(event.event_type);
  const [confidence, setConfidence] = useState(event.confidence);
  const [error, setError] = useState<string | null>(null);

  // Ensure the event's own code is selectable even if outside the known set.
  const typeOptions = EVENT_TYPE_CODES.includes(event.event_type)
    ? EVENT_TYPE_CODES
    : [event.event_type, ...EVENT_TYPE_CODES];

  const mutation = useMutation({
    mutationFn: (patch: EventUpdate) =>
      api.updateEvent(String(event.id), patch, token as string),
    onSuccess: (updated) => {
      setError(null);
      queryClient.setQueryData(["event", String(event.id)], updated);
      // A direction/type edit shifts the impact aggregates the list and stats read.
      queryClient.invalidateQueries({ queryKey: ["events"] });
      queryClient.invalidateQueries({ queryKey: ["significance"] });
    },
    onError: (err) => {
      if (isApiError(err) && err.status === 401) {
        logout();
        setError(t("eventDetail.review.sessionExpired"));
        return;
      }
      setError(t("eventDetail.review.failed"));
    },
  });

  const dirty =
    direction !== event.direction ||
    eventType !== event.event_type ||
    confidence !== event.confidence;

  function handleSave() {
    const patch: EventUpdate = {};
    if (direction !== event.direction) patch.direction = direction;
    if (eventType !== event.event_type) patch.event_type = eventType;
    if (confidence !== event.confidence) patch.confidence = confidence;
    if (Object.keys(patch).length > 0) mutation.mutate(patch);
  }

  // Public transparency: show a "corrected" note whenever the event was
  // reviewed, even for logged-out viewers.
  const correctedNote = event.reviewed_at ? (
    <p className="text-xs leading-relaxed text-amber-700">
      {t("eventDetail.review.reviewedAt", {
        date: new Date(event.reviewed_at).toLocaleDateString(locale),
      })}
      {event.original_direction &&
        event.original_direction !== event.direction && (
          <>
            {" · "}
            {t("eventDetail.review.direction")}: {t(`direction.${event.original_direction}`)}
            {" → "}
            {t(`direction.${event.direction}`)}
          </>
        )}
      {event.original_event_type &&
        event.original_event_type !== event.event_type && (
          <>
            {" · "}
            {t("eventDetail.review.eventType")}:{" "}
            {describeEventType(event.original_event_type, lang).label}
            {" → "}
            {describeEventType(event.event_type, lang).label}
          </>
        )}
    </p>
  ) : null;

  if (!token) {
    // Logged-out: only surface the transparency note (no edit controls).
    return correctedNote ? (
      <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-4 shadow-sm">
        {correctedNote}
      </div>
    ) : null;
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-gray-700">
        {t("eventDetail.review.title")}
      </h3>
      <p className="mt-1 text-xs leading-relaxed text-gray-500">
        {t("eventDetail.review.subtitle")}
      </p>
      {correctedNote && <div className="mt-2">{correctedNote}</div>}

      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-gray-500">
            {t("eventDetail.review.direction")}
          </span>
          <select
            value={direction}
            onChange={(e) => setDirection(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm"
          >
            {DIRECTIONS.map((d) => (
              <option key={d} value={d}>
                {t(`direction.${d}`)}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1 block text-xs font-medium text-gray-500">
            {t("eventDetail.review.eventType")}
          </span>
          <select
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm"
          >
            {typeOptions.map((code) => (
              <option key={code} value={code}>
                {describeEventType(code, lang).label}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1 block text-xs font-medium text-gray-500">
            {t("eventDetail.review.confidence")}
          </span>
          <input
            type="number"
            min={0}
            max={1}
            step={0.01}
            value={confidence}
            onChange={(e) => setConfidence(Number(e.target.value))}
            className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm"
          />
        </label>
      </div>

      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}

      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={!dirty || mutation.isPending}
          className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-gray-300"
        >
          {mutation.isPending
            ? t("eventDetail.review.saving")
            : t("eventDetail.review.save")}
        </button>
        {!dirty && !mutation.isPending && (
          <span className="text-xs text-gray-400">
            {t("eventDetail.review.noChanges")}
          </span>
        )}
      </div>
    </div>
  );
}
