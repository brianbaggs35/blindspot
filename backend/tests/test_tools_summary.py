"""The plain-words summary every result gets."""

from app.tools.parsers import ToolResult
from app.tools.parsers.schema import (
    Credential,
    Host,
    HttpResponse,
    Issue,
    Service,
    Severity,
    Technology,
    TlsFinding,
)
from app.tools.parsers.summary import summarize


def result(**found: object) -> ToolResult:
    return ToolResult.model_validate({"tool": "t.x", "parser": "p", **found})


def test_a_result_with_nothing_says_so() -> None:
    assert summarize(result()) == ["The tool ran and found nothing to report."]


def test_every_kind_of_finding_gets_a_sentence() -> None:
    found = result(
        issues=[
            Issue(title="a", severity=Severity.HIGH),
            Issue(title="b", severity=Severity.INFO),
            Issue(title="c", severity=Severity.HIGH),
        ],
        hosts=[
            Host(
                address="10.0.0.1",
                services=[Service(port=80), Service(port=22, state="closed")],
            )
        ],
        http=[HttpResponse(url="http://x/")],
        technologies=[Technology(name=f"T{n}") for n in range(10)] + [Technology(name="T1")],
        tls=[
            TlsFinding(id="a", severity=Severity.INFO, finding="ok"),
            TlsFinding(id="b", severity=Severity.HIGH, finding="bad"),
        ],
        credentials=[Credential(target="h", secret="s")],  # pyright: ignore[reportArgumentType]
        truncated=True,
    )
    assert summarize(found) == [
        "3 issues found: 2 high, 1 info.",
        "1 host answered, with 1 open port.",
        "1 web address recorded.",
        "Recognised software: T0, T1, T2, T3, T4, T5, T6, T7 and more.",
        "2 TLS checks run, 1 with a problem.",
        "1 credential found (kept sealed).",
        "The output was long, so only the first part is shown.",
    ]


def test_plurals_and_a_short_list_of_software() -> None:
    found = result(
        hosts=[Host(address="a"), Host(address="b")],
        http=[HttpResponse(url="http://x/"), HttpResponse(url="http://y/")],
        technologies=[Technology(name="Apache")],
        issues=[Issue(title="a", severity=Severity.LOW)],
    )
    assert summarize(found) == [
        "1 issue found: 1 low.",
        "2 hosts answered, with 0 open ports.",
        "2 web addresses recorded.",
        "Recognised software: Apache.",
    ]
