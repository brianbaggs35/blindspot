"""b.entropy: whether session tokens can be guessed.

Asks for a page several times without a cookie, collects the session cookie each answer sets, and
looks at what was issued: repeats, a counter, a short or small-alphabet value, a shared prefix. A
token's value is never written to a result, only its length and an estimate of its strength.
"""

import itertools
import math
import re
from collections import Counter
from collections.abc import Mapping

from app.tools.analyzers.fetch import Fetcher
from app.tools.parsers.schema import Confidence, Issue, Severity, ToolResult

MIN_BITS = 64  # OWASP's advice for a session id
GOOD_BITS = 112
MAX_SAMPLES = 30
_SESSIONISH = re.compile(r"sess|sid|token|auth|jwt|login|phpsessid|jsessionid", re.IGNORECASE)


def _alphabet(token: str) -> int:
    size = 0
    if re.search(r"[a-z]", token):
        size += 26
    if re.search(r"[A-Z]", token):
        size += 26
    if re.search(r"[0-9]", token):
        size += 10
    if re.search(r"[^A-Za-z0-9]", token):
        size += 30
    return size


def estimate_bits(token: str) -> float:
    """A cautious guess at the guessing work in a token: the smaller of what its length and
    alphabet allow and what its own letter frequencies show."""
    if not token:
        return 0.0
    by_alphabet = len(token) * math.log2(max(_alphabet(token), 2))
    counts = Counter(token)
    shannon = -sum(n / len(token) * math.log2(n / len(token)) for n in counts.values())
    return min(by_alphabet, shannon * len(token))


def _counter(tokens: list[str]) -> bool:
    numbers = [int(t) for t in tokens if t.isdecimal()]
    if len(numbers) != len(tokens) or len(numbers) < 3:
        return False
    steps = {b - a for a, b in itertools.pairwise(numbers)}
    return len(steps) == 1 and steps != {0}


def _issue(title: str, severity: Severity, detail: str, tag: str, name: str) -> Issue:
    return Issue(
        title=title,
        severity=severity,
        confidence=Confidence.FIRM,
        detail=detail,
        reference=f"entropy:{tag}",
        tags=["session", "entropy"],
        evidence=f"cookie {name[:60]}",
    )


def analyze_tokens(name: str, tokens: list[str]) -> list[Issue]:
    """What is predictable about the tokens one cookie was given over several requests."""
    if not tokens:
        return []
    found: list[Issue] = []
    if len(set(tokens)) < len(tokens):
        found.append(
            _issue(
                f"Cookie {name} gave the same value to different visitors",
                Severity.HIGH,
                "Requests with no cookie were issued a value that had been issued before.",
                "repeat",
                name,
            )
        )
    if _counter(tokens):
        found.append(
            _issue(
                f"Cookie {name} counts up",
                Severity.CRITICAL,
                "The values form a sequence, so the next visitor's value can be guessed.",
                "counter",
                name,
            )
        )
    weakest = min(estimate_bits(t) for t in tokens)
    shortest = min(len(t) for t in tokens)
    if weakest < MIN_BITS:
        found.append(
            _issue(
                f"Cookie {name} is too easy to guess",
                Severity.HIGH,
                f"About {weakest:.0f} bits of guessing work in a value of {shortest} "
                f"characters; at least {MIN_BITS} are needed.",
                "weak",
                name,
            )
        )
    elif weakest < GOOD_BITS:
        found.append(
            _issue(
                f"Cookie {name} is short for a session id",
                Severity.INFO,
                f"About {weakest:.0f} bits; {GOOD_BITS} or more is comfortable.",
                "short",
                name,
            )
        )
    if len(tokens) > 1:
        prefix = len(_common_prefix(tokens))
        if prefix >= max(8, shortest // 4):
            found.append(
                _issue(
                    f"Cookie {name} values share a long start",
                    Severity.LOW,
                    f"The first {prefix} characters never change, so they add no strength.",
                    "prefix",
                    name,
                )
            )
    return found


def _common_prefix(tokens: list[str]) -> str:
    first, last = min(tokens), max(tokens)
    size = 0
    while size < len(first) and size < len(last) and first[size] == last[size]:
        size += 1
    return first[:size]


def _cookies(set_cookie: list[str]) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for line in set_cookie:
        name, _, rest = line.partition("=")
        cookies[name.strip()[:100]] = rest.partition(";")[0].strip()
    return cookies


async def run(values: Mapping[str, object], fetcher: Fetcher) -> ToolResult:
    """Collect up to `samples` session cookies from `url` and judge them."""
    url = str(values["url"])
    wanted = values.get("cookie")
    samples = min(int(str(values.get("samples", 10))), MAX_SAMPLES)
    seen: dict[str, list[str]] = {}
    for _ in range(samples):
        response = await fetcher.get(url)
        for name, value in _cookies(response.headers_named("set-cookie")).items():
            if (wanted and name == wanted) or (not wanted and _SESSIONISH.search(name)):
                seen.setdefault(name, []).append(value)
    issues = [
        issue for name, tokens in sorted(seen.items()) for issue in analyze_tokens(name, tokens)
    ]
    warnings = [] if seen else ["No session cookie was set, so there was nothing to measure"]
    return ToolResult(tool="b.entropy", parser="builtin", issues=issues, warnings=warnings)
