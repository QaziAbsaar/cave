"""FastAPI application entry point — Project Cave API."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.database import engine
from src.api.routers import projects, models
from src.api.websocket import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: engine is created at import time. Shutdown: dispose."""
    yield
    await engine.dispose()


app = FastAPI(
    title="Project Cave API",
    description="Multi-tenant SaaS platform that autonomously builds full-stack applications",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow localhost:3000 for React dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(models.router, prefix="/api/v1/models", tags=["models"])
app.include_router(ws_router, prefix="/ws", tags=["websocket"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "cave-api"}
