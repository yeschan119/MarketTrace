// Hand-written TypeScript interfaces matching the FastAPI contract.
// Run `npm run gen:types` (with backend running) to regenerate from OpenAPI schema.

export interface EventSummary {
  id: string;
  event_type: string;
  direction: "positive" | "negative" | "neutral" | string;
  confidence: number;
  published_at: string;
  primary_ticker: string;
  instrument_name: string;
}

export interface Outcome {
  horizon_days: number;
  raw_return: number;
  market_return: number;
  abnormal_return: number;
  sector_return?: number | null;
  sector_abnormal_return?: number | null;
}

export interface EventTypeStat {
  event_type: string;
  horizon_days: number;
  count: number;
  mean_abnormal_return: number | null;
  std_abnormal_return: number | null;
}

export interface MacroObservation {
  series_id: string;
  reference_date: string;
  released_value: number;
  previous_value: number | null;
  expected_value: number | null;
  expected_source: string | null;
  surprise_score: number | null;
  published_at: string;
}

export interface Document {
  url: string;
  source: string;
  published_at: string;
  title: string;
}

export interface EventDetail {
  id: string;
  event_type: string;
  entities: string[];
  industries: string[];
  channels: string[];
  direction: "positive" | "negative" | "neutral" | string;
  horizon_days: number;
  confidence: number;
  surprise_score: number | null;
  novelty_score: number | null;
  source_reliability: number | null;
  evidence: string[];
  model: string;
  model_version: string;
  document: Document;
  outcomes: Outcome[];
}

export interface Instrument {
  id: string;
  ticker: string;
  name: string;
}

export interface InstrumentTimeline {
  instrument: Instrument;
  events: EventSummary[];
}

export interface HealthResponse {
  status: string;
}
