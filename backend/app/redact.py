"""Keep secrets out of logs: anything that looks like one is replaced before it is written.

This is the last line of defence. The first is that secrets are sealed and never put in a log
call. It errs on the side of hiding too much.
"""

import logging
import re
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any, cast

REDACTED = "[redacted]"

_PATTERNS = [
    # A sealed envelope from the vault.
    re.compile(r"v1:[0-9a-f]{8}:[A-Za-z0-9_-]+:[A-Za-z0-9_-]+"),
    # Provider keys (sk-..., sk-ant-...), GitHub tokens, AWS access key ids, JSON web tokens.
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+"),
    # Private key blocks.
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    # Credentials in a URL.
    re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)"),
]
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
_ASSIGNMENT = re.compile(
    r"(?i)(\b[\w-]*(?:api[_-]?key|secret|(?<![a-z])token(?![a-z])|passw(?:or)?d|passwd"
    r"|authorization|cookie)[\w-]*"
    r"[\"']?\s*[:=]\s*[\"']?)([^\s\"',;&]+)"
)
_SENSITIVE_KEY = re.compile(
    r"(?i)(api[_-]?key|secret|(?<![a-z])token(?![a-z])|passw(?:or)?d|passwd|authorization|cookie"
    r"|private[_-]?key)"
)
_MAX_DEPTH = 8


def redact(text: str) -> str:
    """The text with anything that looks like a secret hidden."""
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    text = _BEARER.sub(lambda match: f"{match.group(1)} {REDACTED}", text)
    return _ASSIGNMENT.sub(lambda match: f"{match.group(1)}{REDACTED}", text)


def redact_value(value: Any, depth: int = 0) -> Any:
    """Redact a log value: text is scrubbed, and so is whatever is inside lists and mappings."""
    if isinstance(value, str):
        return redact(value)
    if depth >= _MAX_DEPTH:
        return REDACTED
    if isinstance(value, Mapping):
        mapping = cast("Mapping[Any, Any]", value)
        return {
            key: REDACTED if _SENSITIVE_KEY.search(str(key)) else redact_value(item, depth + 1)
            for key, item in mapping.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [redact_value(item, depth + 1) for item in cast("Sequence[Any]", value)]
    return value


def redact_event(
    _logger: object, _method: str, event: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """A structlog processor: runs before the line is written."""
    return {
        key: REDACTED if _SENSITIVE_KEY.search(key) else redact_value(value)
        for key, value in event.items()
    }


class RedactingFilter(logging.Filter):
    """The same for the standard library's logging (uvicorn, SQLAlchemy and the like)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        return True


def mask(secret: str) -> str:
    """How a stored secret is shown: only the last four characters, and only when it is long."""
    if len(secret) < 12:
        return "••••"
    return f"••••{secret[-4:]}"
