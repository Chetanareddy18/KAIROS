"""Shared FastAPI dependencies."""
import secrets

from fastapi import Header, HTTPException, Query, Request

from backend.config import settings


def require_api_key(x_api_key: str | None = Header(default=None),
                    api_key: str | None = Query(default=None, include_in_schema=False)) -> None:
    """Enforced only when KAIROS_API_KEY is set (always set it in production)."""
    if not settings.api_key:
        return
    supplied = x_api_key or api_key or ""
    if not secrets.compare_digest(supplied, settings.api_key):
        raise HTTPException(401, "Missing or invalid API key (X-API-Key header)")


def get_pipeline(request: Request):
    p = getattr(request.app.state, "pipeline", None)
    if p is None:
        raise HTTPException(503, "Pipeline not initialised")
    return p


def dev_only() -> None:
    if settings.is_production:
        raise HTTPException(403, "Disabled in production")
