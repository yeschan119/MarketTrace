"""Application configuration via pydantic-settings.

Settings are read from environment variables (or a local ``.env`` file). Tests
override ``database_url`` to point at in-memory SQLite, so the default here is the
local postgres compose service rather than a throwaway sqlite file.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default extraction model per LLM provider. Used when ``extraction_model`` is
# left unset so the right model is picked for whichever provider is active.
_DEFAULT_EXTRACTION_MODEL: dict[str, str] = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
}


def normalize_db_url(url: str) -> str:
    """Coerce ``postgres(ql)://`` URLs to the psycopg3 driver scheme.

    Managed hosts (Render, Heroku, etc.) hand out ``postgres://`` or
    ``postgresql://`` connection strings, but SQLAlchemy with psycopg3 requires
    the explicit ``postgresql+psycopg://`` driver prefix. Shared by both the
    Settings validator and Alembic's env so migrations and the app agree.
    """
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings(BaseSettings):
    """Runtime configuration for the MarketTrace backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Which LLM backend the event extractor talks to.
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    database_url: str = (
        "postgresql+psycopg://markettrace:markettrace@localhost:5432/markettrace"
    )
    sec_user_agent: str = "MarketTrace dev youremail@example.com"
    opendart_api_key: str | None = None
    object_store_dir: str = "./_objectstore"
    # Which price data backend the US market uses.
    price_provider: Literal["tiingo", "stooq"] = "tiingo"
    tiingo_api_key: str | None = None
    # KR market-index proxy (KODEX 200 ETF) for abnormal-return computation.
    kr_market_index_ticker: str = "069500"
    # FRED/ALFRED macroeconomic data (surprise feature). Key is optional; macro
    # ingestion is skipped/raises clearly when unset.
    fred_api_key: str | None = None
    # Comma-separated FRED series ingested by default (markettrace-macro).
    macro_series: str = "CPIAUCSL,UNRATE,FEDFUNDS,DGS10"
    # Explicit model override. When None, the provider's default (above) is used.
    extraction_model: str | None = None
    # Comma-separated list of origins allowed by CORS (the deployed web URL).
    cors_allow_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Admin credentials + token-signing secret for the login-gated manual ingest.
    # All env-driven (sync:false on Render); login is disabled (503) when unset.
    admin_username: str | None = None
    admin_password: str | None = None
    auth_secret: str | None = None
    # Local card-statement PDFs used by the login-gated ledger view.
    card_statement_dir: str = "card_statement"
    card_statement_password: str | None = None
    # Merchant-name OCR for card statements. "auto" uses local macOS Vision when
    # available, then OpenAI when OPENAI_API_KEY is configured.
    ledger_ocr_provider: Literal["auto", "none", "swift", "openai"] = "auto"
    ledger_ocr_model: str = "gpt-4o-mini"
    # Local bank-account (passbook) PDFs used by the login-gated passbook view.
    passbook_dir: str = "passbook"
    passbook_password: str | None = None

    @field_validator("database_url")
    @classmethod
    def _normalize_db_scheme(cls, v: str) -> str:
        return normalize_db_url(v)

    @property
    def cors_origins_list(self) -> list[str]:
        """Parsed CORS origins from the comma-separated ``cors_allow_origins``."""
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def macro_series_list(self) -> list[str]:
        """Parsed FRED series ids from the comma-separated ``macro_series``."""
        return [s.strip() for s in self.macro_series.split(",") if s.strip()]

    @property
    def resolved_extraction_model(self) -> str:
        """Model id to use for extraction, falling back to the provider default."""
        return self.extraction_model or _DEFAULT_EXTRACTION_MODEL[self.llm_provider]

    @property
    def active_api_key(self) -> str | None:
        """API key for the currently selected ``llm_provider``."""
        if self.llm_provider == "openai":
            return self.openai_api_key
        return self.anthropic_api_key


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""

    return Settings()
