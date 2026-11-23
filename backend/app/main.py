"""The application factory."""

import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response

from app.auth.csrf import csrf_guard
from app.auth.ratelimit import FailureLimiter
from app.auth.setup_code import SetupGate
from app.config import get_settings
from app.db.session import Database
from app.errors import install_error_handlers
from app.log import configure_logging
from app.routers import ROUTERS
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
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Open the vault and the database pool when the server starts, and close the pool when it
    stops. A missing or too short secret key stops the server from starting. Connecting to the
    database is lazy, so the server starts while the database is still coming up (/api/ready)."""
    app.state.vault = open_vault(get_settings())
    app.state.database = Database(get_settings().database_url)
    await app.state.setup_gate.prepare(app.state.database)
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
    app.state.limiter = FailureLimiter(
        settings.throttle_failures, settings.throttle_window_minutes * 60
    )
    app.state.passkey_limiter = FailureLimiter(
        settings.passkey_failures, settings.throttle_window_minutes * 60
    )
    chosen = settings.setup_code.get_secret_value() if settings.setup_code else None
    app.state.setup_gate = SetupGate(chosen)
    # The last one added runs first: the request id is made before anything can refuse a request.
    app.middleware("http")(csrf_guard)
    app.middleware("http")(add_request_id)
    install_error_handlers(app)
    for router in ROUTERS:
        app.include_router(router)
    return app
