"""Errors as RFC 9457 problem details: a stable code, a safe message and the request id.

Clients get a generic message and a code; the server log has the detail. A stack trace is never
returned.
"""

from http import HTTPStatus
from typing import Any, cast

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"

log = structlog.get_logger()


class AppError(Exception):
    """An error with a status and a code that is safe to show to the person using the app."""

    def __init__(self, status: int, code: str, title: str, detail: str | None = None) -> None:
        super().__init__(title)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail


class BudgetExceeded(AppError):  # noqa: N818  # the plan's name for this error
    """A provider's monthly budget is used up and it is set to stop there."""

    def __init__(self, provider: str) -> None:
        super().__init__(
            402,
            "budget_exceeded",
            f"The monthly budget for {provider} is used up",
            "Raise the budget, or turn off the hard stop, in the AI provider settings.",
        )


def problem(
    request: Request,
    status: int,
    code: str,
    title: str,
    *,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build a problem details response."""
    body: dict[str, Any] = {
        "type": f"https://blindspot.invalid/problems/{code}",
        "title": title,
        "status": status,
        "code": code,
        "request_id": getattr(request.state, "request_id", None),
    }
    if detail:
        body["detail"] = detail
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)


def _app_error(request: Request, exc: Exception) -> JSONResponse:
    error = cast("AppError", exc)  # registered for AppError only
    return problem(request, error.status, error.code, error.title, detail=error.detail)


def _http_error(request: Request, exc: Exception) -> JSONResponse:
    error = cast("StarletteHTTPException", exc)  # registered for it only
    phrase = HTTPStatus(error.status_code).phrase
    return problem(request, error.status_code, f"http_{error.status_code}", phrase)


def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    error = cast("RequestValidationError", exc)  # registered for it only
    fields = [
        {"field": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
        for item in error.errors()
    ]
    return problem(
        request, 422, "validation_failed", "The request is not valid", extra={"errors": fields}
    )


def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled_error", exc_info=exc, path=request.url.path)
    return problem(request, 500, "internal_error", "Something went wrong on the server")


def install_error_handlers(app: FastAPI) -> None:
    """Make every error the app can raise come out as problem details."""
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unexpected_error)
