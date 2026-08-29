"""Local API token authentication (Phase 2).

Provides a FastAPI dependency that validates a shared bearer token on every
route except ``/health`` and ``/config``.  The token is auto-generated at
first run, persisted to ``<data_dir>/.api_token``, and printed once so the
user can configure external clients if needed.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

_bearer_scheme = HTTPBearer(auto_error=False)


async def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """Validate the bearer token against the configured API token.

    Raises 401 if the token is missing or does not match.
    """
    if credentials is None or credentials.credentials != settings.api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token.",
        )
