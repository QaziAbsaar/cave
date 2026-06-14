"""JWT authentication middleware and FastAPI dependency."""

import os
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")
ALGORITHM: str = "HS256"
DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Extract user_id from JWT in Authorization header.

    In development mode (DEBUG=true) returns a default test user
    when no token is provided.
    """
    if DEBUG and credentials is None:
        return "00000000-0000-0000-0000-000000000000"

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
        )

    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
            )
        return user_id
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        ) from exc
