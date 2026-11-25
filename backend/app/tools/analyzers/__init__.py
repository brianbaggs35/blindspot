"""The built-in tools: Python inside the app that reads pages through a fetcher and returns the
same `ToolResult` a parser makes. A manifest names its handler (`execution: builtin`).
"""

from collections.abc import Awaitable, Callable, Mapping

from app.tools.analyzers import entropy, headers, jwt, spider, wellknown
from app.tools.analyzers.fetch import Fetched, Fetcher, FetchError
from app.tools.parsers.schema import ToolResult

Handler = Callable[[Mapping[str, object], Fetcher], Awaitable[ToolResult]]

HANDLERS: dict[str, Handler] = {
    "headers": headers.run,
    "jwt": jwt.run,
    "wellknown": wellknown.run,
    "spider": spider.run,
    "entropy": entropy.run,
}

__all__ = ["HANDLERS", "FetchError", "Fetched", "Fetcher", "Handler"]
