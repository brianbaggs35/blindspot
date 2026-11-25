"""What every parser shares: the limits, the error, and a way to collect items without going over.

A parser is a function from the tool's output (bytes) to a `ToolResult`. It never raises anything
but `ParseError`, whose message is safe to show, and it never trusts the output: output may be
malformed, hostile or enormous.
"""

import json
from collections.abc import Callable
from typing import TypeVar, cast

from app.tools.parsers.schema import MAX_ITEMS, MAX_WARNINGS, ToolResult

MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_JSON_DEPTH = 40

T = TypeVar("T")
JsonObject = dict[str, object]
Parser = Callable[[bytes], ToolResult]


class ParseError(ValueError):
    """The output cannot be understood. The message is safe to show."""


def check_size(data: bytes) -> None:
    """Refuse output too large to read at all (the runner caps output well below this)."""
    if len(data) > MAX_INPUT_BYTES:
        raise ParseError("The output is too large to read")


def text_of(data: bytes) -> str:
    """The output as text. Bytes that are not UTF-8 are replaced, never an error: tools print
    whatever the target sent."""
    check_size(data)
    return data.decode("utf-8", errors="replace")


def load_json(data: bytes) -> object:
    """JSON from a tool, or a `ParseError`. Deeply nested documents are refused."""
    text = text_of(data).strip()
    if not text:
        raise ParseError("The output is empty")
    try:
        document = json.loads(text)
    except json.JSONDecodeError, RecursionError:
        raise ParseError("The output is not valid JSON") from None
    if _too_deep(document):
        raise ParseError("The output is nested too deeply")
    return document


def _too_deep(value: object) -> bool:
    stack: list[tuple[object, int]] = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, dict | list):
            if depth >= MAX_JSON_DEPTH:
                return True
            children = cast(
                "list[object]",
                list(cast("JsonObject", item).values()) if isinstance(item, dict) else item,
            )
            stack.extend((child, depth + 1) for child in children)
    return False


def json_lines(data: bytes) -> tuple[list[JsonObject], int]:
    """The objects of a JSON Lines output, and how many lines were not one (a blank line is fine,
    and a tool's banner or progress line is counted, not fatal)."""
    objects: list[JsonObject] = []
    bad = 0
    for line in text_of(data).splitlines():
        if not line.strip():
            continue
        try:
            document = json.loads(line)
        except json.JSONDecodeError, RecursionError:
            bad += 1
            continue
        found = as_object(document)
        if found is not None and not _too_deep(found):
            objects.append(found)
        else:
            bad += 1
    return objects, bad


class Collector:
    """Adds items to a list up to the cap and notes when it had to stop."""

    def __init__(self) -> None:
        self.truncated = False
        self.warnings: list[str] = []

    def add(self, items: list[T], item: T) -> bool:
        if len(items) >= MAX_ITEMS:
            self.truncated = True
            return False
        items.append(item)
        return True

    def warn(self, message: str) -> None:
        if len(self.warnings) < MAX_WARNINGS:
            self.warnings.append(message[:300])


def clip(value: object, limit: int = 300) -> str | None:
    """Text from a field a tool printed, cut to size, or None when it is missing or empty."""
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def number(value: object) -> int | None:
    """A whole number from a field, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdecimal():
        return int(value)
    return None


def as_object(value: object) -> JsonObject | None:
    """The value if it is a JSON object, else None."""
    return cast("JsonObject", value) if isinstance(value, dict) else None


def as_list(value: object) -> list[object] | None:
    """The value if it is a JSON array, else None."""
    return cast("list[object]", value) if isinstance(value, list) else None
