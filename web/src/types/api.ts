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
  market: string | null;
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

export interface EventContribution {
  event_id: number;
  event_type: string;
  horizon_days: number;
  abnormal_return: number | null;
  direction: "positive" | "negative" | "neutral" | string;
  published_at: string;
  primary_ticker: string | null;
  instrument_name: string | null;
  market: string | null;
}

export interface EventTypeSignificance {
  event_type: string;
  horizon_days: number;
  count: number;
  mean_abnormal_return: number | null;
  std_abnormal_return: number | null;
  t_stat: number | null;
  p_value: number | null;
  significant_5pct: boolean;
  sufficient_sample: boolean;
}

export type BacktestModel =
  | "event_type_history"
  | "significant_event_type"
  | "macro_surprise"
  | "combined"
  | "llm_direction";

export interface BacktestResult {
  model: BacktestModel | string;
  horizon_days: number;
  min_train_per_type: number;
  n_events_total: number;
  n_dropped_no_outcome: number;
  n_events: number;
  n_predictions: number;
  hit_rate: number | null;
  mean_strategy_return: number | null;
  mean_strategy_return_net: number | null;
  information_coefficient: number | null;
  commission_per_trade: number;
  slippage_per_trade: number;
}

export interface MacroSeriesBacktest {
  series_id: string;
  horizon_days: number;
  n_predictions: number;
  hit_rate: number | null;
  mean_strategy_return_net: number | null;
  information_coefficient: number | null;
}

export interface CalibrationBin {
  lower: number;
  upper: number;
  count: number;
  mean_confidence: number | null;
  hit_rate: number | null;
  gap: number | null;
}

export interface CalibrationReport {
  horizon_days: number;
  n_bins: number;
  n_events_total: number;
  n_dropped_neutral: number;
  n_dropped_no_outcome: number;
  n_predictions: number;
  mean_confidence: number | null;
  hit_rate: number | null;
  expected_calibration_error: number | null;
  brier_score: number | null;
  bins: CalibrationBin[];
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
  reviewed_at: string | null;
  original_direction: string | null;
  original_event_type: string | null;
  original_confidence: number | null;
  document: Document;
  outcomes: Outcome[];
}

export interface EventUpdate {
  direction?: string;
  event_type?: string;
  confidence?: number;
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

export interface LedgerEntry {
  date: string;
  card_tail: string | null;
  description: string;
  amount: number;
  category: string;
}

export interface LedgerCategory {
  category: string;
  amount: number;
  count: number;
}

export interface LedgerStatement {
  statement_month: string | null;
  file_name: string;
  file_modified_at: string;
  uploaded_at: string | null;
  encrypted: boolean;
  payment_due_date: string | null;
  period_start: string | null;
  period_end: string | null;
  billed_total: number | null;
  domestic_total: number | null;
  foreign_total: number | null;
  parsed_total: number;
  entry_count: number;
  entries: LedgerEntry[];
  categories: LedgerCategory[];
  warnings: string[];
}

export interface LedgerStatementSummary {
  statement_month: string;
  file_name: string;
  uploaded_at: string;
  period_start: string | null;
  period_end: string | null;
  payment_due_date: string | null;
  billed_total: number | null;
  parsed_total: number;
  entry_count: number;
}

export type PassbookDirection = "out" | "in";

export interface PassbookEntry {
  date: string;
  time: string;
  summary: string;
  direction: PassbookDirection;
  amount: number;
  withdrawal: number;
  deposit: number;
  description: string;
  balance: number | null;
  branch: string;
  category: string;
}

export interface PassbookCategory {
  category: string;
  withdrawal: number;
  deposit: number;
  count: number;
}

export interface PassbookStatement {
  statement_month: string | null;
  file_name: string;
  file_modified_at: string;
  uploaded_at: string | null;
  encrypted: boolean;
  account_no: string | null;
  account_holder: string | null;
  period_start: string | null;
  period_end: string | null;
  closing_balance: number | null;
  withdrawal_total: number;
  deposit_total: number;
  entry_count: number;
  entries: PassbookEntry[];
  categories: PassbookCategory[];
  warnings: string[];
}

export interface PassbookStatementSummary {
  statement_month: string;
  file_name: string;
  uploaded_at: string;
  account_no: string | null;
  account_holder: string | null;
  period_start: string | null;
  period_end: string | null;
  closing_balance: number | null;
  withdrawal_total: number;
  deposit_total: number;
  entry_count: number;
}
