"""The friendly view of a result: plain-language cards made from the normalized result.

Everything here comes from templates and from the shape of the result (counts, severities, names a
tool reported), never from the text a tool printed. A header value, a token, a page's own words
or evidence are not copied into a card, so the friendly view cannot show a secret.
"""

from pydantic import BaseModel

from app.results.advice import advice_for
from app.results.glossary import terms_in
from app.tools.parsers.schema import Issue, Severity, ToolResult
from app.tools.parsers.summary import summarize

MAX_CARDS = 100
_RANK = {
    s: n
    for n, s in enumerate(
        (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO)
    )
}
_GRADES = {
    Severity.CRITICAL: "F",
    Severity.HIGH: "D",
    Severity.MEDIUM: "C",
    Severity.LOW: "B",
    Severity.INFO: "A",
}
# What the header scorecard checks, and the references that make each one fail.
SCORECARD: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Always uses https (HSTS)", ("headers:no-hsts", "headers:short-hsts")),
    ("Stops content-type guessing", ("headers:no-nosniff",)),
    ("Stops other sites framing it", ("headers:framing",)),
    ("Limits what it tells other sites (Referrer-Policy)", ("headers:referrer",)),
    ("Switches off unused browser features", ("headers:no-permissions-policy",)),
    ("Has a strong Content-Security-Policy", ("headers:no-csp", "csp:")),
    ("Does not reveal software versions", ("headers:leak-",)),
    ("Cookies are protected", ("headers:cookie",)),
    ("Shares data only with trusted sites (CORS)", ("headers:cors-",)),
)


class Card(BaseModel):
    title: str
    severity: Severity
    target: str | None
    what: str
    why: str
    todo: str


class PortRow(BaseModel):
    port: int
    protocol: str
    state: str
    service: str | None
    software: str | None


class HostMap(BaseModel):
    address: str
    state: str
    ports: list[PortRow]


class ScoreItem(BaseModel):
    name: str
    passed: bool


class Visuals(BaseModel):
    port_map: list[HostMap]
    tls_grade: str | None
    scorecard: list[ScoreItem]


class Friendly(BaseModel):
    headline: str
    summary: list[str]
    cards: list[Card]
    hidden_cards: int
    visuals: Visuals
    terms: list[dict[str, str]]


def _headline(result: ToolResult) -> str:
    issues = result.issues
    if not issues:
        return "Nothing to worry about in this result."
    worst = min((i.severity for i in issues), key=_RANK.__getitem__)
    if worst in (Severity.CRITICAL, Severity.HIGH):
        return "This result has a serious problem that needs attention."
    if worst is Severity.MEDIUM:
        return "This result has problems worth fixing."
    return "This result has only minor points or notes."


def _card(issue: Issue) -> Card:
    advice = advice_for(issue.reference, issue.severity)
    return Card(
        title=issue.title,
        severity=issue.severity,
        target=issue.target,
        what=advice.what,
        why=advice.why,
        todo=advice.todo,
    )


def _port_map(result: ToolResult) -> list[HostMap]:
    return [
        HostMap(
            address=host.address,
            state=host.state,
            ports=[
                PortRow(
                    port=s.port,
                    protocol=s.protocol,
                    state=s.state,
                    service=s.name,
                    software=" ".join(p for p in (s.product, s.version) if p) or None,
                )
                for s in host.services
            ],
        )
        for host in result.hosts
    ]


def _tls_grade(result: ToolResult) -> str | None:
    if not result.tls:
        return None
    worst = min((t.severity for t in result.tls), key=_RANK.__getitem__)
    return _GRADES[worst]


def _scorecard(result: ToolResult) -> list[ScoreItem]:
    if result.tool != "b.headers":
        return []
    references = [i.reference or "" for i in result.issues]
    return [
        ScoreItem(
            name=name,
            passed=not any(r.startswith(failing) for r in references for failing in fails),
        )
        for name, fails in SCORECARD
    ]


def friendly(result: ToolResult) -> Friendly:
    """The friendly view of a result: most serious cards first, at most `MAX_CARDS`."""
    ordered = sorted(result.issues, key=lambda issue: _RANK[issue.severity])
    cards = [_card(issue) for issue in ordered[:MAX_CARDS]]
    summary = summarize(result)
    return Friendly(
        headline=_headline(result),
        summary=summary,
        cards=cards,
        hidden_cards=len(ordered) - len(cards),
        visuals=Visuals(
            port_map=_port_map(result), tls_grade=_tls_grade(result), scorecard=_scorecard(result)
        ),
        terms=terms_in(*summary, *(f"{c.title} {c.what} {c.why} {c.todo}" for c in cards)),
    )
