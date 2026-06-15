"""Integration test for the vertical-slice pipeline.

Runs entirely on in-memory SQLite with fakes — no network, no Anthropic API
key. Synthetic price frames are constructed so the D+1/5/20 raw, market, and
abnormal returns are known exact numbers (positional row offsets).

Synthetic design
----------------
Both stock and market frames have 30 rows over consecutive calendar days.
The event sits at row 5 (its date is the document's ``published_at.date()``).
Positional offsets from row 5: +1 -> row 6, +5 -> row 10, +20 -> row 25.

  Stock adj_close:  row5=100, row6=103, row10=115, row25=140
    raw: 1d=0.03, 5d=0.15, 20d=0.40
  Market adj_close: row5=200, row6=202, row10=210, row25=220
    mkt: 1d=0.01, 5d=0.05, 20d=0.10
  Abnormal: 1d=0.02, 5d=0.10, 20d=0.30
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest

from markettrace.db.models import Document, Event, EventImpact, Instrument, ModelRun, Outcome
from markettrace.nlp.schemas import EventExtraction
from markettrace.pipeline.vertical_slice import (
    SliceResult,
    recompute_document_outcomes,
    run_slice,
)
from markettrace.providers.base import DocumentRef, RawDocument

_BASE_DATE = date(2024, 1, 2)  # one calendar day per row
_EVENT_ROW = 5
_EVENT_DATE = _BASE_DATE + timedelta(days=_EVENT_ROW)
_PUBLISHED_AT = datetime(
    _EVENT_DATE.year, _EVENT_DATE.month, _EVENT_DATE.day, tzinfo=UTC
)

_DISCLOSURE_TEXT = (
    "Apple Inc. reported quarterly results that beat analyst expectations, "
    "driven by strong iPhone demand. Management raised guidance for the year."
)


def _build_price_frame(overrides: dict[int, float]) -> pl.DataFrame:
    """30-row OHLCV frame; ``overrides`` sets adj_close at given row indices."""
    n = 30
    closes = [50.0] * n
    for idx, value in overrides.items():
        closes[idx] = value
    dates = [_BASE_DATE + timedelta(days=i) for i in range(n)]
    return pl.DataFrame(
        {
            "date": dates,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "adj_close": closes,
            "volume": [1_000_000.0] * n,
        }
    )


_STOCK_FRAME = _build_price_frame({5: 100.0, 6: 103.0, 10: 115.0, 25: 140.0})
_MARKET_FRAME = _build_price_frame({5: 200.0, 6: 202.0, 10: 210.0, 25: 220.0})


class _FakeDisclosureProvider:
    market = "US"

    def fetch_raw(self, ref: DocumentRef) -> RawDocument:
        return RawDocument(
            ref=ref,
            content=_DISCLOSURE_TEXT,
            fetched_at=datetime.now(UTC),
        )


class _FakePriceProvider:
    market = "US"

    def get_ohlcv(self, ticker: str, start: date, end: date) -> pl.DataFrame:
        if ticker.lower() == "spy":
            return _MARKET_FRAME.clone()
        return _STOCK_FRAME.clone()


class _FakeExtractor:
    model = "claude-sonnet-4-6"

    def extract(self, text: str, *, source_reliability: float | None = None):
        event = EventExtraction(
            event_type="earnings_beat",
            entities=["AAPL"],
            industries=["Technology"],
            channels=["earnings", "sentiment"],
            direction="positive",
            horizon_days=5,
            surprise_score=0.8,
            novelty_score=0.3,
            source_reliability=source_reliability,
            confidence=0.9,
            evidence=[
                "Apple Inc. reported quarterly results that beat analyst expectations.",
                "Management raised guidance for the year.",
            ],
        )
        return event, "claude-sonnet-4-6-20260101"


def _make_ref() -> DocumentRef:
    return DocumentRef(
        source="sec_edgar",
        external_id="0000320193-24-000001",
        url="https://www.sec.gov/Archives/edgar/data/320193/aapl_10q.html",
        market="US",
        published_at=_PUBLISHED_AT,
        title="10-Q",
        primary_ticker="AAPL",
    )


def _seed_instrument(session) -> Instrument:
    instrument = Instrument(market="US", ticker="AAPL", name="Apple Inc.")
    session.add(instrument)
    session.commit()
    return instrument


def test_run_slice_end_to_end(db_session, tmp_object_store) -> None:
    instrument = _seed_instrument(db_session)

    result = run_slice(
        db_session,
        tmp_object_store,
        ref=_make_ref(),
        disclosure_provider=_FakeDisclosureProvider(),
        price_provider=_FakePriceProvider(),
        extractor=_FakeExtractor(),
        ticker="AAPL",
        market_index_ticker="spy",
        horizons=(1, 5, 20),
    )

    assert isinstance(result, SliceResult)
    assert result.instrument_id == instrument.id

    # --- exactly one Document ---
    documents = db_session.query(Document).all()
    assert len(documents) == 1
    assert documents[0].id == result.document_id

    # --- exactly one Event, fields round-tripped ---
    events = db_session.query(Event).all()
    assert len(events) == 1
    event = events[0]
    assert event.id == result.event_id
    assert event.primary_instrument_id == instrument.id
    assert event.event_type == "earnings_beat"
    assert event.entities == ["AAPL"]
    assert event.evidence == [
        "Apple Inc. reported quarterly results that beat analyst expectations.",
        "Management raised guidance for the year.",
    ]
    assert event.model == "claude-sonnet-4-6"
    assert event.model_version == "claude-sonnet-4-6-20260101"

    # --- three Outcomes with known abnormal returns ---
    outcomes = (
        db_session.query(Outcome).order_by(Outcome.horizon_days).all()
    )
    assert [o.horizon_days for o in outcomes] == [1, 5, 20]
    for o in outcomes:
        assert o.event_id == event.id
        assert o.instrument_id == instrument.id

    by_h = {o.horizon_days: o for o in outcomes}
    assert by_h[1].raw_return == pytest.approx(0.03)
    assert by_h[1].market_return == pytest.approx(0.01)
    assert by_h[1].abnormal_return == pytest.approx(0.02)
    assert by_h[5].raw_return == pytest.approx(0.15)
    assert by_h[5].market_return == pytest.approx(0.05)
    assert by_h[5].abnormal_return == pytest.approx(0.10)
    assert by_h[20].raw_return == pytest.approx(0.40)
    assert by_h[20].market_return == pytest.approx(0.10)
    assert by_h[20].abnormal_return == pytest.approx(0.30)

    # SliceResult carries the same outcomes.
    assert {o.horizon_days for o in result.outcomes} == {1, 5, 20}

    # --- one EventImpact per horizon, directional sign applied ---
    impacts = db_session.query(EventImpact).order_by(EventImpact.horizon_days).all()
    assert [i.horizon_days for i in impacts] == [1, 5, 20]
    assert all(i.event_id == event.id and i.event_type == "earnings_beat" for i in impacts)
    # positive direction + positive abnormal return -> positive signed impact
    by_h_imp = {i.horizon_days: i for i in impacts}
    assert by_h_imp[1].signed_abnormal_return == pytest.approx(0.02)
    assert by_h_imp[20].signed_abnormal_return == pytest.approx(0.30)

    # --- exactly one ModelRun(kind="vertical_slice") ---
    model_runs = db_session.query(ModelRun).all()
    assert len(model_runs) == 1
    assert model_runs[0].kind == "vertical_slice"
    assert model_runs[0].params == {
        "ticker": "AAPL",
        "horizons": [1, 5, 20],
        "sector_index_ticker": None,
    }


class _FakeSectorPriceProvider:
    """Returns a distinct sector frame for XLK, market frame for spy, else stock."""

    market = "US"

    def get_ohlcv(self, ticker: str, start: date, end: date) -> pl.DataFrame:
        t = ticker.lower()
        if t == "spy":
            return _MARKET_FRAME.clone()
        if t == "xlk":
            # sector index: row5=300, row6=306 -> 1d sector return = 0.02
            return _build_price_frame({5: 300.0, 6: 306.0, 10: 330.0, 25: 360.0})
        return _STOCK_FRAME.clone()


def test_run_slice_auto_resolves_sector_from_industry(db_session, tmp_object_store) -> None:
    """An instrument with a mapped industry gets sector-adjusted outcomes."""
    instrument = Instrument(
        market="US", ticker="AAPL", name="Apple Inc.", industry="Technology"
    )
    db_session.add(instrument)
    db_session.commit()

    run_slice(
        db_session,
        tmp_object_store,
        ref=_make_ref(),
        disclosure_provider=_FakeDisclosureProvider(),
        price_provider=_FakeSectorPriceProvider(),
        extractor=_FakeExtractor(),
        ticker="AAPL",
        market_index_ticker="spy",
        horizons=(1,),
    )

    outcome = db_session.query(Outcome).filter(Outcome.horizon_days == 1).one()
    # stock 1d raw = 0.03, sector (XLK) 1d = 0.02 -> sector abnormal = 0.01
    assert outcome.sector_return == pytest.approx(0.02)
    assert outcome.sector_abnormal_return == pytest.approx(0.01)

    # provenance records the auto-resolved sector ticker
    run = db_session.query(ModelRun).one()
    assert run.params["sector_index_ticker"] == "XLK"


def test_run_slice_unresolvable_ticker_raises(db_session, tmp_object_store) -> None:
    _seed_instrument(db_session)

    with pytest.raises(ValueError):
        run_slice(
            db_session,
            tmp_object_store,
            ref=_make_ref(),
            disclosure_provider=_FakeDisclosureProvider(),
            price_provider=_FakePriceProvider(),
            extractor=_FakeExtractor(),
            ticker="ZZZZ",  # not seeded -> unresolvable
        )


def test_run_slice_dedups_document_on_rerun(db_session, tmp_object_store) -> None:
    """Re-running fetch+ingest of identical content must not duplicate the Document."""
    _seed_instrument(db_session)

    ref = _make_ref()
    kwargs = dict(
        disclosure_provider=_FakeDisclosureProvider(),
        price_provider=_FakePriceProvider(),
        extractor=_FakeExtractor(),
        ticker="AAPL",
        market_index_ticker="spy",
    )

    first = run_slice(db_session, tmp_object_store, ref=ref, **kwargs)
    second = run_slice(db_session, tmp_object_store, ref=ref, **kwargs)

    # Same content -> deduped to a single Document row.
    assert db_session.query(Document).count() == 1
    assert second.document_id == first.document_id


def test_recompute_backfills_missing_horizon_and_impacts(db_session, tmp_object_store) -> None:
    """Old-engine data (no 60-day horizon) is recomputed in place, no duplicate event."""
    _seed_instrument(db_session)
    ref = _make_ref()

    # Simulate data produced by an older engine: only the 1/5/20-day horizons.
    result = run_slice(
        db_session,
        tmp_object_store,
        ref=ref,
        disclosure_provider=_FakeDisclosureProvider(),
        price_provider=_FakePriceProvider(),
        extractor=_FakeExtractor(),
        ticker="AAPL",
        market_index_ticker="spy",
        horizons=(1, 5, 20),
    )
    document = db_session.get(Document, result.document_id)
    assert {o.horizon_days for o in db_session.query(Outcome).all()} == {1, 5, 20}

    # Recompute with the current default horizons (adds the 60-day horizon).
    recomputed = recompute_document_outcomes(
        db_session,
        document=document,
        price_provider=_FakePriceProvider(),
        ticker="AAPL",
        market="US",
        market_index_ticker="spy",
    )
    assert recomputed == 1

    # Same single event reused — no duplicate, full horizon set + paired impacts.
    assert db_session.query(Event).count() == 1
    assert {o.horizon_days for o in db_session.query(Outcome).all()} == {1, 5, 20, 60}
    assert {i.horizon_days for i in db_session.query(EventImpact).all()} == {1, 5, 20, 60}

    # Now up to date -> a second recompute is a no-op.
    assert (
        recompute_document_outcomes(
            db_session,
            document=document,
            price_provider=_FakePriceProvider(),
            ticker="AAPL",
            market="US",
            market_index_ticker="spy",
        )
        == 0
    )


def test_recompute_backfills_when_impacts_missing(db_session, tmp_object_store) -> None:
    """Outcomes present for every horizon but no event_impacts still triggers recompute."""
    _seed_instrument(db_session)
    ref = _make_ref()
    result = run_slice(
        db_session,
        tmp_object_store,
        ref=ref,
        disclosure_provider=_FakeDisclosureProvider(),
        price_provider=_FakePriceProvider(),
        extractor=_FakeExtractor(),
        ticker="AAPL",
        market_index_ticker="spy",
        horizons=(1, 5, 20, 60),
    )
    document = db_session.get(Document, result.document_id)

    # Drop the event_impacts (as if an older engine never wrote them).
    db_session.query(EventImpact).delete()
    db_session.commit()
    assert db_session.query(EventImpact).count() == 0

    recomputed = recompute_document_outcomes(
        db_session,
        document=document,
        price_provider=_FakePriceProvider(),
        ticker="AAPL",
        market="US",
        market_index_ticker="spy",
    )
    assert recomputed == 1
    assert {i.horizon_days for i in db_session.query(EventImpact).all()} == {1, 5, 20, 60}


# ---------------------------------------------------------------------------
# KR market path
# ---------------------------------------------------------------------------

_KR_DISCLOSURE_TEXT = "삼성전자 분기 실적이 예상치를 상회했습니다."


class _FakeKRDisclosureProvider:
    market = "KR"

    def fetch_raw(self, ref: DocumentRef) -> RawDocument:
        return RawDocument(
            ref=ref,
            content=_KR_DISCLOSURE_TEXT,
            fetched_at=datetime.now(UTC),
        )


class _FakeKRPriceProvider:
    market = "KR"

    def get_ohlcv(self, ticker: str, start: date, end: date) -> pl.DataFrame:
        if ticker.lower() in ("kospi", "spy"):
            return _MARKET_FRAME.clone()
        return _STOCK_FRAME.clone()


def _make_kr_ref() -> DocumentRef:
    return DocumentRef(
        source="opendart",
        external_id="20240330000001",
        url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20240330000001",
        market="KR",
        published_at=_PUBLISHED_AT,
        title="사업보고서",
        primary_ticker="005930",
    )


def _seed_kr_instrument(session) -> Instrument:
    instrument = Instrument(market="KR", ticker="005930", name="Samsung Electronics Co., Ltd.")
    session.add(instrument)
    session.commit()
    return instrument


def test_run_slice_kr_end_to_end(db_session, tmp_object_store) -> None:
    """KR-flavored ref (market='KR', opendart source) flows through run_slice correctly."""
    instrument = _seed_kr_instrument(db_session)

    result = run_slice(
        db_session,
        tmp_object_store,
        ref=_make_kr_ref(),
        disclosure_provider=_FakeKRDisclosureProvider(),
        price_provider=_FakeKRPriceProvider(),
        extractor=_FakeExtractor(),
        ticker="005930",
        market_index_ticker="kospi",
        horizons=(1, 5, 20),
    )

    assert isinstance(result, SliceResult)
    assert result.instrument_id == instrument.id

    events = db_session.query(Event).all()
    assert len(events) == 1
    assert events[0].primary_instrument_id == instrument.id

    outcomes = db_session.query(Outcome).order_by(Outcome.horizon_days).all()
    assert [o.horizon_days for o in outcomes] == [1, 5, 20]
    by_h = {o.horizon_days: o for o in outcomes}
    assert by_h[1].abnormal_return == pytest.approx(0.02)
    assert by_h[5].abnormal_return == pytest.approx(0.10)
    assert by_h[20].abnormal_return == pytest.approx(0.30)
