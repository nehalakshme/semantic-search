import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Header, HTTPException, status

SECRET = os.getenv("AUTH_SECRET", "docusearch-dev-secret-change-me-please")
ALGORITHM = "HS256"
TOKEN_TTL_HOURS = 8


def create_access_token(claims: dict) -> str:
    """claims should include at least `sub` (username); typically also node/label/level."""
    payload = {**claims, "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)}
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def decode_token(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        p = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        return {
            "username": p["sub"],
            "node": p.get("node"),
            "label": p.get("label"),
            "level": p.get("level"),
        }
    except Exception:
        return None


def _token_from_header(authorization: str | None) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    return None


async def get_current_user(authorization: str | None = Header(None)) -> dict:
    user = decode_token(_token_from_header(authorization))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
