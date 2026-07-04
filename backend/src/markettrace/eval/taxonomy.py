"""Canonical event-type taxonomy — eval-facing re-export.

The taxonomy now lives in :mod:`markettrace.nlp.taxonomy` (a pure leaf the
extractor depends on to enforce the family enum at extraction time). This module
re-exports the same symbols so the eval harness — and existing
``markettrace.eval.taxonomy`` imports — keep working unchanged, scoring both
gold labels and predictions at the family level via :func:`canonicalize`.
"""

from __future__ import annotations

from markettrace.nlp.taxonomy import (
    CANONICAL_FAMILIES,
    OTHER,
    canonical_rules,
    canonicalize,
)

__all__ = ["CANONICAL_FAMILIES", "OTHER", "canonicalize", "canonical_rules"]
