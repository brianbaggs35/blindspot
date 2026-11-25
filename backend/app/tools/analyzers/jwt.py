"""b.jwt: what is wrong with a JSON Web Token, read without ever verifying it.

The token is decoded, never checked against a key, and never written to a result: the findings
name claims and header fields, not their values, except for harmless ones. A token that is longer
than `MAX_TOKEN` is refused rather than decoded.
"""

import base64
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime

from app.tools.parsers.base import JsonObject, as_object, number
from app.tools.parsers.schema import Confidence, Issue, Severity, ToolResult

MAX_TOKEN = 4000
TOOL = "b.jwt"
LONG_LIVED_SECONDS = 365 * 24 * 3600
_SEGMENT = re.compile(r"^[A-Za-z0-9_-]*$")
_SENSITIVE = re.compile(r"pass(word)?|secret|token|api[_-]?key|ssn|card|private", re.IGNORECASE)
_WEAK_HMAC = ("HS256", "HS384", "HS512")
_EMBEDDED_KEY = ("jku", "x5u", "jwk", "x5c")


def _decode(segment: str) -> JsonObject | None:
    try:
        raw = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
        return as_object(json.loads(raw.decode("utf-8")))
    except ValueError, RecursionError:  # binascii.Error is a ValueError
        return None


def _issue(title: str, severity: Severity, detail: str, tag: str) -> Issue:
    return Issue(
        title=title,
        severity=severity,
        confidence=Confidence.FIRM,
        detail=detail,
        reference=f"jwt:{tag}",
        tags=["jwt", "authentication"],
    )


def _algorithm_problems(header: JsonObject, signature: str) -> list[Issue]:
    alg = str(header.get("alg", "")).strip()
    found: list[Issue] = []
    if alg.lower() in ("none", ""):
        found.append(
            _issue(
                "The token says it is not signed",
                Severity.CRITICAL,
                "alg is none or missing. A server that accepts it lets anyone make a token.",
                "alg-none",
            )
        )
    elif not signature:
        found.append(
            _issue(
                "The token has no signature",
                Severity.HIGH,
                f"alg is {alg[:20]} but the signature part is empty. Test whether the server "
                "accepts it.",
                "no-signature",
            )
        )
    if alg.upper() in _WEAK_HMAC:
        found.append(
            _issue(
                "The token is signed with a shared secret",
                Severity.LOW,
                f"{alg.upper()} tokens can have a weak secret guessed offline. Try a wordlist, "
                "and test whether the server accepts an RS256 token re-signed with its own "
                "public key as the secret.",
                "hmac",
            )
        )
    return found


def _header_problems(header: JsonObject) -> list[Issue]:
    found = [
        _issue(
            f"The token header names its own key ({name})",
            Severity.MEDIUM,
            f"A server that follows {name} will verify a token with a key the sender "
            "chose. Test with a key you control.",
            f"header-{name}",
        )
        for name in _EMBEDDED_KEY
        if name in header
    ]
    kid = header.get("kid")
    if isinstance(kid, str) and re.search(r"[./\\'\";|`$]|\.\.", kid):
        found.append(
            _issue(
                "The key id has characters that suggest a file path or a query",
                Severity.MEDIUM,
                "A kid looked up in a file or a database can be injected into. Test path "
                "traversal and SQL injection through it.",
                "kid",
            )
        )
    return found


def _time_problems(claims: JsonObject, now: datetime) -> list[Issue]:
    found: list[Issue] = []
    expires = number(claims.get("exp"))
    issued = number(claims.get("iat"))
    if expires is None:
        found.append(
            _issue(
                "The token never expires",
                Severity.MEDIUM,
                "There is no exp claim, so a stolen token works forever.",
                "no-exp",
            )
        )
    else:
        base = issued if issued is not None else int(now.timestamp())
        if expires - base > LONG_LIVED_SECONDS:
            found.append(
                _issue(
                    "The token lives for more than a year",
                    Severity.LOW,
                    "A stolen token stays useful for a long time.",
                    "long-lived",
                )
            )
    return found


def _claim_problems(claims: JsonObject) -> list[Issue]:
    names = sorted(name for name in claims if _SENSITIVE.search(name))
    if not names:
        return []
    return [
        _issue(
            "The token carries claims that look sensitive",
            Severity.LOW,
            "A token is readable by anyone who holds it. Claims: "
            + ", ".join(n[:40] for n in names[:10]),
            "sensitive-claims",
        )
    ]


def inspect_jwt(token: str, now: datetime | None = None) -> ToolResult:
    """The problems with a token. `now` is a parameter so a test can fix the time."""
    parts = token.strip().split(".")
    if len(token) > MAX_TOKEN or len(parts) != 3 or not all(_SEGMENT.match(p) for p in parts):
        return ToolResult(
            tool=TOOL,
            parser="builtin",
            warnings=["The value is not a JSON Web Token (three dot-separated base64url parts)"],
        )
    header, claims = _decode(parts[0]), _decode(parts[1])
    if header is None or claims is None:
        return ToolResult(
            tool=TOOL,
            parser="builtin",
            warnings=["The token's header or claims are not JSON"],
        )
    issues = [
        *_algorithm_problems(header, parts[2]),
        *_header_problems(header),
        *_time_problems(claims, now or datetime.now(UTC)),
        *_claim_problems(claims),
    ]
    return ToolResult(tool=TOOL, parser="builtin", issues=issues)


def run(values: Mapping[str, object]) -> ToolResult:
    """Inspect the token the agent gives. Nothing is fetched."""
    return inspect_jwt(str(values["token"]))
