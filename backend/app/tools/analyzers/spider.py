"""b.spider: the forms, parameters and links of a site, found by reading its pages.

It reads HTML with the standard library's tolerant parser and never runs script. It stays on the
site it started on, fetches at most `MAX_PAGES` pages, and every page goes through the fetcher, so
the scope guard sees each request.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urldefrag, urljoin, urlsplit

from app.tools.analyzers.fetch import Fetched, Fetcher, FetchError
from app.tools.parsers.base import Collector, clip
from app.tools.parsers.schema import Confidence, HttpResponse, Issue, Severity, ToolResult

MAX_PAGES = 20
MAX_LINKS_PER_PAGE = 200
_CSRF_NAME = re.compile(r"csrf|xsrf|authenticity|nonce|_token|anti-?forgery", re.IGNORECASE)


@dataclass
class Form:
    """A form on a page."""

    action: str
    method: str
    inputs: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    autocomplete_off: bool = False

    def has(self, kind: str) -> bool:
        return any(k == kind for _, k in self.inputs)

    @property
    def names(self) -> list[str]:
        return [name for name, kind in self.inputs if name and kind not in ("submit", "button")]

    @property
    def has_token(self) -> bool:
        return any(kind == "hidden" and _CSRF_NAME.search(name) for name, kind in self.inputs)


class _Reader(HTMLParser):
    def __init__(self, base: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base = base
        self.links: list[str] = []
        self.forms: list[Form] = []
        self._open: Form | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): (value or "") for name, value in attrs}
        if tag in ("a", "area") and values.get("href"):
            self.links.append(urljoin(self.base, values["href"]))
        elif tag == "form":
            self._open = Form(
                action=urljoin(self.base, values.get("action") or self.base),
                method=(values.get("method") or "get").lower(),
                autocomplete_off=values.get("autocomplete", "").lower() == "off",
            )
            self.forms.append(self._open)
        elif tag in ("input", "textarea", "select") and self._open is not None:
            kind = values.get("type", "text").lower() if tag == "input" else tag
            self._open.inputs.append((values.get("name", "")[:100], kind))

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._open = None


def read_page(base: str, html: str) -> tuple[list[str], list[Form]]:
    """The links and forms of one page."""
    reader = _Reader(base)
    reader.feed(html)
    reader.close()
    return reader.links[:MAX_LINKS_PER_PAGE], reader.forms


def _web_address(link: str) -> str | None:
    cleaned, _ = urldefrag(link)
    return cleaned if urlsplit(cleaned).scheme in ("http", "https") else None


def _issue(title: str, severity: Severity, detail: str, target: str, tag: str) -> Issue:
    return Issue(
        title=title,
        severity=severity,
        confidence=Confidence.TENTATIVE,
        target=target[:4000],
        detail=detail,
        reference=f"spider:{tag}",
        tags=["spider", "forms"],
    )


def form_issues(page: str, form: Form) -> list[Issue]:
    """What is risky about one form."""
    found: list[Issue] = []
    secure_page = page.lower().startswith("https://")
    if form.has("password") and not form.action.lower().startswith("https://"):
        found.append(
            _issue(
                "A password is sent without HTTPS",
                Severity.HIGH,
                "The form that asks for a password posts to an address that is not HTTPS.",
                form.action,
                "password-http",
            )
        )
    elif secure_page and form.method == "post" and form.action.lower().startswith("http://"):
        found.append(
            _issue(
                "A form on an HTTPS page posts to HTTP",
                Severity.MEDIUM,
                "What is typed into the form is sent in the clear.",
                form.action,
                "mixed-form",
            )
        )
    if form.method == "post" and not form.has_token:
        found.append(
            _issue(
                "A form that changes data shows no anti-forgery token",
                Severity.LOW,
                "No hidden field looks like a CSRF token. Cookies with SameSite may still "
                "protect it. Test a forged request.",
                form.action,
                "no-csrf-token",
            )
        )
    if form.has("password") and not form.autocomplete_off:
        found.append(
            _issue(
                "Password manager and browser may keep the password",
                Severity.INFO,
                "Normal for a login form; noted for a form where the password is a one-off.",
                form.action,
                "password-autocomplete",
            )
        )
    if form.has("file"):
        found.append(
            _issue(
                "The site takes file uploads",
                Severity.INFO,
                "File uploads are a classic place for stored script, path traversal and "
                "unchecked types. Test them.",
                form.action,
                "upload",
            )
        )
    return found


def _response_of(url: str, response: Fetched) -> HttpResponse:
    return HttpResponse(
        url=url[:4000],
        status=response.status if 100 <= response.status <= 599 else None,
        content_type=clip(response.header("content-type")),
    )


def _follow(
    response: Fetched, site: str, parameters: dict[str, set[str]], issues: list[Issue]
) -> list[str]:
    """Read one HTML page: note its forms and query parameters, and return the same-site links."""
    links, forms = read_page(response.url, response.text())
    for form in forms:
        parameters.setdefault(form.action, set()).update(form.names)
        issues.extend(form_issues(response.url, form))
    same_site: list[str] = []
    for link in map(_web_address, links):
        if link is None or urlsplit(link).netloc.lower() != site:
            continue
        for name, _ in parse_qsl(urlsplit(link).query, keep_blank_values=True):
            parameters.setdefault(link.split("?", 1)[0], set()).add(name[:100])
        same_site.append(link)
    return same_site


async def run(values: Mapping[str, object], fetcher: Fetcher) -> ToolResult:
    """Read up to `max_pages` pages of the site, starting at `url`."""
    start = str(values["url"])
    limit = min(int(str(values.get("max_pages", 5))), MAX_PAGES)
    site = urlsplit(start).netloc.lower()
    found = Collector()
    queue, seen = [start], {start}
    http: list[HttpResponse] = []
    issues: list[Issue] = []
    parameters: dict[str, set[str]] = {}
    pages = 0
    while queue and pages < limit:
        url = queue.pop(0)
        try:
            response = await fetcher.get(url)
        except FetchError as error:
            found.warn(f"{url}: {error}")
            continue
        pages += 1
        http.append(_response_of(url, response))
        if "html" not in (response.header("content-type") or "html").lower():
            continue
        for link in _follow(response, site, parameters, issues):
            if link not in seen:
                seen.add(link)
                queue.append(link)
    for address, names in sorted(parameters.items()):
        if names:
            found.add(http, HttpResponse(url=address[:4000], input=", ".join(sorted(names))[:300]))
    return ToolResult(
        tool="b.spider",
        parser="builtin",
        http=http,
        issues=issues,
        truncated=found.truncated,
        warnings=found.warnings,
    )
