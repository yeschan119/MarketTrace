"""Tests for configuration helpers (DB URL normalization, etc.)."""

from __future__ import annotations

import pytest

from markettrace.config import Settings, normalize_db_url


class TestNormalizeDbUrl:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("postgres://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
            ("postgresql://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
            # Already-correct driver scheme is left untouched (idempotent).
            ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
            ("sqlite+pysqlite:///./x.db", "sqlite+pysqlite:///./x.db"),
        ],
    )
    def test_scheme_coerced_to_psycopg3(self, raw, expected):
        assert normalize_db_url(raw) == expected

    def test_idempotent(self):
        once = normalize_db_url("postgres://u:p@h/db")
        assert normalize_db_url(once) == once

    def test_settings_validator_applies_normalization(self):
        s = Settings(database_url="postgres://u:p@h:5432/db")
        assert s.database_url == "postgresql+psycopg://u:p@h:5432/db"
