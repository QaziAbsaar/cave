"""Monitoring — structured logging, health checks, Prometheus metrics.

Phase 4 production readiness.

Usage:
    from src.api.monitoring import setup_monitoring
    setup_monitoring(app)
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import time
from typing import Any, Dict

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────────────────

ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
SERVICE_NAME: str = "cave-api"
_VERSION: str = "0.1.0"

# Simple in-memory counters for /metrics
_metrics: Dict[str, Any] = {
    "requests_total": 0,
    "requests_active": 0,
    "requests_by_method": {},
    "requests_by_status": {},
    "errors_total": 0,
    "start_time": time.time(),
}


# ── Structured JSON logging ────────────────────────────────────────────────


class _JSONFormatter(logging.Formatter):
    """Format log records as JSON lines for production."""
    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


def setup_json_logging() -> None:
    """Replace root handler with JSON formatter in production."""
    if ENVIRONMENT != "development":
        root_logger = logging.getLogger()
        # Remove default handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        handler = logging.StreamHandler()
        handler.setFormatter(_JSONFormatter())
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)
        logger.info("Structured JSON logging enabled")


# ── Request metrics middleware ─────────────────────────────────────────────


class _MetricsMiddleware(BaseHTTPMiddleware):
    """Track request counts, active requests, error rates."""

    async def dispatch(self, request: Request, call_next) -> Response:
        _metrics["requests_total"] += 1
        _metrics["requests_active"] += 1
        method = request.method
        _metrics["requests_by_method"][method] = \
            _metrics["requests_by_method"].get(method, 0) + 1

        start = time.time()
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            _metrics["errors_total"] += 1
            _metrics["requests_active"] -= 1
            raise exc

        duration = time.time() - start
        _metrics["requests_active"] -= 1

        status_group = f"{status_code // 100}xx"
        _metrics["requests_by_status"][status_group] = \
            _metrics["requests_by_status"].get(status_group, 0) + 1

        if status_code >= 500:
            _metrics["errors_total"] += 1

        # Log slow requests
        if duration > 5.0:
            logger.warning(
                "Slow request: %s %s took %.2fs",
                method,
                request.url.path,
                duration,
            )

        return response


# ── Metric endpoints ──────────────────────────────────────────────────────


def _format_metrics() -> str:
    """Format metrics as Prometheus text format."""
    uptime = time.time() - _metrics["start_time"]
    lines = [
        f'# HELP cave_requests_total Total requests',
        f'# TYPE cave_requests_total counter',
        f'cave_requests_total {_metrics["requests_total"]}',
        '',
        f'# HELP cave_requests_active Currently active requests',
        f'# TYPE cave_requests_active gauge',
        f'cave_requests_active {_metrics["requests_active"]}',
        '',
        f'# HELP cave_errors_total Total errors',
        f'# TYPE cave_errors_total counter',
        f'cave_errors_total {_metrics["errors_total"]}',
        '',
        f'# HELP cave_uptime_seconds Service uptime',
        f'# TYPE cave_uptime_seconds gauge',
        f'cave_uptime_seconds {uptime:.0f}',
        '',
        f'# HELP cave_requests_by_method Request count by HTTP method',
        f'# TYPE cave_requests_by_method counter',
    ]
    for method, count in sorted(_metrics["requests_by_method"].items()):
        lines.append(f'cave_requests_by_method{{method="{method}"}} {count}')

    lines.append('')
    lines.append('# HELP cave_requests_by_status Request count by status group')
    lines.append('# TYPE cave_requests_by_status counter')
    for group, count in sorted(_metrics["requests_by_status"].items()):
        lines.append(f'cave_requests_by_status{{status="{group}"}} {count}')

    return '\n'.join(lines) + '\n'


def _health_check() -> Dict[str, Any]:
    """Return detailed health status."""
    uptime = time.time() - _metrics["start_time"]
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": _VERSION,
        "environment": ENVIRONMENT,
        "uptime_seconds": round(uptime, 1),
        "requests_total": _metrics["requests_total"],
        "errors_total": _metrics["errors_total"],
    }


# ── Setup function ─────────────────────────────────────────────────────────


def setup_monitoring(app: FastAPI) -> None:
    """Configure monitoring: JSON logging, metrics middleware, endpoints."""
    setup_json_logging()

    # Add metrics middleware
    app.add_middleware(_MetricsMiddleware)

    # Override /health with detailed check
    @app.get("/health", tags=["monitoring"])
    async def health():
        """Enhanced health check with service metrics."""
        return _health_check()

    # Add /metrics endpoint (Prometheus scrape target)
    @app.get("/metrics", tags=["monitoring"])
    async def metrics():
        """Prometheus metrics endpoint."""
        return Response(
            content=_format_metrics(),
            media_type="text/plain; version=0.0.4",
        )

    logger.info(
        "Monitoring initialized: environment=%s service=%s",
        ENVIRONMENT,
        SERVICE_NAME,
    )
