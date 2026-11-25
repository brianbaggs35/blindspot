"""The friendly view: templates only, so it says the same thing every time and never shows a value
a tool printed."""

import json
from pathlib import Path

import pytest

from app.results import friendly as friendly_module
from app.results.advice import ADVICE, advice_for
from app.results.friendly import SCORECARD, friendly
from app.results.glossary import GLOSSARY, terms_in
from app.tools.parsers import PARSERS, parse_output
from app.tools.parsers.schema import (
    Host,
    Issue,
    Service,
    Severity,
    TlsFinding,
    ToolResult,
)

FIXTURES = Path(__file__).parent / "fixtures" / "tools"
FILES = {
    "nmap_xml": "nmap.xml",
    "ffuf_json": "ffuf.json",
    "whatweb_json": "whatweb.json",
    "wafw00f_json": "wafw00f.json",
    "testssl_json": "testssl.json",
    "nikto_csv": "nikto.csv",
    "nuclei_jsonl": "nuclei.jsonl",
    "httpx_jsonl": "httpx.jsonl",
}
TOKEN = "eyJhbGciOiJub25lIn0.eyJzdWIiOiJhIn0.c2lnbmF0dXJl"


def issue(reference: str | None = None, severity: Severity = Severity.LOW, **more: str) -> Issue:
    return Issue(title="Something", severity=severity, reference=reference, **more)  # pyright: ignore[reportArgumentType]


def result(*issues: Issue, tool: str = "t.x", **more: object) -> ToolResult:
    return ToolResult.model_validate(
        {"tool": tool, "parser": "p", "issues": [i.model_dump() for i in issues], **more}
    )


def test_every_parser_has_a_fixture_here() -> None:
    assert set(FILES) == set(PARSERS)


@pytest.mark.parametrize(("parser", "name"), sorted(FILES.items()))
def test_the_friendly_view_of_each_parsers_output_copies_nothing_the_tool_printed(
    parser: str, name: str
) -> None:
    parsed = parse_output(parser, "t.x", (FIXTURES / name).read_bytes())
    view = friendly(parsed)
    dump = json.dumps(view.model_dump(mode="json"))
    assert view.headline
    assert view.summary
    for one in parsed.issues:
        for private in (one.evidence, one.detail):
            if private and len(private) > 12:
                assert private not in dump
    assert all(card.what and card.why and card.todo for card in view.cards)


def test_a_token_in_a_result_never_reaches_the_friendly_view() -> None:
    planted = issue(
        "jwt:alg-none",
        Severity.CRITICAL,
        evidence=TOKEN,
        detail=f"Authorization: Bearer {TOKEN}",
    )
    dump = json.dumps(friendly(result(planted)).model_dump(mode="json"))
    assert TOKEN not in dump
    assert "Bearer" not in dump


def test_advice_is_found_by_reference_then_by_the_longest_prefix_then_by_severity() -> None:
    assert advice_for("headers:no-csp", Severity.LOW) is ADVICE["headers:no-csp"]
    assert advice_for("headers:cors-reflected", Severity.LOW) is ADVICE["headers:cors-reflected"]
    assert advice_for("headers:cors-null", Severity.LOW) is ADVICE["headers:cors-"]
    assert advice_for("headers:leak-server", Severity.LOW) is ADVICE["headers:leak-"]
    assert advice_for("csp:unsafe-eval", Severity.LOW) is ADVICE["csp:"]
    assert advice_for("wellknown:robots-interesting", Severity.LOW) is ADVICE["wellknown:robots"]
    other = advice_for("cve-2021-41773", Severity.CRITICAL)
    assert "critical" in other.what
    assert advice_for(None, Severity.INFO) is not other
    assert len({advice_for(None, s).what for s in Severity}) == len(Severity)


