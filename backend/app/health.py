"""Health and version, for the container's health check and the smoke test."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(prefix="/api", tags=["health"])


class Health(BaseModel):
    """What the health endpoint answers."""

    status: str
    release: str


@router.get("/health")
async def health() -> Health:
    """Answers while the app can serve requests."""
    return Health(status="ok", release=get_settings().release)
