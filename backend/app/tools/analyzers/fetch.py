"""How the built-in analyzers read a web page: through a `Fetcher` they are given.

An analyzer never opens a connection. The runner hands it a fetcher that checks every request, and
every redirect it follows, with the scope guard first (`app/tools/guard.py`), so an analyzer cannot
reach anything the pentest does not allow, and a test can hand it canned pages instead.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

# What a body is cut to before an analyzer reads it. A fetcher cuts at this too; this is the
# analyzer's own limit, for a fetcher that does not.
MAX_BODY = 2 * 1024 * 1024


class FetchError(Exception):
    """A page could not be fetched. The message is safe to show."""


@dataclass(frozen=True)
class Fetched:
    """One response. `headers` keeps every header, in order, so repeated ones (`Set-Cookie`) are
    not lost."""

    url: str
    status: int
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes = b""

    def header(self, name: str) -> str | None:
        """The first header of this name, or None."""
        found = self.headers_named(name)
        return found[0] if found else None

    def headers_named(self, name: str) -> list[str]:
        """Every header of this name."""
        wanted = name.lower()
        return [value for key, value in self.headers if key.lower() == wanted]

    def text(self) -> str:
        """The body as text, cut to `MAX_BODY`. Bytes that are not UTF-8 are replaced."""
        return self.body[:MAX_BODY].decode("utf-8", errors="replace")


class Fetcher(Protocol):
    """Sends one GET request and returns the answer. It raises `FetchError` for a request that is
    refused (out of scope, a redirect out of scope) or fails."""

    async def get(self, url: str, headers: Mapping[str, str] | None = None) -> Fetched: ...
