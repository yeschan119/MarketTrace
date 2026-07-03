import type {
  BacktestModel,
  BacktestResult,
  EventContribution,
  EventSummary,
  EventDetail,
  EventTypeStat,
  EventTypeSignificance,
  InstrumentTimeline,
  LedgerCategory,
  LedgerEntry,
  LedgerStatement,
  LedgerStatementSummary,
  PassbookCategory,
  PassbookDirection,
  PassbookEntry,
  PassbookStatement,
  PassbookStatementSummary,
  MacroObservation,
  MacroSeriesBacktest,
  HealthResponse,
} from "@/types/api";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly url: string,
    public readonly detail: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

async function buildApiError(res: Response, url: string): Promise<ApiError> {
  let detail = "";
  try {
    const contentType = res.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (body.detail != null) {
        detail = JSON.stringify(body.detail);
      }
    } else {
      detail = await res.text();
    }
  } catch {
    detail = "";
  }

  const reason = detail || res.statusText || "Request failed";
  return new ApiError(
    res.status,
    `API error ${res.status}: ${reason} (${url})`,
    url,
    reason
  );
}

async function apiFetch<T>(path: string, token?: string): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(url, { headers });
  if (!res.ok) {
    throw await buildApiError(res, url);
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
    throw await buildApiError(res, url);
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
    throw await buildApiError(res, url);
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

  getEventTypeContributions(): Promise<EventContribution[]> {
    return apiFetch<EventContribution[]>("/stats/event-types/contributions");
  },

  getEventTypeSignificance(): Promise<EventTypeSignificance[]> {
    return apiFetch<EventTypeSignificance[]>("/stats/significance");
  },

  getBacktest(model: BacktestModel = "event_type_history"): Promise<BacktestResult[]> {
    const query = new URLSearchParams({ model });
    return apiFetch<BacktestResult[]>(`/stats/backtest?${query}`);
  },

  getMacroDecomposition(): Promise<MacroSeriesBacktest[]> {
    return apiFetch<MacroSeriesBacktest[]>("/stats/macro-decomposition");
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

  listLedgerStatements(token: string): Promise<LedgerStatementSummary[]> {
    return apiFetch<LedgerStatementSummary[]>("/ledger/statements", token);
  },

  getLedgerStatementByMonth(
    token: string,
    statementMonth: string
  ): Promise<LedgerStatement> {
    return apiFetch<LedgerStatement>(
      `/ledger/statements/${encodeURIComponent(statementMonth)}`,
      token
    );
  },

  getLedgerCategories(
    token: string,
    month: string,
    window: "month" | "year"
  ): Promise<LedgerCategory[]> {
    const query = new URLSearchParams({ month, window });
    return apiFetch<LedgerCategory[]>(
      `/ledger/categories?${query.toString()}`,
      token
    );
  },

  getLedgerTopEntries(
    token: string,
    month: string,
    window: "month" | "year",
    limit = 10
  ): Promise<LedgerEntry[]> {
    const query = new URLSearchParams({
      month,
      window,
      limit: String(limit),
    });
    return apiFetch<LedgerEntry[]>(
      `/ledger/entries/top?${query.toString()}`,
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

  listPassbookStatements(token: string): Promise<PassbookStatementSummary[]> {
    return apiFetch<PassbookStatementSummary[]>("/passbook/statements", token);
  },

  getPassbookStatementByMonth(
    token: string,
    statementMonth: string
  ): Promise<PassbookStatement> {
    return apiFetch<PassbookStatement>(
      `/passbook/statements/${encodeURIComponent(statementMonth)}`,
      token
    );
  },

  getPassbookCategories(
    token: string,
    month: string,
    window: "month" | "year"
  ): Promise<PassbookCategory[]> {
    const query = new URLSearchParams({ month, window });
    return apiFetch<PassbookCategory[]>(
      `/passbook/categories?${query.toString()}`,
      token
    );
  },

  getPassbookTopEntries(
    token: string,
    month: string,
    window: "month" | "year",
    direction: PassbookDirection,
    limit = 10
  ): Promise<PassbookEntry[]> {
    const query = new URLSearchParams({
      month,
      window,
      direction,
      limit: String(limit),
    });
    return apiFetch<PassbookEntry[]>(
      `/passbook/entries/top?${query.toString()}`,
      token
    );
  },

  uploadPassbookStatement(
    token: string,
    file: File,
    password?: string
  ): Promise<PassbookStatement> {
    const form = new FormData();
    form.append("file", file);
    if (password) form.append("password", password);
    return apiPostForm<PassbookStatement>(
      "/passbook/statement/upload",
      form,
      token
    );
  },
};
