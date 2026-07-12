"""Pydantic v2 response schemas for the MarketTrace read API."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    primary_instrument_id: int | None
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
    primary_instrument_id: int | None = None
    primary_ticker: str | None = None
    instrument_name: str | None = None
    market: str | None = None
    reviewed_at: datetime | None = None
    original_direction: str | None = None
    original_event_type: str | None = None
    original_confidence: float | None = None
    original_primary_instrument_id: int | None = None
    document: DocumentOut
    outcomes: list[OutcomeOut]


class EventUpdate(BaseModel):
    """Human corrections to an LLM-extracted event (Phase 2 review).

    All fields optional — only those provided are changed. ``direction`` and
    ``event_type`` edits trigger a rebuild of the event's impact rows. A
    ``primary_instrument_id`` edit re-fetches prices and recomputes outcomes
    for the corrected instrument.
    """

    direction: str | None = None
    event_type: str | None = None
    confidence: float | None = None
    primary_instrument_id: int | None = None


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name: str


class InstrumentSearchOut(BaseModel):
    """Lightweight instrument row for the search entry point."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name: str
    market: str
    industry: str | None = None
    event_count: int


class InstrumentSummary(BaseModel):
    """Instrument row used by the event-review company picker."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name: str
    market: str
    industry: str | None = None


class InstrumentAnalyzeRequest(BaseModel):
    """Login-gated ad hoc issuer analysis request from the search page."""

    market: str
    ticker: str | None = None
    name: str | None = None
    industry: str | None = None
    max_filings: int = Field(default=10, ge=1, le=10)

    @field_validator("market")
    @classmethod
    def _valid_market(cls, value: str) -> str:
        market = value.strip().upper()
        if market not in {"KR", "US"}:
            raise ValueError("market must be KR or US")
        return market

    @field_validator("ticker")
    @classmethod
    def _valid_ticker(cls, value: str | None) -> str | None:
        if value is None:
            return None
        ticker = value.strip().upper()
        if not ticker:
            return None
        if len(ticker) > 20:
            raise ValueError("ticker is too long")
        return ticker

    @field_validator("name", "industry")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def _ticker_or_name_required(self) -> InstrumentAnalyzeRequest:
        if self.ticker is None and self.name is None:
            raise ValueError("ticker or name is required")
        return self


class InstrumentAnalyzeResponse(BaseModel):
    status: str
    market: str
    ticker: str
    max_filings: int


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


class DrawdownScreenerOut(BaseModel):
    """One sharply-fallen instrument plus the honest event-based diagnosis.

    ``diagnosis`` is deliberately conservative given the corpus has no validated
    *bullish* signal: it never asserts "will rise". ``possible_overreaction`` is
    a candidate flag pending the mean-reversion backtest, not a buy call.
    """

    model_config = ConfigDict(from_attributes=True)

    instrument_id: int
    ticker: str
    name: str
    market: str
    # Drawdown from the trailing-window high (<= 0), and the bars behind it.
    drawdown: float
    current_price: float
    current_date: date
    high_price: float
    high_date: date
    latest_date: date
    is_stale: bool
    # Validated event context (reused from the instrument ranking).
    recent_event_count: int
    lean: str | None
    weighted_score: float | None
    validated_count: int
    top_factor: TopFactorOut | None
    # "persistent_risk" | "unexplained_drop" | "possible_overreaction"
    diagnosis: str


class ReboundBacktestOut(BaseModel):
    """Out-of-sample result of the mean-reversion drop->rebound rule at one horizon.

    Validates (or refutes) the screener's ``possible_overreaction`` flag. A large
    ``n_dropped_no_outcome`` relative to ``n_signals`` means sparse price history —
    the numbers are underpowered, not an edge.
    """

    model_config = ConfigDict(from_attributes=True)

    horizon_days: int
    threshold: float
    window: int
    n_signals_total: int
    n_dropped_no_outcome: int
    n_signals: int
    hit_rate: float | None
    mean_forward_return: float | None
    mean_forward_return_net: float | None
    mean_abnormal_return: float | None
    mean_abnormal_return_net: float | None
    market_adjusted: bool
    commission_per_trade: float
    slippage_per_trade: float


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


class WatchlistItemOut(BaseModel):
    """An instrument on the admin's watchlist."""

    model_config = ConfigDict(from_attributes=True)

    instrument_id: int
    ticker: str
    name: str
    market: str | None
    created_at: datetime


class AlertOut(BaseModel):
    """An in-app alert joined to its event + instrument for display."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str  # "conflict" | "significant"
    created_at: datetime
    read_at: datetime | None
    event_id: int
    event_type: str
    direction: str
    primary_ticker: str | None
    instrument_name: str | None
    market: str | None
    published_at: datetime


class UnreadCountOut(BaseModel):
    """Unread-alert count for the header bell badge."""

    count: int
