"""End-to-end vertical-slice pipeline.

Wires the existing provider / ingest / nlp / impact modules into a single
flow: one disclosure -> identify company & event -> store impact hypothesis
-> auto-compute market-adjusted returns at the configured horizons.
"""

from __future__ import annotations

from markettrace.pipeline.vertical_slice import SliceResult, run_slice

__all__ = ["SliceResult", "run_slice"]
