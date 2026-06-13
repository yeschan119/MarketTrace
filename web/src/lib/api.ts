import type {
  EventSummary,
  EventDetail,
  InstrumentTimeline,
  HealthResponse,
} from "@/types/api";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText} (${url})`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health(): Promise<HealthResponse> {
    return apiFetch<HealthResponse>("/health");
  },

  listEvents(): Promise<EventSummary[]> {
    return apiFetch<EventSummary[]>("/events");
  },

  getEvent(id: string): Promise<EventDetail> {
    return apiFetch<EventDetail>(`/events/${id}`);
  },

  getInstrumentTimeline(id: string): Promise<InstrumentTimeline> {
    return apiFetch<InstrumentTimeline>(`/instruments/${id}/timeline`);
  },
};
