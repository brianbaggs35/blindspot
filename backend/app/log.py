"""Structured logging: one JSON object per line, with the request id on every line."""

import logging
import sys

import structlog

from app.redact import RedactingFilter, redact_event


def configure_logging(level: str) -> None:
    """Send structlog and the standard library's logs to stdout as JSON."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level, force=True)
    for handler in logging.getLogger().handlers:
        handler.addFilter(RedactingFilter())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            redact_event,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )
