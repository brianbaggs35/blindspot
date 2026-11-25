"""b.wellknown: robots.txt, the sitemap and security.txt of a site."""

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

from app.tools.analyzers.fetch import Fetched, Fetcher, FetchError
from app.tools.parsers.base import Collector, ParseError
from app.tools.parsers.schema import Confidence, HttpResponse, Issue, Severity, ToolResult
from app.tools.parsers.xmlsafe import parse_xml

MAX_SITEMAPS = 3
_INTERESTING = re.compile(
    r"admin|backup|\.bak|config|\.git|\.env|internal|private|secret|staging|test|upload|"
    r"debug|console|phpinfo|dump|\.sql|old\b",
    re.IGNORECASE,
)


def _issue(title: str, severity: Severity, detail: str, target: str, tag: str) -> Issue:
    return Issue(
        title=title,
        severity=severity,
        confidence=Confidence.FIRM,
        target=target[:4000],
        detail=detail,
        reference=f"wellknown:{tag}",
        tags=["wellknown", "information-disclosure"],
    )


def parse_robots(text: str) -> tuple[list[str], list[str]]:
    """The paths robots.txt asks crawlers to stay out of, and the sitemaps it names."""
    paths: list[str] = []
    sitemaps: list[str] = []
    for raw in text.splitlines():
        field, _, value = raw.partition("#")[0].partition(":")
        value = value.strip()
        if not value:
            continue
        if field.strip().lower() == "disallow":
            paths.append(value[:300])
        elif field.strip().lower() == "sitemap":
            sitemaps.append(value[:1000])
    return list(dict.fromkeys(paths)), list(dict.fromkeys(sitemaps))


def robots_issues(url: str, text: str) -> list[Issue]:
    """What robots.txt gives away."""
    paths, _ = parse_robots(text)
    if not paths:
        return []
    interesting = [p for p in paths if _INTERESTING.search(p)]
    found = [
        _issue(
            f"robots.txt lists {len(paths)} paths",
            Severity.INFO,
            "Paths a site asks crawlers to avoid are often the ones worth testing.",
            url,
            "robots",
        ).model_copy(update={"evidence": ", ".join(paths[:15])[:4000]})
    ]
    if interesting:
        found.append(
            _issue(
                "robots.txt points at sensitive-looking paths",
                Severity.LOW,
                "Names such as admin, backup or config invite a look.",
                url,
                "robots-interesting",
            ).model_copy(update={"evidence": ", ".join(interesting[:15])[:4000]})
        )
    return found


def sitemap_urls(data: bytes) -> tuple[list[str], list[str]]:
    """The pages and the further sitemaps a sitemap lists. Raises `ParseError`."""
    root = parse_xml(data)
    kind = str(root.tag).rsplit("}", 1)[-1]
    if kind not in ("urlset", "sitemapindex"):
        raise ParseError("The output is not a sitemap")
    locations = [
        (element.text or "").strip()
        for element in root.iter()
        if str(element.tag).rsplit("}", 1)[-1] == "loc" and (element.text or "").strip()
    ]
    return (locations, []) if kind == "urlset" else ([], locations)


def parse_security_txt(text: str) -> dict[str, list[str]]:
    """The fields of a security.txt (RFC 9116), lower-cased by name."""
    fields: dict[str, list[str]] = {}
    for raw in text.splitlines():
        if raw.startswith("#") or ":" not in raw:
            continue
        name, _, value = raw.partition(":")
        fields.setdefault(name.strip().lower(), []).append(value.strip()[:500])
    return fields


def _expiry_problem(value: str, now: datetime) -> str | None:
    try:
        expires = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "Expires is not a date"
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return "The file has expired" if expires < now else None


def security_txt_issues(url: str, text: str, now: datetime) -> list[Issue]:
    """What is wrong with a security.txt that exists."""
    fields = parse_security_txt(text)
    found: list[Issue] = []
    if "contact" not in fields:
        found.append(
            _issue(
                "security.txt has no Contact",
                Severity.LOW,
                "Researchers have nobody to tell.",
                url,
                "txt-no-contact",
            )
        )
    if "expires" not in fields:
        found.append(
            _issue(
                "security.txt has no Expires",
                Severity.LOW,
                "RFC 9116 requires an Expires field so stale files are noticed.",
                url,
                "txt-no-expires",
            )
        )
    elif problem := _expiry_problem(fields["expires"][0], now):
        found.append(
            _issue("security.txt is out of date", Severity.LOW, problem, url, "txt-expired")
        )
    return found


async def _get(fetcher: Fetcher, url: str, warnings: Collector) -> Fetched | None:
    try:
        response = await fetcher.get(url)
    except FetchError as error:
        warnings.warn(f"{url}: {error}")
        return None
    return response if response.status == 200 else None


def _same_site(base: str, other: str) -> bool:
    return urlsplit(base).netloc.lower() == urlsplit(other).netloc.lower()


async def run(
    values: Mapping[str, object], fetcher: Fetcher, now: datetime | None = None
) -> ToolResult:
    """Fetch the three files from the site's root and report what they say."""
    parts = urlsplit(str(values["url"]))
    origin = f"{parts.scheme}://{parts.netloc}"
    clock = now or datetime.now(UTC)
    notes = Collector()
    issues: list[Issue] = []
    http: list[HttpResponse] = []
    robots = await _get(fetcher, f"{origin}/robots.txt", notes)
    declared: list[str] = []
    if robots is not None:
        issues += robots_issues(robots.url, robots.text())
        declared = parse_robots(robots.text())[1]
    queue = [u for u in declared if _same_site(origin, u)] or [f"{origin}/sitemap.xml"]
    for location in queue[:MAX_SITEMAPS]:
        sitemap = await _get(fetcher, urljoin(origin, location), notes)
        if sitemap is None:
            continue
        try:
            pages, _ = sitemap_urls(sitemap.body)
        except ParseError as error:
            notes.warn(f"{location}: {error}")
            continue
        for page in pages:
            if not notes.add(http, HttpResponse(url=page[:4000])):
                break
    for path in ("/.well-known/security.txt", "/security.txt"):
        found = await _get(fetcher, f"{origin}{path}", notes)
        if found is not None:
            issues += security_txt_issues(found.url, found.text(), clock)
            break
    else:
        issues.append(
            _issue(
                "No security.txt",
                Severity.INFO,
                "There is no published way to report a vulnerability (RFC 9116).",
                origin,
                "txt-missing",
            )
        )
    return ToolResult(
        tool="b.wellknown",
        parser="builtin",
        http=http,
        issues=issues,
        truncated=notes.truncated,
        warnings=notes.warnings,
    )
