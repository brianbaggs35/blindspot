"""Cross-site request forgery: a request that changes something must come from this app's own
pages. Browsers say so in `Sec-Fetch-Site` and `Origin`; the session cookie is also SameSite=Strict.

A request is refused when it has the session cookie, or an `Origin`, but cannot show it is
same-origin. A script with no cookie (and so no way to act as anyone) is not affected.
"""

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import Request, Response

from app.auth.deps import COOKIE_NAME
from app.errors import problem

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def came_from_this_site(request: Request) -> bool:
    """Whether the browser vouches that the request is from this site's own page."""
    fetch_site = request.headers.get("sec-fetch-site")
    origin = request.headers.get("origin")
    if fetch_site is None and origin is None:
        return False
    if fetch_site is not None and fetch_site not in {"same-origin", "none"}:
        return False
    if origin is not None:
        host = request.headers.get("host", "")
        return urlsplit(origin).netloc.casefold() == host.casefold() and host != ""
    return True


async def csrf_guard(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Refuse a state-changing request that is not from this site's own pages."""
    changes_something = request.method not in SAFE_METHODS
    has_credentials = bool(request.cookies.get(COOKIE_NAME) or request.headers.get("origin"))
    if changes_something and has_credentials and not came_from_this_site(request):
        return problem(
            request, 403, "cross_site_request", "The request did not come from this site"
        )
    return await call_next(request)
