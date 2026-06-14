"""JWT + API key authentication middleware and FastAPI dependency.

Phase 4 hardening:
- Dual auth: JWT (Bearer) or API key (X-API-Key header)
- Auth failure logging
- User tier extraction (for rate limiting)
- Rate limit context set on request.state
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")
ALGORITHM: str = "HS256"
DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

# Optional static API key for machine-to-machine auth
API_KEY: Optional[str] = os.getenv("API_KEY", None)

security = HTTPBearer(auto_error=False)

# ── Bypass paths (no auth required) ─────────────────────────────────────────

_PUBLIC_PATHS = frozenset({
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
})


async def authenticate_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Authenticate request and return user_id.

    Supports:
    1. JWT Bearer token (Authorization: Bearer <token>)
    2. API key (X-API-Key header)
    3. Dev mode: no auth → test user when DEBUG=true

    Sets request.state.user_id, request.state.user_tier for downstream
    middleware (rate limiter, RLS).
    """
    path = request.url.path

    # Public paths — no auth required
    if path in _PUBLIC_PATHS or path.startswith("/openapi.json"):
        request.state.user_id = None
        request.state.user_tier = "free"
        return "anonymous"

    # ── Dev mode bypass ────────────────────────────────────────────
    if DEBUG and credentials is None and API_KEY is None:
        user_id = "00000000-0000-0000-0000-000000000000"
        request.state.user_id = user_id
        request.state.user_tier = "free"
        return user_id

    # ── API key auth ────────────────────────────────────────────────
    api_key = request.headers.get("X-API-Key")
    if api_key and API_KEY:
        if api_key == API_KEY:
            user_id = "api-user"
            request.state.user_id = user_id
            request.state.user_tier = "enterprise"  # API keys get enterprise tier
            return user_id
        else:
            logger.warning("Invalid API key attempt from %s", request.client.host)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "ApiKey"},
            )

    # ── JWT auth ───────────────────────────────────────────────────
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide Bearer token or X-API-Key header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub", "")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject (sub)",
            )

        # Extract user tier from token claims (default: free)
        user_tier: str = payload.get("tier", "free")
        if user_tier not in ("free", "pro", "enterprise"):
            user_tier = "free"

        request.state.user_id = user_id
        request.state.user_tier = user_tier
        return user_id

    except JWTError as exc:
        logger.warning("JWT validation failed from %s: %s", request.client.host, exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


# Re-export the dependency as `get_current_user` for backward compat
get_current_user = authenticate_request
