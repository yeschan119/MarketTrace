"""FastAPI application factory for MarketTrace."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from markettrace.api.auth import router as auth_router
from markettrace.api.ingest import router as ingest_router
from markettrace.api.routes import router
from markettrace.config import get_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="MarketTrace API",
        version="0.1.0",
        description="Read API for MarketTrace market event analysis.",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    application.include_router(router)
    application.include_router(auth_router)
    application.include_router(ingest_router)

    return application


app = create_app()
