"""b.headers: the security headers, cookies, CORS and CSP of one page."""

import re
from collections.abc import Mapping

from app.tools.analyzers.csp import evaluate_csp
from app.tools.analyzers.fetch import Fetched, Fetcher
from app.tools.parsers.base import Collector, clip
from app.tools.parsers.schema import (
    Confidence,
    HttpResponse,
    Issue,
    Severity,
    Technology,
    ToolResult,
)

HSTS_MIN_SECONDS = 15_552_000  # six months
PROBE_ORIGIN = "https://blindspot-cors-probe.invalid"
_MAX_AGE = re.compile(r"max-age\s*=\s*\"?(\d{1,12})", re.IGNORECASE)
_VERSIONED = re.compile(r"[A-Za-z][\w.-]*/\d|\d+\.\d+")
_LEAKY = ("server", "x-powered-by", "x-aspnet-version", "x-aspnetmvc-version")
_REFERRER_LEAKY = ("unsafe-url", "no-referrer-when-downgrade", "origin-when-cross-origin")


def _issue(
    title: str,
    severity: Severity,
    detail: str,
    target: str,
    tag: str,
    *,
    evidence: str | None = None,
    confidence: Confidence = Confidence.CERTAIN,
) -> Issue:
    return Issue(
        title=title,
        severity=severity,
        confidence=confidence,
        target=target[:4000],
        detail=detail,
        evidence=evidence[:4000] if evidence else None,
        reference=f"headers:{tag}",
        tags=["headers"],
    )


def _hsts(response: Fetched) -> list[Issue]:
    value = response.header("strict-transport-security")
    if value is None:
        return [
            _issue(
                "Strict-Transport-Security is missing",
                Severity.LOW,
                "Browsers are not told to use HTTPS only, so a first visit can be downgraded.",
                response.url,
                "no-hsts",
            )
        ]
    match = _MAX_AGE.search(value)
    age = int(match.group(1)) if match else 0
    if age < HSTS_MIN_SECONDS:
        return [
            _issue(
                "Strict-Transport-Security is short",
                Severity.LOW,
                f"max-age is {age} seconds; at least {HSTS_MIN_SECONDS} (six months) is advised.",
                response.url,
                "short-hsts",
                evidence=value,
            )
        ]
    return []


def _framing(response: Fetched) -> list[Issue]:
    csp = response.header("content-security-policy") or ""
    if "frame-ancestors" in csp.lower():
        return []
    option = (response.header("x-frame-options") or "").strip().upper()
    if option in ("DENY", "SAMEORIGIN"):
        return []
    return [
        _issue(
            "The page can be framed by any site",
            Severity.LOW,
            "Neither X-Frame-Options nor a CSP frame-ancestors directive stops other sites "
            "from framing the page (clickjacking).",
            response.url,
            "framing",
            evidence=f"X-Frame-Options: {option}" if option else None,
        )
    ]


def _basic_headers(response: Fetched) -> list[Issue]:
    found: list[Issue] = []
    if response.url.lower().startswith("https://"):
        found += _hsts(response)
    if (response.header("x-content-type-options") or "").strip().lower() != "nosniff":
        found.append(
            _issue(
                "X-Content-Type-Options is not nosniff",
                Severity.LOW,
                "Browsers may guess a content type and run a file as script.",
                response.url,
                "no-nosniff",
            )
        )
    found += _framing(response)
    referrer = (response.header("referrer-policy") or "").strip().lower()
    if not referrer or referrer in _REFERRER_LEAKY:
        found.append(
            _issue(
                "Referrer-Policy is missing or sends the full address",
                Severity.INFO,
                "The address of this page, with its query string, can be sent to other sites.",
                response.url,
                "referrer",
                evidence=referrer or None,
            )
        )
    if response.header("permissions-policy") is None:
        found.append(
            _issue(
                "Permissions-Policy is missing",
                Severity.INFO,
                "Powerful browser features are not switched off for this page.",
                response.url,
                "no-permissions-policy",
            )
        )
    return found


def _csp(response: Fetched) -> list[Issue]:
    enforced = response.header("content-security-policy")
    report_only = response.header("content-security-policy-report-only")
    if enforced is None and report_only is None:
        return [
            _issue(
                "Content-Security-Policy is missing",
                Severity.MEDIUM,
                "Nothing limits where script can come from, so an injected script runs.",
                response.url,
                "no-csp",
            )
        ]
    problems = evaluate_csp(enforced, False) if enforced else evaluate_csp(report_only or "", True)
    return [
        issue.model_copy(update={"target": response.url[:4000], "confidence": Confidence.FIRM})
        for issue in problems
    ]


