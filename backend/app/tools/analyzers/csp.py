"""A Content-Security-Policy evaluator: whether the policy would stop script injection."""

from app.tools.parsers.schema import Confidence, Issue, Severity

# Hosts that serve user-controlled or library script and so defeat a policy that allows them.
_BYPASS_HOSTS = (
    "ajax.googleapis.com",
    "cdnjs.cloudflare.com",
    "cdn.jsdelivr.net",
    "unpkg.com",
    "*.googleapis.com",
    "*.cloudfront.net",
    "*.amazonaws.com",
    "*.herokuapp.com",
    "*.firebaseapp.com",
    "*.appspot.com",
)
_SCRIPT_FALLBACK = ("script-src", "default-src")


def parse_csp(value: str) -> dict[str, list[str]]:
    """The directives of a policy. The first of a repeated directive wins, as in a browser."""
    directives: dict[str, list[str]] = {}
    for part in value.split(";"):
        words = part.split()
        if words and words[0].lower() not in directives:
            directives[words[0].lower()] = [word.lower() for word in words[1:]]
    return directives


def _issue(
    title: str, severity: Severity, detail: str, evidence: str | None = None, tag: str = "csp"
) -> Issue:
    return Issue(
        title=title,
        severity=severity,
        confidence=Confidence.FIRM,
        detail=detail,
        evidence=evidence,
        reference=f"csp:{tag}",
        tags=["csp", "headers"],
    )


def _script_sources(directives: dict[str, list[str]]) -> tuple[str, list[str]] | None:
    for name in _SCRIPT_FALLBACK:
        if name in directives:
            return name, directives[name]
    return None


def _script_problems(name: str, sources: list[str]) -> list[Issue]:
    strict = "'strict-dynamic'" in sources
    guarded = strict or any(s.startswith(("'nonce-", "'sha")) for s in sources)
    found: list[Issue] = []
    if "'unsafe-inline'" in sources and not guarded:
        found.append(
            _issue(
                "CSP allows inline script",
                Severity.MEDIUM,
                f"{name} contains 'unsafe-inline' with no nonce or hash, so an injected script "
                "tag or event handler runs.",
                f"{name} {' '.join(sources)}"[:300],
                "unsafe-inline",
            )
        )
    if "'unsafe-eval'" in sources:
        found.append(
            _issue(
                "CSP allows eval",
                Severity.LOW,
                f"{name} contains 'unsafe-eval', which lets injected text run as script.",
                tag="unsafe-eval",
            )
        )
    if not strict and any(s in ("*", "http:", "https:", "data:") for s in sources):
        wide = next(s for s in sources if s in ("*", "http:", "https:", "data:"))
        found.append(
            _issue(
                "CSP allows script from anywhere",
                Severity.MEDIUM,
                f"{name} contains {wide}, so script can be loaded from any matching address.",
                f"{name} {wide}",
                "wildcard-script",
            )
        )
    risky = [s for s in sources if s in _BYPASS_HOSTS]
    if risky and not strict:
        found.append(
            _issue(
                "CSP allows a host that serves script an attacker can use",
                Severity.LOW,
                "A shared script host in the policy can be used to run an attacker's code: "
                + ", ".join(risky[:5]),
                tag="bypass-host",
            )
        )
    return found


def evaluate_csp(value: str, report_only: bool = False) -> list[Issue]:
    """What is weak in a policy. A policy that only reports blocks nothing, so that is the one
    finding for it."""
    directives = parse_csp(value)
    if report_only:
        return [
            _issue(
                "CSP only reports, it does not block",
                Severity.LOW,
                "The policy is sent as Content-Security-Policy-Report-Only, so nothing is blocked.",
                tag="report-only",
            )
        ]
    found: list[Issue] = []
    scripts = _script_sources(directives)
    if scripts is None:
        found.append(
            _issue(
                "CSP does not limit script",
                Severity.MEDIUM,
                "The policy has neither script-src nor default-src.",
                tag="no-script-src",
            )
        )
    else:
        found += _script_problems(*scripts)
    if "object-src" not in directives and not (
        "default-src" in directives and directives["default-src"] == ["'none'"]
    ):
        found.append(
            _issue(
                "CSP does not restrict plug-in content",
                Severity.LOW,
                "No object-src (and no default-src 'none') lets an object or embed element "
                "load active content.",
                tag="no-object-src",
            )
        )
    if "base-uri" not in directives:
        found.append(
            _issue(
                "CSP does not restrict the base address",
                Severity.LOW,
                "Without base-uri an injected base tag can redirect every relative script.",
                tag="no-base-uri",
            )
        )
    if "frame-ancestors" not in directives:
        found.append(
            _issue(
                "CSP does not restrict who may frame the page",
                Severity.INFO,
                "Without frame-ancestors the page can be put in a frame on another site "
                "(clickjacking), unless X-Frame-Options says otherwise.",
                tag="no-frame-ancestors",
            )
        )
    return found
