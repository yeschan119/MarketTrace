"""SQLAlchemy 2.0 declarative models.

These table and column names are the integration contract that the
ingest / nlp / impact / api modules depend on. JSON columns use
``sqlalchemy.JSON`` so they map to ``jsonb`` on PostgreSQL and ``JSON``
on SQLite, keeping the models portable for tests. All timestamps are
timezone-aware.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all MarketTrace ORM models."""


class Instrument(Base):
    __tablename__ = "instruments"
    __table_args__ = (UniqueConstraint("market", "ticker", name="uq_instruments_market_ticker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String, nullable=False)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    listed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    aliases: Mapped[list[EntityAlias]] = relationship(
        back_populates="instrument", cascade="all, delete-orphan"
    )
    prices: Mapped[list[Price]] = relationship(
        back_populates="instrument", cascade="all, delete-orphan"
    )


class EntityAlias(Base):
    __tablename__ = "entity_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instruments.id"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String, nullable=False)
    alias_type: Mapped[str] = mapped_column(String, nullable=False)

    instrument: Mapped[Instrument] = relationship(back_populates="aliases")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_object_key: Mapped[str | None] = mapped_column(String, nullable=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    market: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentEntity(Base):
    __tablename__ = "document_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False)
    primary_instrument_id: Mapped[int | None] = mapped_column(
        ForeignKey("instruments.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    entities: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    industries: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    channels: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    surprise_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    novelty_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_reliability: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    model: Mapped[str] = mapped_column(String, nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Phase 2 human review: timestamp of the last manual correction and the
    # model's original values, snapshotted on the first edit so the LLM read
    # stays recoverable. All NULL until an event is reviewed.
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    original_direction: Mapped[str | None] = mapped_column(String, nullable=True)
    original_event_type: Mapped[str | None] = mapped_column(String, nullable=True)
    original_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_primary_instrument_id: Mapped[int | None] = mapped_column(
        ForeignKey("instruments.id"), nullable=True
    )

    primary_instrument: Mapped[Instrument | None] = relationship(
        foreign_keys=[primary_instrument_id]
    )


class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint("instrument_id", "date", name="uq_prices_instrument_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    adj_close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)

    instrument: Mapped[Instrument] = relationship(back_populates="prices")


class Outcome(Base):
    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    abnormal_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    sector_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    sector_abnormal_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EventImpact(Base):
    """Per-event, per-horizon impact score linking an event to its instrument.

    Sits one layer above :class:`Outcome`: it folds the raw/abnormal returns
    together with the event's stated ``direction`` into a *directional* impact
    figure (``signed_abnormal_return``), so a positive-direction event followed
    by outperformance reads as a *confirmed* positive impact and the opposite as
    a *contradicted* one. ``industry`` snapshots the instrument's sector at
    analysis time for sector-level aggregation.
    """

    __tablename__ = "event_impacts"
    __table_args__ = (
        UniqueConstraint("event_id", "horizon_days", name="uq_event_impacts_event_horizon"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    abnormal_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    sector_abnormal_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    signed_abnormal_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    params: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    data_version: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MacroObservation(Base):
    """A single vintage-preserving macroeconomic release (blueprint §4).

    Stores the value *as first published* (``released_value``) together with the
    consensus or baseline ``expected_value`` and the prior reading, so a
    standardized ``surprise_score`` can be computed without look-ahead bias
    (§9). Each revision of a given ``(series_id, reference_date)`` is kept as a
    separate row (``revision``) to preserve the revision history. The three
    timestamps follow the §2 principle: ``occurred_at`` = end of the reference
    period, ``published_at`` = the release/vintage date, ``first_seen_at`` =
    when this system ingested it.
    """

    __tablename__ = "macro_observations"
    __table_args__ = (
        UniqueConstraint(
            "series_id", "reference_date", "revision", name="uq_macro_obs_series_ref_rev"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[str] = mapped_column(String, nullable=False)
    reference_date: Mapped[date] = mapped_column(Date, nullable=False)
    released_value: Mapped[float] = mapped_column(Float, nullable=False)
    previous_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    # "consensus" when a real forecast was supplied, "baseline" when derived
    # deterministically from history, NULL when no expectation is available.
    expected_source: Mapped[str | None] = mapped_column(String, nullable=True)
    surprise_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String, nullable=False)


class LedgerStatementRecord(Base):
    __tablename__ = "ledger_statements"
    __table_args__ = (
        UniqueConstraint("statement_month", name="uq_ledger_statements_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    statement_month: Mapped[date] = mapped_column(Date, nullable=False)
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    file_modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    encrypted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    payment_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    billed_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    domestic_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    foreign_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parsed_total: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    entries: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    categories: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class LedgerCategoryRule(Base):
    """A user keyword→category rule shared by the card and passbook views.

    ``domain`` separates the two ledgers ("card" vs "passbook") so a merchant
    keyword rule never bleeds into 적요-based passbook matching. ``keyword_norm``
    is the normalized (upper-cased, punctuation-stripped) form used for
    substring matching; ``keyword`` keeps the original text for display. Rules
    take precedence over the built-in category rules and apply retroactively to
    every stored statement as well as future ones.
    """

    __tablename__ = "ledger_category_rules"
    __table_args__ = (
        UniqueConstraint("domain", "keyword_norm", name="uq_ledger_rule_domain_keyword"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    keyword: Mapped[str] = mapped_column(String, nullable=False)
    keyword_norm: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LedgerEntryOverride(Base):
    """A single-transaction category correction keyed by its stable fingerprint.

    ``entry_key`` is the ``make_entry_key`` hash of the transaction's immutable
    fields, so the override re-binds to the same row every time the statement is
    re-parsed. Highest precedence: it beats both user keyword rules and the
    built-in rules.
    """

    __tablename__ = "ledger_entry_overrides"
    __table_args__ = (
        UniqueConstraint("domain", "entry_key", name="uq_ledger_override_domain_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    entry_key: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LedgerCustomCategory(Base):
    """A user-created category name for a ledger domain.

    Lets a category exist (and be managed) before any transaction or rule
    references it, so the reassignment dropdown can offer it immediately.
    """

    __tablename__ = "ledger_custom_categories"
    __table_args__ = (
        UniqueConstraint("domain", "name", name="uq_ledger_custom_category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PassbookStatementRecord(Base):
    __tablename__ = "passbook_statements"
    __table_args__ = (
        UniqueConstraint("statement_month", name="uq_passbook_statements_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    statement_month: Mapped[date] = mapped_column(Date, nullable=False)
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    file_modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    encrypted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    account_no: Mapped[str | None] = mapped_column(String, nullable=True)
    account_holder: Mapped[str | None] = mapped_column(String, nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    closing_balance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    withdrawal_total: Mapped[int] = mapped_column(Integer, nullable=False)
    deposit_total: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    entries: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    categories: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class AdminUser(Base):
    """Login-capable admin-console user.

    The app still supports the legacy environment-variable admin login. This
    table backs the new 관리자 탭 user-management workflow and stores only
    password hashes, never plaintext passwords.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    login_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String, nullable=False, default="viewer")
    status: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RoleTabPermission(Base):
    """Role-based tab visibility matrix for the admin console."""

    __tablename__ = "role_tab_permissions"
    __table_args__ = (
        UniqueConstraint("role", "tab_id", name="uq_role_tab_permission"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    tab_id: Mapped[str] = mapped_column(String, nullable=False)
    can_view: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TabStatus(Base):
    """Global tab on/off state controlled by 관리자 > 탭 관리."""

    __tablename__ = "tab_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tab_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    in_use: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WatchlistItem(Base):
    """An instrument the (single admin) user has chosen to watch.

    The watchlist is global — there is one admin — so a row is simply an
    instrument the user wants alerts for. ``instrument_id`` is unique so watching
    is idempotent.
    """

    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("instrument_id", name="uq_watchlist_instrument"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    instrument: Mapped[Instrument] = relationship()


class Alert(Base):
    """An in-app notification generated for a watched instrument's event.

    Created during ingest when a new event on a watched instrument is *notable*
    — its type is a statistically validated (significant) bucket, and the alert
    ``kind`` is ``"conflict"`` when the model's stated direction opposes the
    validated historical drift, else ``"significant"``. ``read_at`` is NULL until
    the user marks it read. ``(event_id)`` is unique so re-running ingest never
    duplicates an alert for the same event.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_alerts_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # "conflict" | "significant"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    instrument: Mapped[Instrument] = relationship()
    event: Mapped[Event] = relationship()
