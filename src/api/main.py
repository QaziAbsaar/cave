"""FastAPI application entry point — Project Cave API.

Phase 4: Rate limiting, monitoring, auth hardening all wired here.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.database import engine
from src.api.routers import projects, models
from src.api.websocket import router as ws_router

logger = logging.getLogger(__name__)

ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan: cleanup on shutdown."""
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    """Application factory — builds and configures the FastAPI app."""
    app = FastAPI(
        title="Project Cave API",
        description="Multi-tenant SaaS platform that autonomously builds full-stack applications",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── CORS ────────────────────────────────────────────────────────────
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    if ENVIRONMENT == "production":
        origins = os.getenv("CORS_ORIGINS", "https://cave.app").split(",")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Rate limiting ───────────────────────────────────────────────────
    if RATE_LIMIT_ENABLED:
        from src.api.ratelimit import RateLimitMiddleware
        app.add_middleware(RateLimitMiddleware)
        logger.info("Rate limiting enabled")
    else:
        logger.info("Rate limiting disabled (RATE_LIMIT_ENABLED=false)")

    # ── Monitoring ──────────────────────────────────────────────────────
    from src.api.monitoring import setup_monitoring
    setup_monitoring(app)

    # ── Routers ─────────────────────────────────────────────────────────
    app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
    app.include_router(models.router, prefix="/api/v1/models", tags=["models"])
    app.include_router(ws_router, prefix="/ws", tags=["websocket"])

    return app


# Module-level app for uvicorn
app = create_app()