def _leaks(response: Fetched, technologies: list[Technology]) -> list[Issue]:
    found: list[Issue] = []
    for name in _LEAKY:
        for value in response.headers_named(name):
            if _VERSIONED.search(value):
                found.append(
                    _issue(
                        f"{name} reveals a version",
                        Severity.INFO,
                        "Software names and versions help an attacker pick a known exploit.",
                        response.url,
                        f"leak-{name}",
                        evidence=f"{name}: {value}",
                    )
                )
                product, _, version = value.partition("/")
                technologies.append(
                    Technology(
                        name=product.strip()[:300],
                        version=clip(version.split()[0] if version.split() else None, 100),
                        target=response.url[:300],
                    )
                )
    return found


def analyze_cookies(response: Fetched) -> list[Issue]:
    """What is missing from each `Set-Cookie`. The value is never printed."""
    secure_page = response.url.lower().startswith("https://")
    found: list[Issue] = []
    for line in response.headers_named("set-cookie"):
        parts = [part.strip() for part in line.split(";")]
        name = parts[0].partition("=")[0].strip()[:100]
        flags = {
            part.split("=")[0].strip().lower(): part.partition("=")[2].strip().lower()
            for part in parts[1:]
        }
        missing = [
            flag
            for flag, wanted in (("secure", secure_page), ("httponly", True))
            if wanted and flag not in flags
        ]
        samesite = flags.get("samesite")
        if samesite is None:
            missing.append("samesite")
        elif samesite == "none" and "secure" not in flags and "secure" not in missing:
            missing.append("secure (needed with SameSite=None)")
        if name.lower().startswith("__host-") and not (
            "secure" in flags and "path" in flags and flags["path"] == "/" and "domain" not in flags
        ):
            missing.append("the __Host- rules")
        if missing:
            found.append(
                _issue(
                    f"Cookie {name} is missing {', '.join(missing)}",
                    Severity.LOW,
                    "A cookie without these flags can be read by script, sent over plain HTTP "
                    "or sent with cross-site requests.",
                    response.url,
                    "cookie",
                    evidence=f"Set-Cookie: {name}=… ({', '.join(sorted(flags)) or 'no flags'})",
                )
            )
    return found


def analyze_cors(plain: Fetched, probed: Fetched | None) -> list[Issue]:
    """Whether another site may read the answers. `probed` is the same page asked for with a
    made-up `Origin`."""
    found: list[Issue] = []
    for response, origin in ((plain, None), (probed, PROBE_ORIGIN)):
        if response is None:
            continue
        allow = (response.header("access-control-allow-origin") or "").strip()
        credentials = (response.header("access-control-allow-credentials") or "").lower() == "true"
        if allow == "*":
            found.append(
                _issue(
                    "CORS allows every site to read this page",
                    Severity.MEDIUM if credentials else Severity.LOW,
                    "Access-Control-Allow-Origin is *. Browsers refuse credentials with it, "
                    "but any site can read the page's public answers.",
                    response.url,
                    "cors-wildcard",
                    evidence="Access-Control-Allow-Origin: *",
                )
            )
        elif origin is not None and allow == origin:
            found.append(
                _issue(
                    "CORS repeats any Origin it is sent",
                    Severity.HIGH if credentials else Severity.MEDIUM,
                    "A made-up site was allowed to read this page"
                    + (" with the visitor's cookies." if credentials else "."),
                    response.url,
                    "cors-reflected",
                    evidence=f"Origin: {origin} -> Access-Control-Allow-Origin: {allow}",
                )
            )
        elif allow == "null":
            found.append(
                _issue(
                    "CORS allows the null origin",
                    Severity.MEDIUM if credentials else Severity.LOW,
                    "Pages in a sandboxed frame send Origin: null, so any site can read this page.",
                    response.url,
                    "cors-null",
                    evidence="Access-Control-Allow-Origin: null",
                )
            )
    return found


def analyze_response(plain: Fetched, probed: Fetched | None) -> ToolResult:
    """Everything wrong with one page's headers, cookies, CORS and CSP."""
    technologies: list[Technology] = []
    issues = [
        *_basic_headers(plain),
        *_csp(plain),
        *_leaks(plain, technologies),
        *analyze_cookies(plain),
        *analyze_cors(plain, probed),
    ]
    found = Collector()
    kept: list[Issue] = []
    for issue in issues:
        if not found.add(kept, issue):
            break
    return ToolResult(
        tool="b.headers",
        parser="builtin",
        http=[
            HttpResponse(
                url=plain.url[:4000],
                status=plain.status if 100 <= plain.status <= 599 else None,
                content_type=clip(plain.header("content-type")),
                server=clip(plain.header("server")),
                redirect=clip(plain.header("location"), 4000),
            )
        ],
        technologies=technologies,
        issues=kept,
        truncated=found.truncated,
        warnings=found.warnings,
    )


async def run(values: Mapping[str, object], fetcher: Fetcher) -> ToolResult:
    """Fetch the page, then again with a made-up Origin, and analyze both."""
    url = str(values["url"])
    plain = await fetcher.get(url)
    probed = await fetcher.get(url, {"Origin": PROBE_ORIGIN})
    return analyze_response(plain, probed)
