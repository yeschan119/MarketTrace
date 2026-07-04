"""Pydantic v2 response schemas for the MarketTrace read API."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str
    source: str
    published_at: datetime
    title: str | None


class OutcomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    horizon_days: int
    raw_return: float | None
    market_return: float | None
    abnormal_return: float | None
    sector_return: float | None = None
    sector_abnormal_return: float | None = None


class EventSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    direction: str
    confidence: float
    published_at: datetime
    primary_ticker: str | None
    instrument_name: str | None
    market: str | None
    reviewed_at: datetime | None = None


class EventDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    entities: list[str]
    industries: list[str]
    channels: list[str]
    direction: str
    horizon_days: int
    confidence: float
    surprise_score: float | None
    novelty_score: float | None
    source_reliability: float | None
    evidence: list[str]
    model: str
    model_version: str
    reviewed_at: datetime | None = None
    original_direction: str | None = None
    original_event_type: str | None = None
    original_confidence: float | None = None
    document: DocumentOut
    outcomes: list[OutcomeOut]


class EventUpdate(BaseModel):
    """Human corrections to an LLM-extracted event (Phase 2 review).

    All fields optional — only those provided are changed. ``direction`` and
    ``event_type`` edits trigger a rebuild of the event's impact rows.
    """

    direction: str | None = None
    event_type: str | None = None
    confidence: float | None = None


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name: str


class InstrumentTimeline(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    instrument: InstrumentOut
    events: list[EventSummary]


class EventTypeStatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: str
    horizon_days: int
    count: int
    mean_abnormal_return: float | None
    std_abnormal_return: float | None


class EventContributionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: int
    event_type: str
    horizon_days: int
    abnormal_return: float | None
    direction: str
    published_at: datetime
    primary_ticker: str | None
    instrument_name: str | None
    market: str | None


class EventTypeSignificanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: str
    horizon_days: int
    count: int
    mean_abnormal_return: float | None
    std_abnormal_return: float | None
    t_stat: float | None
    p_value: float | None
    significant_5pct: bool
    sufficient_sample: bool


class TopFactorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: str
    drift: float
    count: int


class InstrumentRankingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    instrument_id: int
    ticker: str
    name: str
    market: str | None
    weighted_score: float
    simple_mean: float
    lean: str
    validated_count: int
    conflict_count: int
    unreviewed_conflict_count: int
    top_factor: TopFactorOut | None


class BacktestResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model: str
    horizon_days: int
    min_train_per_type: int
    n_events_total: int
    n_dropped_no_outcome: int
    n_events: int
    n_predictions: int
    hit_rate: float | None
    mean_strategy_return: float | None
    mean_strategy_return_net: float | None
    information_coefficient: float | None
    commission_per_trade: float
    slippage_per_trade: float


class MacroSeriesBacktestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    series_id: str
    horizon_days: int
    n_predictions: int
    hit_rate: float | None
    mean_strategy_return_net: float | None
    information_coefficient: float | None


class CalibrationBinOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lower: float
    upper: float
    count: int
    mean_confidence: float | None
    hit_rate: float | None
    gap: float | None


class CalibrationReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    horizon_days: int
    n_bins: int
    n_events_total: int
    n_dropped_neutral: int
    n_dropped_no_outcome: int
    n_predictions: int
    mean_confidence: float | None
    hit_rate: float | None
    expected_calibration_error: float | None
    brier_score: float | None
    bins: list[CalibrationBinOut]


class MacroObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    series_id: str
    reference_date: date
    released_value: float
    previous_value: float | None
    expected_value: float | None
    expected_source: str | None
    surprise_score: float | None
    published_at: datetime


class LedgerRequest(BaseModel):
    password: str | None = None


class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    card_tail: str | None
    description: str
    amount: int
    category: str


class LedgerCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: str
    amount: int
    count: int


class LedgerStatementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    statement_month: date | None = None
    file_name: str
    file_modified_at: datetime
    uploaded_at: datetime | None = None
    encrypted: bool
    payment_due_date: date | None
    period_start: date | None
    period_end: date | None
    billed_total: int | None
    domestic_total: int | None
    foreign_total: int | None
    parsed_total: int
    entry_count: int
    entries: list[LedgerEntryOut]
    categories: list[LedgerCategoryOut]
    warnings: list[str]


class LedgerStatementSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    statement_month: date
    file_name: str
    uploaded_at: datetime
    period_start: date | None
    period_end: date | None
    payment_due_date: date | None
    billed_total: int | None
    parsed_total: int
    entry_count: int


class PassbookRequest(BaseModel):
    password: str | None = None


class PassbookEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    time: str
    summary: str
    direction: str
    amount: int
    withdrawal: int
    deposit: int
    description: str
    balance: int | None
    branch: str
    category: str


class PassbookCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: str
    withdrawal: int
    deposit: int
    count: int


class PassbookStatementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    statement_month: date | None = None
    file_name: str
    file_modified_at: datetime
    uploaded_at: datetime | None = None
    encrypted: bool
    account_no: str | None
    account_holder: str | None
    period_start: date | None
    period_end: date | None
    closing_balance: int | None
    withdrawal_total: int
    deposit_total: int
    entry_count: int
    entries: list[PassbookEntryOut]
    categories: list[PassbookCategoryOut]
    warnings: list[str]


class PassbookStatementSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    statement_month: date
    file_name: str
    uploaded_at: datetime
    account_no: str | None
    account_holder: str | None
    period_start: date | None
    period_end: date | None
    closing_balance: int | None
    withdrawal_total: int
    deposit_total: int
    entry_count: int
