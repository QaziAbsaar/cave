"""Rate limiting middleware — Redis-backed token bucket with in-memory fallback.

Usage:
    from src.api.ratelimit import RateLimitMiddleware

    app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)

Or apply per-route with the @rate_limit decorator.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────────────────

RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Default limits: (max_requests, window_seconds) per tier
_DEFAULT_LIMITS: Dict[str, Tuple[int, int]] = {
    "free":       (20,   60),    # 20 req/min
    "pro":        (100,  60),    # 100 req/min
    "enterprise": (500,  60),    # 500 req/min
}

# Endpoints that bypass rate limiting (health, metrics)
_BYPASS_PATHS: List[str] = ["/health", "/metrics", "/docs", "/openapi.json"]


# ── Token Bucket (in-memory fallback) ──────────────────────────────────────


class _InMemoryBucket:
    """Simple in-memory token bucket for rate limiting when Redis is unavailable."""

    def __init__(self) -> None:
        self._buckets: Dict[str, Tuple[float, int]] = {}  # key -> (reset_time, count)

    def check(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """Return (allowed, remaining) for a request."""
        now = time.monotonic()
        reset_time, count = self._buckets.get(key, (now, 0))

        if now >= reset_time:
            # Window expired — reset
            reset_time = now + window_seconds
            count = 0

        count += 1
        self._buckets[key] = (reset_time, count)
        remaining = max(0, max_requests - count)

        return count <= max_requests, remaining

    def get_retry_after(self, key: str) -> float:
        reset_time, _ = self._buckets.get(key, (0.0, 0))
        return max(0.0, reset_time - time.monotonic())


# ── Redis-backed bucket ────────────────────────────────────────────────────


def _make_redis_client():
    """Create a Redis client for rate limiting."""
    try:
        import redis as sync_redis
        return sync_redis.from_url(REDIS_URL, socket_connect_timeout=2)
    except Exception:
        return None


class _RedisBucket:
    """Redis-based sliding window counter."""

    def __init__(self) -> None:
        self._client = _make_redis_client()

    def check(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """Return (allowed, remaining) using Redis sorted set sliding window."""
        if self._client is None:
            return True, max_requests  # fail open

        now = time.time()
        window_start = now - window_seconds
        redis_key = f"ratelimit:{key}"

        try:
            pipe = self._client.pipeline()
            # Remove old entries
            pipe.zremrangebyscore(redis_key, "-inf", window_start)
            # Count current window
            pipe.zcard(redis_key)
            # Add this request
            pipe.zadd(redis_key, {str(now): now})
            # Set TTL
            pipe.expire(redis_key, window_seconds * 2)

            _, count, _, _ = pipe.execute()
            remaining = max(0, max_requests - count)
            return count <= max_requests, remaining

        except Exception as exc:
            logger.warning("Redis rate limit check failed (fail open): %s", exc)
            return True, max_requests

    def get_retry_after(self, key: str) -> float:
        if self._client is None:
            return 0.0
        try:
            ttl = self._client.ttl(f"ratelimit:{key}")
            return max(0.0, float(ttl)) if ttl > 0 else 0.0
        except Exception:
            return 0.0


# ── Middleware ─────────────────────────────────────────────────────────────


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that rate-limits requests per user.

    Uses Redis when available, falls back to in-memory token bucket.
    Limits are tier-based (free/pro/enterprise).

    Set RATE_LIMIT_ENABLED=false to disable.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_requests: Optional[int] = None,
        window_seconds: int = 60,
        limits: Optional[Dict[str, Tuple[int, int]]] = None,
    ) -> None:
        super().__init__(app)
        self._max_requests = max_requests  # overrides tier-based limits
        self._window_seconds = window_seconds
        self._limits = limits or _DEFAULT_LIMITS

        # Try Redis first, fall back to in-memory
        self._redis = _RedisBucket()
        # Check if Redis is actually connected
        self._in_memory = _InMemoryBucket()
        self._use_redis = False
        try:
            # Verify connection
            import redis as sync_redis
            r = sync_redis.from_url(REDIS_URL, socket_connect_timeout=2)
            r.ping()
            self._use_redis = True
            r.close()
        except Exception:
            logger.info("Rate limiter using in-memory bucket (Redis unavailable)")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check rate limit before processing request."""
        if not RATE_LIMIT_ENABLED:
            return await call_next(request)

        path = request.url.path
        # Bypass for health/metrics/docs
        if any(path.startswith(p) for p in _BYPASS_PATHS):
            return await call_next(request)

        # Determine user key
        user_id = self._get_user_id(request)
        tier = self._get_user_tier(request)
        key = f"{tier}:{user_id}" if user_id else f"ip:{request.client.host}"

        # Get limits for this tier
        if self._max_requests is not None:
            max_r, window_s = self._max_requests, self._window_seconds
        else:
            max_r, window_s = self._limits.get(tier, self._limits["free"])

        # Check bucket
        allowed, remaining = self._redis.check(key, max_r, window_s) if self._use_redis \
            else self._in_memory.check(key, max_r, window_s)

        if not allowed:
            retry_after = self._redis.get_retry_after(key) if self._use_redis \
                else self._in_memory.get_retry_after(key)

            logger.warning("Rate limit hit: key=%s tier=%s", key, tier)
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Too many requests",
                    "retry_after_seconds": round(retry_after, 1),
                },
                headers={
                    "X-RateLimit-Limit": str(max_r),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + retry_after)),
                    "Retry-After": str(int(retry_after)),
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(max_r)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_user_id(request: Request) -> Optional[str]:
        """Extract user identifier from request state or headers."""
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return str(user_id)
        # Fall back to Authorization header hash (don't log the actual token)
        auth = request.headers.get("Authorization", "")
        if auth:
            return f"token:{hash(auth) % 10_000_000:07d}"
        return None

    @staticmethod
    def _get_user_tier(request: Request) -> str:
        """Determine user tier from request state."""
        tier = getattr(request.state, "user_tier", None)
        if tier in ("free", "pro", "enterprise"):
            return tier
        return "free"
