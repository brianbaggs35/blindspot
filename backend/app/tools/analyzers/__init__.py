"""The built-in tools: Python inside the app that reads pages through a fetcher and returns the
same `ToolResult` a parser makes. A manifest names its handler (`execution: builtin`).
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping

from app.tools.analyzers import entropy, headers, jwt, spider, wellknown
from app.tools.analyzers.fetch import Fetched, Fetcher, FetchError
from app.tools.parsers.schema import ToolResult

Handler = Callable[[Mapping[str, object], Fetcher], Awaitable[ToolResult]]


def _offline(inspect: Callable[[Mapping[str, object]], ToolResult]) -> Handler:
    """A handler for a tool that reads nothing from the target, so it has no use for a fetcher."""

    async def handler(values: Mapping[str, object], _fetcher: Fetcher) -> ToolResult:
        return await asyncio.to_thread(inspect, values)

    return handler


HANDLERS: dict[str, Handler] = {
    "headers": headers.run,
    "jwt": _offline(jwt.run),
    "wellknown": wellknown.run,
    "spider": spider.run,
    "entropy": entropy.run,
}

__all__ = ["HANDLERS", "FetchError", "Fetched", "Fetcher", "Handler"]
