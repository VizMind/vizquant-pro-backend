"""
FastAPI dependencies for authentication.

Token verification is delegated to the Supabase SDK (auth.get_user),
which works regardless of the JWT algorithm used by the project.

Two dependency functions are exposed:
  - get_current_user  : *requires* a valid token -> 401 if missing/invalid
  - get_optional_user : returns the user dict when a valid token is present, None otherwise
"""

import logging
from typing import Optional

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


def _extract_token(request: Request) -> Optional[str]:
    """Extract a Bearer token from the Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 7:
        return auth[7:]
    return None


def _verify_token(token: str) -> dict:
    """Verify a Supabase access token via the Supabase Auth API."""
    try:  # lazy import avoids circular deps; handles both run modes
        from backend.config import get_supabase_client
    except ImportError:
        from config import get_supabase_client  # type: ignore[no-redef]

    supabase = get_supabase_client()
    response = supabase.auth.get_user(token)

    if not response.user:
        raise ValueError("Token returned no user")

    return {
        "id": response.user.id,
        "email": response.user.email,
    }


async def get_current_user(request: Request) -> dict:
    """Require a valid Supabase token. Returns {"id", "email"}."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )
    try:
        return _verify_token(token)
    except Exception as exc:
        logger.warning("Token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )


async def get_optional_user(request: Request) -> Optional[dict]:
    """Return user dict if a valid token is present, else None."""
    token = _extract_token(request)
    if not token:
        return None
    try:
        return _verify_token(token)
    except Exception:
        return None
