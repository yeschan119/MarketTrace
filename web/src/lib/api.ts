import type {
  EventSummary,
  EventDetail,
  EventTypeStat,
  InstrumentTimeline,
  LedgerStatement,
  MacroObservation,
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

async function apiPost<T>(
  path: string,
  body?: unknown,
  token?: string
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(url, {
    method: "POST",
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText} (${url})`);
  }
  return res.json() as Promise<T>;
}

async function apiPostForm<T>(
  path: string,
  body: FormData,
  token?: string
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(url, {
    method: "POST",
    headers,
    body,
  });
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

  getEventTypeStats(): Promise<EventTypeStat[]> {
    return apiFetch<EventTypeStat[]>("/stats/event-types");
  },

  getMacroObservations(): Promise<MacroObservation[]> {
    return apiFetch<MacroObservation[]>("/macro/observations");
  },

  login(username: string, password: string): Promise<{ token: string }> {
    return apiPost<{ token: string }>("/auth/login", { username, password });
  },

  ingest(token: string): Promise<{ status: string }> {
    return apiPost<{ status: string }>("/ingest", undefined, token);
  },

  getLedgerStatement(
    token: string,
    password?: string
  ): Promise<LedgerStatement> {
    return apiPost<LedgerStatement>(
      "/ledger/statement",
      { password: password || undefined },
      token
    );
  },

  uploadLedgerStatement(
    token: string,
    file: File,
    password?: string
  ): Promise<LedgerStatement> {
    const form = new FormData();
    form.append("file", file);
    if (password) form.append("password", password);
    return apiPostForm<LedgerStatement>("/ledger/statement/upload", form, token);
  },
};
