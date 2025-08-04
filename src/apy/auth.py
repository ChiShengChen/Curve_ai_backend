from __future__ import annotations

"""Simple token-based authentication helpers."""

import os
from typing import Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()


def _load_tokens() -> Dict[str, str]:
    """Load user tokens from ``API_TOKENS`` env variable.

    The variable should contain comma separated ``user:token`` pairs, e.g.::

        API_TOKENS="alice:alice-token,bob:bob-token"
    """

    pairs = [item.split(":", 1) for item in os.getenv("API_TOKENS", "").split(",") if ":" in item]
    return {user: token for user, token in pairs}


TOKENS = _load_tokens()
TOKEN_TO_USER = {token: user for user, token in TOKENS.items()}


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Return the user_id associated with the provided bearer token."""

    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    user_id = TOKEN_TO_USER.get(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return user_id


def verify_user(user_id: str, current_user: str = Depends(get_current_user)) -> None:
    """Ensure the authenticated user can only access their own resources."""

    if user_id != current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
