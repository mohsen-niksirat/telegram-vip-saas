"""API dependency: verify the X-API-Token header."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.config import settings


async def verify_api_token(x_api_token: str = Header(..., alias="X-API-Token")) -> str:
    """Dependency requiring ``X-API-Token`` to equal ``settings.API_TOKEN``."""
    if not settings.API_TOKEN or x_api_token != settings.API_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token")
    return x_api_token
