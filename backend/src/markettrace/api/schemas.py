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
    document: DocumentOut
    outcomes: list[OutcomeOut]


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