@pytest.mark.parametrize(
    "reference",
    [
        *(f"headers:{n}" for n in ("no-hsts", "short-hsts", "no-nosniff", "framing", "referrer")),
        *("headers:no-permissions-policy", "headers:no-csp", "headers:leak-x-powered-by"),
        *("headers:cookie", "headers:cors-wildcard", "headers:cors-reflected", "headers:cors-null"),
        *(f"csp:{n}" for n in ("report-only", "no-script-src", "unsafe-inline", "bypass-host")),
        *(f"jwt:{n}" for n in ("alg-none", "no-signature", "hmac", "kid", "no-exp", "header-jku")),
        *("wellknown:robots", "wellknown:robots-interesting", "wellknown:txt-missing"),
        *(f"spider:{n}" for n in ("password-http", "mixed-form", "no-csrf-token", "upload")),
        *(f"entropy:{n}" for n in ("repeat", "counter", "weak", "short", "prefix")),
    ],
)
def test_every_finding_the_built_in_tools_make_has_its_own_advice(reference: str) -> None:
    fallbacks = {advice_for(None, s) for s in Severity}
    assert advice_for(reference, Severity.LOW) not in fallbacks


def test_the_headline_follows_the_worst_finding() -> None:
    def headline(severity: Severity | None) -> str:
        return friendly(result(*([issue(severity=severity)] if severity else []))).headline

    heads = {s: headline(s) for s in Severity}
    assert headline(None) == "Nothing to worry about in this result."
    assert heads[Severity.CRITICAL] == heads[Severity.HIGH]
    assert len({heads[Severity.HIGH], heads[Severity.MEDIUM], heads[Severity.LOW]}) == 3
    assert heads[Severity.LOW] == heads[Severity.INFO]


def test_cards_are_most_serious_first_and_cut_at_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(friendly_module, "MAX_CARDS", 2)
    view = friendly(
        result(
            issue(severity=Severity.INFO),
            issue(severity=Severity.CRITICAL),
            issue(severity=Severity.MEDIUM),
        )
    )
    assert [c.severity for c in view.cards] == [Severity.CRITICAL, Severity.MEDIUM]
    assert view.hidden_cards == 1


def test_the_port_map_names_each_open_door() -> None:
    parsed = ToolResult(
        tool="c.nmap",
        parser="nmap_xml",
        hosts=[
            Host(
                address="10.0.0.1",
                state="up",
                services=[
                    Service(port=80, name="http", product="Apache", version="2.4"),
                    Service(port=22, state="closed"),
                ],
            )
        ],
    )
    (host,) = friendly(parsed).visuals.port_map
    assert [(p.port, p.state, p.service, p.software) for p in host.ports] == [
        (80, "open", "http", "Apache 2.4"),
        (22, "closed", None, None),
    ]


@pytest.mark.parametrize(
    ("severity", "grade"),
    [
        (Severity.INFO, "A"),
        (Severity.LOW, "B"),
        (Severity.MEDIUM, "C"),
        (Severity.HIGH, "D"),
        (Severity.CRITICAL, "F"),
    ],
)
def test_the_tls_grade_is_the_worst_finding(severity: Severity, grade: str) -> None:
    parsed = ToolResult(
        tool="p.testssl",
        parser="p",
        tls=[
            TlsFinding(id="a", severity=Severity.INFO, finding="ok"),
            TlsFinding(id="b", severity=severity, finding="x"),
        ],
    )
    assert friendly(parsed).visuals.tls_grade == grade
    assert friendly(result()).visuals.tls_grade is None


def test_the_header_scorecard_fails_what_the_headers_tool_found() -> None:
    clean = friendly(result(tool="b.headers")).visuals.scorecard
    assert [i.name for i in clean] == [name for name, _ in SCORECARD]
    assert all(i.passed for i in clean)
    failing = friendly(
        result(
            issue("headers:no-hsts"),
            issue("csp:unsafe-inline"),
            issue("headers:leak-server"),
            tool="b.headers",
        )
    ).visuals.scorecard
    assert {i.name for i in failing if not i.passed} == {
        "Always uses https (HSTS)",
        "Has a strong Content-Security-Policy",
        "Does not reveal software versions",
    }
    assert friendly(result(issue("headers:no-hsts"))).visuals.scorecard == []


def test_terms_that_appear_are_explained_once() -> None:
    found = terms_in("The Cookie has no HttpOnly flag", "see CORS and cors", "XSS")
    assert [t["term"] for t in found] == ["CORS", "XSS", "cookie", "HttpOnly"]
    assert found[2]["meaning"] == GLOSSARY["cookie"]
    assert terms_in("Nothing to explain here") == []
    assert terms_in("a portal") == []  # a word that only contains a term is not the term
    view = friendly(result(issue("headers:no-csp", Severity.MEDIUM)))
    assert "CSP" in {t["term"] for t in view.terms}
