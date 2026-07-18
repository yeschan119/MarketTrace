"""Stable per-entry fingerprints for ledger / passbook category overrides.

A statement is re-parsed and re-categorized on every read, so a manual
category correction cannot be pinned to a database row id — the entries have
none. Instead each entry gets a deterministic ``entry_key`` derived from the
immutable fields the parser produces (date, amount, merchant, …). The same
transaction therefore hashes to the same key across re-parses and across
months, which is exactly what an override needs to survive on.

This module has no intra-package imports on purpose: both the parsing layer
(``statements``) and the customization layer import it, so keeping it
dependency-free avoids an import cycle.
"""

from __future__ import annotations

import hashlib

_SEPARATOR = ""


def make_entry_key(parts: list[object]) -> str:
    """Return a short, stable hex key for a transaction's identifying fields."""
    joined = _SEPARATOR.join("" if part is None else str(part) for part in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]
