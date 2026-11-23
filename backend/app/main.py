"""The application factory."""

import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response

from app.config import get_settings
from app.db.session import Database
from app.errors import install_error_handlers
from app.health import router as health_router
from app.log import configure_logging
from app.vault import open_vault

REQUEST_ID_HEADER = "X-Request-ID"


async def add_request_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Give every request an id, use it in the logs and return it to the caller."""
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Open the vault and the database pool when the server starts, and close the pool when it
    stops. A missing or too short secret key stops the server from starting. Connecting to the
    database is lazy, so the server starts while the database is still coming up (/api/ready)."""
    app.state.vault = open_vault(get_settings())
    app.state.database = Database(get_settings().database_url)
    try:
        yield
    finally:
        await app.state.database.close()


def create_app() -> FastAPI:
    """Build the app. Called by the server (`app.main:create_app`) and by the tests."""
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="Blindspot",
        version=settings.release,
        lifespan=lifespan,
        # The interactive docs are for development only.
        docs_url="/api/docs" if settings.environment == "development" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.environment == "development" else None,
    )
    app.middleware("http")(add_request_id)
    install_error_handlers(app)
    app.include_router(health_router)
    return app
