"""Health and version, for the container's health check and the smoke test."""

from typing import cast

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.auth.deps import Anyone
from app.config import get_settings
from app.db.session import Database
from app.errors import AppError

router = APIRouter(prefix="/api", tags=["health"])


class Health(BaseModel):
    """What the health endpoint answers."""

    status: str
    release: str


@router.get("/health")
async def health(_: Anyone) -> Health:
    """Answers while the app can serve requests."""
    return Health(status="ok", release=get_settings().release)


@router.get("/ready")
async def ready(request: Request, _: Anyone) -> Health:
    """Answers once the database does too: for the start-up check, not the health check."""
    if not await cast("Database", request.app.state.database).is_ready():
        raise AppError(503, "database_unavailable", "The database is not ready yet")
    return Health(status="ok", release=get_settings().release)
