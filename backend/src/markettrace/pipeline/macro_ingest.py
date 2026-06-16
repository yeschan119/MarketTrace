"""Macro ingestion pipeline: FRED series -> macro_observations with surprise.

Fetches initial-release observations for a set of FRED series, computes the
standardized surprise for each (blueprint §7-3), and upserts them into
``macro_observations``. Idempotent: an observation already present (matched on
``series_id`` + ``reference_date`` + ``revision``) is skipped, so re-running is
safe. Mirrors the orchestration style of ``vertical_slice`` — it only wires the
provider, the numeric core, and persistence together.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime

from sqlalchemy import select

from markettrace.db.models import MacroObservation, ModelRun
from markettrace.impact.macro_surprise import build_macro_observations

__all__ = ["ingest_macro_series", "main"]

_DEFAULT_SINCE = date(1990, 1, 1)


def ingest_macro_series(
    session,
    provider,
    series_ids: list[str],
    *,
    now: datetime,
    since: date = _DEFAULT_SINCE,
) -> dict[str, int]:
    """Fetch + persist macro observations for each series; return inserts per series.

    For every series the provider's initial-release points are turned into
    :class:`MacroObservation` rows (with surprise) and inserted unless an
    identical ``(series_id, reference_date, revision)`` row already exists. A
    single ``ModelRun`` records provenance when anything was inserted; the
    session is committed once at the end.

    Fetches are *incremental*: a series already present in the DB is re-fetched
    only from its latest stored ``reference_date`` (the overlap row is deduped),
    not from *since*, so repeat runs avoid re-downloading decades of data. The
    surprise of each new release still needs the full prior history for its
    baseline/scale, so the released values stored before the fetch window seed
    that history — reproducing a full-history compute. *since* is the fetch floor
    only for series with no rows yet.
    """
    inserted: dict[str, int] = {}

    for series_id in series_ids:
        # Existing rows: dedup keys + the released-value history (initial release
        # per period) used to seed surprise for incrementally fetched points.
        existing_rows = session.execute(
            select(
                MacroObservation.reference_date,
                MacroObservation.revision,
                MacroObservation.released_value,
            )
            .where(MacroObservation.series_id == series_id)
            .order_by(MacroObservation.reference_date)
        ).all()
        existing = {(r.reference_date, r.revision) for r in existing_rows}

        # Re-fetch from the latest stored reference_date so only new releases come
        # back (the boundary row is deduped, and re-including it lets the provider
        # chain previous_value into the first new point). Seed history with the
        # released values from strictly-earlier periods so baseline/scale match a
        # full-history compute. New series fall back to the *since* floor.
        last_ref = existing_rows[-1].reference_date if existing_rows else None
        fetch_since = last_ref if last_ref is not None else since
        prior_history = [
            r.released_value
            for r in existing_rows
            if r.revision == 0 and r.reference_date < fetch_since
        ]

        points = provider.get_observations(series_id, fetch_since)
        rows = build_macro_observations(points, now=now, prior_history=prior_history)

        count = 0
        for row in rows:
            if (row.reference_date, row.revision) in existing:
                continue
            session.add(row)
            existing.add((row.reference_date, row.revision))
            count += 1
        inserted[series_id] = count

    total = sum(inserted.values())
    if total:
        session.add(
            ModelRun(
                kind="macro_ingest",
                params={"series": series_ids, "inserted": inserted},
                data_version=None,
                created_at=now,
            )
        )
    session.commit()
    return inserted


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``markettrace-macro`` (live; requires FRED_API_KEY).

    Builds a real FRED provider and DB session from settings, ingests the chosen
    series, and prints the per-series insert counts as JSON. Not run in CI.
    """
    parser = argparse.ArgumentParser(
        prog="markettrace-macro",
        description="Ingest FRED macro series into macro_observations with surprise scores.",
    )
    parser.add_argument(
        "--series",
        default=None,
        help="Comma-separated FRED series ids (default: settings.macro_series).",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Earliest reference date YYYY-MM-DD (default: 1990-01-01).",
    )
    args = parser.parse_args(argv)

    from markettrace.config import get_settings
    from markettrace.db.session import make_engine, make_session_factory
    from markettrace.providers.registry import get_macro_provider

    settings = get_settings()
    if settings.fred_api_key is None:
        print(
            "error: FRED_API_KEY is not configured; cannot fetch macro data.",
            file=sys.stderr,
        )
        return 2

    series_ids = (
        [s.strip() for s in args.series.split(",") if s.strip()]
        if args.series
        else settings.macro_series_list
    )
    since = (
        datetime.strptime(args.since, "%Y-%m-%d").date()
        if args.since
        else _DEFAULT_SINCE
    )

    provider = get_macro_provider("fred")
    engine = make_engine(settings.database_url)
    session = make_session_factory(engine)()
    try:
        inserted = ingest_macro_series(
            session, provider, series_ids, now=datetime.now(UTC), since=since
        )
    finally:
        session.close()

    print(json.dumps({"inserted": inserted}, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
