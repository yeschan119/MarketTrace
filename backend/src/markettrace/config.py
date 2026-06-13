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
    object_store_dir: str = "./_objectstore"
    # Which price data backend the US market uses.
    price_provider: Literal["tiingo", "stooq"] = "tiingo"
    tiingo_api_key: str | None = None
    # Explicit model override. When None, the provider's default (above) is used.
    extraction_model: str | None = None
    # Comma-separated list of origins allowed by CORS (the deployed web URL).
    cors_allow_origins: str = "http://localhost:3000"

    @field_validator("database_url")
    @classmethod
    def _normalize_db_scheme(cls, v: str) -> str:
        """Coerce ``postgres(ql)://`` URLs to the psycopg3 driver scheme.

        Managed hosts (Render, Heroku, etc.) hand out ``postgres://`` or
        ``postgresql://`` connection strings, but SQLAlchemy with psycopg3
        requires the explicit ``postgresql+psycopg://`` driver prefix.
        """
        for prefix in ("postgresql://", "postgres://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        """Parsed CORS origins from the comma-separated ``cors_allow_origins``."""
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

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
