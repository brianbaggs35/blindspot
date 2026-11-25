"""Findings: writing, scoring, the status workflow, evidence that stays sealed, merging, listing,
bulk changes, the trash, results promoted to findings, and the read-only cases."""

import base64
import uuid
from typing import Any, LiteralString

import psycopg
import pytest
from fastapi.testclient import TestClient
from tests.conftest import add_account, another_browser
from tests.pentest_helpers import make

from app.db.events import connection_string
from app.findings import routes as findings_routes
from app.findings import service as findings_service
from app.tools.parsers import PARSERS, ToolResult
from app.tools.parsers.schema import Issue, Severity

V4_CRITICAL = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"
V31_MEDIUM = "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N"
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16).decode()
SECRET_LINE = "Authorization: Bearer abcdefghij0123456789"
GHOST = "00000000-0000-7000-8000-000000000000"


def url(made: dict[str, Any], tail: str = "") -> str:
    return f"/api/pentests/{made['id']}/findings{tail}"


def write(admin: TestClient, made: dict[str, Any], **changes: Any) -> dict[str, Any]:
    document = {"title": "No HSTS", "severity": "low"} | changes
    answer = admin.post(url(made), json=document)
    assert answer.status_code == 201, answer.text
    return answer.json()


def listing(admin: TestClient, made: dict[str, Any], **query: Any) -> dict[str, Any]:
    answer = admin.get(url(made), params=query)
    assert answer.status_code == 200, answer.text
    return answer.json()


def numbers(admin: TestClient, made: dict[str, Any], **query: Any) -> list[int]:
    return [one["number"] for one in listing(admin, made, **query)["items"]]


def evidence(
    admin: TestClient, made: dict[str, Any], one: dict[str, Any], **changes: Any
) -> dict[str, Any]:
    document = {"kind": "note", "title": "Header dump", "body": "Server: nginx"} | changes
    answer = admin.post(url(made, f"/{one['id']}/evidence"), json=document)
    assert answer.status_code == 201, answer.text
    return answer.json()


def stored(database_url: str, sql: LiteralString) -> list[tuple[Any, ...]]:
    with psycopg.connect(connection_string(database_url)) as connection:
        return [tuple(row) for row in connection.execute(sql)]


def audited(database_url: str) -> list[str]:
    rows = stored(database_url, "SELECT action FROM audit_event WHERE action LIKE 'finding.%'")
    return [row[0] for row in rows]


@pytest.fixture
def with_issues(monkeypatch: pytest.MonkeyPatch) -> None:
    """A parser whose output holds three issues, one with proof that looks like a secret."""

    def parse(data: bytes) -> ToolResult:
        return ToolResult(
            tool="x",
            parser="issues",
            issues=[
                Issue(
                    title="Open admin panel",
                    severity=Severity.HIGH,
                    target="https://shop/admin",
                    detail="Reachable without signing in.",
                    reference="https://example.org/a",
                    evidence="password=hunter2hunter2",
                ),
                Issue(title="Old TLS", severity=Severity.MEDIUM, reference="CVE-2024-1"),
                Issue(title="Banner", severity=Severity.INFO),
            ],
        )

    monkeypatch.setitem(PARSERS, "issues", parse)


def promoted(admin: TestClient, made: dict[str, Any], **document: Any) -> Any:
    one = admin.post(
        f"/api/pentests/{made['id']}/results/import",
        json={
            "parser": "issues",
            "content": "x",
            "tool_id": "c.sshcheck",
            "test_id": "WSTG-CONF-06",
        },
    ).json()
    return admin.post(f"/api/pentests/{made['id']}/results/{one['id']}/promote", json=document), one


# -- writing and scoring ----------------------------------------------------------------------


def test_a_finding_is_scored_from_its_vector_and_numbered(
    admin: TestClient, database_url: str
) -> None:
    made = make(admin)
    first = write(admin, made, severity=None, cvss4_vector=V4_CRITICAL, cvss31_vector=V31_MEDIUM)
    assert (first["number"], first["severity"], first["source"], first["status"]) == (
        1,
        "critical",
        "manual",
        "new",
    )
    assert (first["cvss4_score"], first["cvss31_score"]) == ("9.3", "6.1")
    second = write(admin, made, title="Another", severity="high")
    assert second["number"] == 2
    assert [e["kind"] for e in first["timeline"]] == ["created"]
    assert first["allowed_statuses"] == ["confirmed", "false_positive", "accepted_risk", "fixed"]
    assert "finding.create" in audited(database_url)
    assert write(admin, made, severity=None, cvss31_vector=V31_MEDIUM)["severity"] == "medium"


def test_a_finding_needs_a_severity_or_a_vector_and_a_real_vector(admin: TestClient) -> None:
    made = make(admin)
    refused = admin.post(url(made), json={"title": "x"})
    assert (refused.status_code, refused.json()["code"]) == (422, "severity_needed")
    refused = admin.post(url(made), json={"title": "x", "cvss4_vector": "CVSS:4.0/AV:N"})
    assert (refused.status_code, refused.json()["code"]) == (422, "bad_vector")
    refused = admin.post(url(made), json={"title": "x", "severity": "low", "cvss31_vector": "nope"})
    assert (refused.status_code, refused.json()["code"]) == (422, "bad_vector")
    for bad in ({"cwe": ["79"]}, {"owasp": "A11:2021"}, {"references": ["javascript:alert(1)"]}):
        assert (
            admin.post(url(made), json={"title": "x", "severity": "low"} | bad).status_code == 422
        )
    assert (
        admin.post(url(made), json={"title": "x", "severity": "low", "nope": 1}).status_code == 422
    )


def test_a_finding_keeps_what_it_is_given(admin: TestClient) -> None:
    made = make(admin)
    one = write(
        admin,
        made,
        description="Strict-Transport-Security is missing.",
        target="https://shop.example.com/",
        test_ids=["WSTG-CONF-07", "WSTG-CONF-07", "WSTG-CRYP-03"],
        cwe=["CWE-319", "CWE-319"],
        owasp="A02:2021",
        confidence="certain",
        remediation="Send the header.",
        references=["https://owasp.org/www-project-secure-headers/"],
    )
    assert one["test_ids"] == ["WSTG-CONF-07", "WSTG-CRYP-03"]
    assert (one["cwe"], one["owasp"], one["category"]) == (["CWE-319"], "A02:2021", "CONF")
    assert (one["confidence"], one["remediation"]) == ("certain", "Send the header.")
    assert admin.get(url(made, f"/{one['id']}")).json() == one


def test_changing_a_finding_rates_it_again_unless_a_severity_is_sent(
    admin: TestClient, database_url: str
) -> None:
    made = make(admin)
    one = write(admin, made, severity="low")
    base = url(made, f"/{one['id']}")
    rated = admin.patch(base, json={"cvss4_vector": V4_CRITICAL}).json()
    assert (rated["severity"], rated["cvss4_score"]) == ("critical", "9.3")
    kept = admin.patch(base, json={"cvss31_vector": V31_MEDIUM, "severity": "high"}).json()
    assert (kept["severity"], kept["cvss31_score"]) == ("high", "6.1")
    cleared = admin.patch(base, json={"cvss4_vector": None, "cvss31_vector": None}).json()
    assert (cleared["cvss4_vector"], cleared["cvss4_score"], cleared["severity"]) == (
        None,
        None,
        "high",
    )
    same = admin.patch(base, json={"cvss31_vector": V31_MEDIUM}).json()
    assert same["cvss31_vector"] == V31_MEDIUM
    assert admin.patch(base, json={"cvss31_vector": V31_MEDIUM}).json()["cvss31_score"] == "6.1"
    done = admin.patch(
        base,
        json={
            "title": "HSTS missing",
            "description": "d",
            "target": "t",
            "test_ids": ["WSTG-CONF-07"],
            "cwe": ["CWE-1"],
            "owasp": "A05:2021",
            "confidence": "tentative",
            "remediation": "r",
            "references": ["https://example.org/"],
        },
    ).json()
    assert (done["title"], done["owasp"], done["confidence"]) == (
        "HSTS missing",
        "A05:2021",
        "tentative",
    )
    assert admin.patch(base, json={"owasp": None}).json()["owasp"] is None
    before = len(done["timeline"])
    assert (
        len(admin.patch(base, json={"title": "HSTS missing"}).json()["timeline"]) == before - 0 + 1
    )
    assert "finding.update" in audited(database_url)
    refused = admin.patch(base, json={"cvss4_vector": "nope"})
    assert (refused.status_code, refused.json()["code"]) == (422, "bad_vector")


def test_the_scores_come_from_the_server_not_the_request(admin: TestClient) -> None:
    made = make(admin)
    refused = admin.post(url(made), json={"title": "x", "severity": "low", "cvss4_score": 1.0})
    assert refused.status_code == 422
    answer = admin.get("/api/cvss/score", params={"vector": V4_CRITICAL})
    assert answer.json() == {
        "vector": V4_CRITICAL,
        "version": "4.0",
        "score": "9.3",
        "severity": "critical",
    }
    answer = admin.get("/api/cvss/score", params={"vector": V31_MEDIUM})
    assert (answer.json()["version"], answer.json()["score"]) == ("3.1", "6.1")
    refused = admin.get("/api/cvss/score", params={"vector": "CVSS:3.1/AV:N"})
    assert (refused.status_code, refused.json()["code"]) == (422, "bad_vector")
    reference = admin.get("/api/findings/reference").json()
    assert reference["owasp"]["A03:2021"] == "Injection"
    assert "confirmed" in reference["transitions"]["new"]


# -- the status workflow, verification and the timeline -----------------------------------------


def test_a_finding_moves_along_the_workflow_and_the_timeline_says_so(
    admin: TestClient, database_url: str
) -> None:
    made = make(admin)
    one = write(admin, made)
    base = url(made, f"/{one['id']}")
    moved = admin.post(base + "/status", json={"status": "confirmed", "note": "Seen again"}).json()
    assert moved["status"] == "confirmed"
    assert moved["timeline"][0]["data"] == {
        "before": "new",
        "after": "confirmed",
        "note": "Seen again",
    }
    assert moved["timeline"][0]["actor"] == "admin"
    for status, code in (("confirmed", "same_status"), ("new", "bad_transition")):
        refused = admin.post(base + "/status", json={"status": status})
        assert (refused.status_code, refused.json()["code"]) == (409, code)
    assert admin.post(base + "/status", json={"status": "fixed"}).json()["status"] == "fixed"
    assert admin.post(base + "/status", json={"status": "bogus"}).status_code == 422
    assert "finding.status" in audited(database_url)


def test_a_person_confirms_or_doubts_a_finding(admin: TestClient) -> None:
    made = make(admin)
    one = write(admin, made)
    base = url(made, f"/{one['id']}")
    doubted = admin.post(base + "/verification", json={"outcome": "unconfirmed"}).json()
    assert (doubted["verification"], doubted["verified_by"], doubted["status"]) == (
        "unconfirmed",
        "manual",
        "new",
    )
    assert doubted["verified_at"]
    sure = admin.post(
        base + "/verification", json={"outcome": "confirmed", "note": "Replayed"}
    ).json()
    assert (sure["verification"], sure["status"]) == ("confirmed", "confirmed")
    assert [e["kind"] for e in sure["timeline"][:2]] == ["status", "verified"]
    again = admin.post(base + "/verification", json={"outcome": "confirmed"}).json()
    assert again["status"] == "confirmed"


def test_a_retest_needs_a_test_and_a_status_that_allows_it(admin: TestClient) -> None:
    made = make(admin)
    bare = write(admin, made)
    refused = admin.post(url(made, f"/{bare['id']}/retest"))
    assert (refused.status_code, refused.json()["code"]) == (409, "no_test")
    one = write(admin, made, title="Tested", test_ids=["WSTG-CONF-07"])
    refused = admin.post(url(made, f"/{one['id']}/retest"))
    assert (refused.status_code, refused.json()["code"]) == (409, "bad_transition")
    admin.post(url(made, f"/{one['id']}/status"), json={"status": "fixed"})
    asked = admin.post(url(made, f"/{one['id']}/retest")).json()
    assert asked["status"] == "retest_needed"
    assert asked["timeline"][0]["kind"] == "retest_requested"
    assert asked["timeline"][0]["data"]["tests"] == ["WSTG-CONF-07"]


def test_people_comment_on_a_finding(admin: TestClient) -> None:
    made = make(admin)
    one = write(admin, made)
    answer = admin.post(url(made, f"/{one['id']}/comments"), json={"body": "  Fix by Friday  "})
    assert answer.status_code == 201
    assert answer.json()["timeline"][0]["data"] == {"body": "Fix by Friday"}
    assert admin.post(url(made, f"/{one['id']}/comments"), json={"body": " "}).status_code == 422


# -- evidence ----------------------------------------------------------------------------------


def test_evidence_that_looks_like_a_secret_is_sealed_and_hidden_until_revealed(
    admin: TestClient, database_url: str
) -> None:
    made = make(admin)
    one = write(admin, made)
    plain = evidence(admin, made, one)["evidence"][0]
    assert (plain["body"], plain["sealed"]) == ("Server: nginx", False)
    sealed = evidence(admin, made, one, title="Request", kind="request_response", body=SECRET_LINE)
    shown = sealed["evidence"][1]
    assert (shown["body"], shown["sealed"]) == ("••••••••", True)
    assert "abcdefghij0123456789" not in admin.get(url(made, f"/{one['id']}")).text
    assert "abcdefghij0123456789" not in admin.get(url(made)).text
    assert stored(database_url, "SELECT body FROM finding_evidence WHERE sealed")[0][0].startswith(
        "v1:"
    )
    revealed = admin.post(url(made, f"/{one['id']}/evidence/{shown['id']}/reveal"))
    assert revealed.json() == {"body": SECRET_LINE}
    assert "finding.evidence_reveal" in audited(database_url)
    audit_text = str(stored(database_url, "SELECT detail FROM audit_event"))
    assert "abcdefghij0123456789" not in audit_text


def test_unsealed_evidence_is_redacted_when_shown_and_can_be_sealed_by_hand(
    admin: TestClient,
) -> None:
    made = make(admin)
    one = write(admin, made)
    loud = evidence(admin, made, one, body=SECRET_LINE, sealed=False)["evidence"][0]
    assert loud["sealed"] is False
    assert "abcdefghij0123456789" not in (loud["body"] or "")
    handled = admin.patch(
        url(made, f"/{one['id']}/evidence/{loud['id']}"), json={"title": "Renamed", "sealed": True}
    ).json()["evidence"][0]
    assert (handled["title"], handled["body"], handled["sealed"]) == ("Renamed", "••••••••", True)
    assert admin.patch(url(made, f"/{one['id']}/evidence/{loud['id']}"), json={}).status_code == 200
    quiet = evidence(admin, made, one, title="Plain", body="ok", sealed=True)["evidence"][1]
    assert quiet["body"] == "••••••••"


def test_a_result_of_the_pentest_is_evidence_and_one_of_another_is_not(
    admin: TestClient, with_issues: None
) -> None:
    made, other = make(admin), make(admin)
    one = write(admin, made)
    result = admin.post(
        f"/api/pentests/{made['id']}/results/import",
        json={"parser": "issues", "content": "x", "tool_id": "c.sshcheck", "title": "Scan"},
    ).json()
    added = evidence(
        admin, made, one, kind="result", title="The scan", body=None, result_id=result["id"]
    )
    assert (added["evidence"][0]["result_title"], added["evidence"][0]["body"]) == ("Scan", None)
    foreign = admin.post(
        f"/api/pentests/{other['id']}/results",
        json={"title": "Elsewhere"},
    ).json()
    for document in (
        {"kind": "result", "title": "x"},
        {"kind": "result", "title": "x", "result_id": foreign["id"]},
    ):
        refused = admin.post(url(made, f"/{one['id']}/evidence"), json=document)
        assert (refused.status_code, refused.json()["code"]) == (422, "result_not_found")


def test_text_evidence_needs_text(admin: TestClient) -> None:
    made = make(admin)
    one = write(admin, made)
    for document in (
        {"kind": "note", "title": "x"},
        {"kind": "note", "title": "x", "body": "a" * 100_001},
    ):
        refused = admin.post(url(made, f"/{one['id']}/evidence"), json=document)
        assert (refused.status_code, refused.json()["code"]) == (422, "evidence_needed")
    assert (
        admin.post(
            url(made, f"/{one['id']}/evidence"), json={"kind": "x", "title": "y"}
        ).status_code
        == 422
    )


def test_a_screenshot_is_checked_and_served_unless_it_is_sealed(admin: TestClient) -> None:
    made = make(admin)
    one = write(admin, made)
    shot = {"kind": "screenshot", "title": "The panel", "body": PNG, "mime": "image/png"}
    added = evidence(admin, made, one, **shot)["evidence"][0]
    assert (added["body"], added["mime"], added["sealed"]) == (None, "image/png", False)
    image = admin.get(url(made, f"/{one['id']}/evidence/{added['id']}/image"))
    assert (image.status_code, image.headers["content-type"], image.content[:4]) == (
        200,
        "image/png",
        b"\x89PNG",
    )
    sealed = evidence(admin, made, one, **shot, sealed=True)["evidence"][1]
    refused = admin.get(url(made, f"/{one['id']}/evidence/{sealed['id']}/image"))
    assert (refused.status_code, refused.json()["code"]) == (403, "sealed")
    revealed = admin.post(url(made, f"/{one['id']}/evidence/{sealed['id']}/reveal")).json()
    assert revealed["body"] == PNG
    text = evidence(admin, made, one)["evidence"][2]
    refused = admin.get(url(made, f"/{one['id']}/evidence/{text['id']}/image"))
    assert (refused.status_code, refused.json()["code"]) == (404, "no_image")


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"body": None}, "image_needed"),
        ({"mime": None}, "image_needed"),
        ({"body": "not base64!!"}, "bad_image"),
        ({"body": base64.b64encode(b"GIF89a....").decode()}, "bad_image"),
        ({"mime": "image/webp"}, "bad_image"),
        (
            {
                "body": base64.b64encode(b"RIFF" + b"\x00" * 4 + b"WAVE").decode(),
                "mime": "image/webp",
            },
            "bad_image",
        ),
    ],
)
def test_a_screenshot_that_is_not_an_image_is_refused(
    admin: TestClient, changes: dict[str, Any], code: str
) -> None:
    made = make(admin)
    one = write(admin, made)
    document = {"kind": "screenshot", "title": "x", "body": PNG, "mime": "image/png"} | changes
    refused = admin.post(url(made, f"/{one['id']}/evidence"), json=document)
    assert (refused.status_code, refused.json()["code"]) == (422, code)


def test_a_screenshot_may_be_webp_and_is_not_too_large(
    admin: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = make(admin)
    one = write(admin, made)
    webp = base64.b64encode(b"RIFF\x00\x00\x00\x00WEBPVP8 ").decode()
    document = {"kind": "screenshot", "title": "x", "body": webp, "mime": "image/webp"}
    assert admin.post(url(made, f"/{one['id']}/evidence"), json=document).status_code == 201
    monkeypatch.setattr(findings_service, "MAX_IMAGE", 8)
    refused = admin.post(url(made, f"/{one['id']}/evidence"), json=document | {"body": PNG})
    assert (refused.status_code, refused.json()["code"]) == (422, "image_too_large")


def test_evidence_can_be_removed_and_a_finding_keeps_a_bounded_amount(
    admin: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(findings_service, "MAX_EVIDENCE_PER_FINDING", 1)
    made = make(admin)
    one = write(admin, made)
    kept = evidence(admin, made, one)["evidence"][0]
    refused = admin.post(
        url(made, f"/{one['id']}/evidence"), json={"kind": "note", "title": "x", "body": "y"}
    )
    assert (refused.status_code, refused.json()["code"]) == (409, "too_much_evidence")
    gone = admin.delete(url(made, f"/{one['id']}/evidence/{kept['id']}"))
    assert gone.status_code == 204
    after = admin.get(url(made, f"/{one['id']}")).json()
    assert (after["evidence"], after["timeline"][0]["kind"]) == ([], "evidence_removed")
    assert admin.delete(url(made, f"/{one['id']}/evidence/{kept['id']}")).status_code == 404


def test_evidence_belongs_to_its_finding_and_text_has_nothing_to_reveal_for_a_result(
    admin: TestClient, with_issues: None
) -> None:
    made = make(admin)
    one, two = write(admin, made), write(admin, made, title="Two")
    kept = evidence(admin, made, one)["evidence"][0]
    for method, tail in (("patch", ""), ("delete", ""), ("post", "/reveal"), ("get", "/image")):
        answer = admin.request(
            method, url(made, f"/{two['id']}/evidence/{kept['id']}{tail}"), json={}
        )
        assert (answer.status_code, answer.json()["code"]) == (404, "evidence_not_found"), tail
    result = admin.post(
        f"/api/pentests/{made['id']}/results/import",
        json={"parser": "issues", "content": "x", "tool_id": "c.sshcheck"},
    ).json()
    linked = evidence(admin, made, one, kind="result", title="r", body=None, result_id=result["id"])
    refused = admin.post(url(made, f"/{one['id']}/evidence/{linked['evidence'][1]['id']}/reveal"))
    assert (refused.status_code, refused.json()["code"]) == (404, "nothing_to_reveal")


# -- duplicates and merging ---------------------------------------------------------------------


def test_findings_that_look_alike_are_pointed_out_and_can_be_merged(admin: TestClient) -> None:
    made = make(admin)
    keep = write(
        admin,
        made,
        title="Missing HSTS",
        severity="low",
        target="https://shop/",
        test_ids=["WSTG-CONF-07"],
        cwe=["CWE-319"],
        references=["https://a.example/"],
    )
    twin = write(
        admin,
        made,
        title="missing hsts",
        severity="high",
        test_ids=["WSTG-CRYP-03"],
        cwe=["CWE-2"],
        references=["https://b.example/"],
    )
    cousin = write(
        admin, made, title="Strict transport", target="HTTPS://shop/", test_ids=["WSTG-CONF-07"]
    )
    write(admin, made, title="Unrelated", target="https://other/", test_ids=["WSTG-CONF-07"])
    evidence(admin, made, twin, title="Twin proof")
    lower = write(admin, made, title="Lower", severity="info")
    found = admin.get(url(made, f"/{keep['id']}")).json()["duplicates"]
    assert [(d["number"], d["reason"]) for d in found] == [
        (2, "The same title"),
        (3, "The same target and test"),
    ]
    merged = admin.post(url(made, f"/{twin['id']}/merge"), json={"into": keep["id"]})
    assert merged.status_code == 200
    kept = merged.json()
    assert kept["id"] == keep["id"]
    assert (kept["severity"], kept["test_ids"], kept["cwe"]) == (
        "high",
        ["WSTG-CONF-07", "WSTG-CRYP-03"],
        ["CWE-319", "CWE-2"],
    )
    assert [e["title"] for e in kept["evidence"]] == ["Twin proof"]
    assert kept["timeline"][0]["kind"] == "merged_from"
    gone = admin.get(url(made, f"/{twin['id']}")).json()
    assert (gone["deleted"], gone["merged_into"], gone["timeline"][0]["kind"]) == (
        True,
        keep["id"],
        "merged_into",
    )
    assert gone["duplicates"] == []
    assert numbers(admin, made, view="trash") == [2]
    refused = admin.post(url(made, f"/{twin['id']}/restore"))
    assert (refused.status_code, refused.json()["code"]) == (409, "merged")
    assert [d["number"] for d in admin.get(url(made, f"/{cousin['id']}")).json()["duplicates"]] == [
        1
    ]
    smaller = admin.post(url(made, f"/{lower['id']}/merge"), json={"into": keep["id"]}).json()
    assert smaller["severity"] == "high"


def test_a_merge_needs_two_findings_of_the_pentest_that_are_not_in_the_trash(
    admin: TestClient,
) -> None:
    made, other = make(admin), make(admin)
    one, two = write(admin, made), write(admin, made, title="Two")
    foreign = write(admin, other)
    for into in (one["id"], foreign["id"]):
        refused = admin.post(url(made, f"/{one['id']}/merge"), json={"into": into})
        assert (refused.status_code, refused.json()["code"]) in {
            (422, "bad_merge"),
            (404, "finding_not_found"),
        }
    admin.delete(url(made, f"/{two['id']}"))
    for source, into in ((one, two), (two, one)):
        refused = admin.post(url(made, f"/{source['id']}/merge"), json={"into": into["id"]})
        assert (refused.status_code, refused.json()["code"]) == (409, "in_trash")
    assert admin.post(url(made, f"/{one['id']}/merge"), json={"into": GHOST}).status_code == 404


# -- the list ---------------------------------------------------------------------------------


@pytest.fixture
def several(admin: TestClient) -> dict[str, Any]:
    made = make(admin)
    write(
        admin,
        made,
        title="Alpha",
        severity="low",
        target="https://a/",
        test_ids=["WSTG-CONF-07"],
        cwe=["CWE-319"],
        description="Plain HTTP",
    )
    write(
        admin,
        made,
        title="Bravo",
        severity="critical",
        target="https://b/",
        test_ids=["WSTG-ATHN-01"],
        cvss4_vector=V4_CRITICAL,
    )
    write(
        admin,
        made,
        title="Charlie",
        severity="medium",
        target="https://a/",
        test_ids=["WSTG-CONF-07"],
        cvss31_vector=V31_MEDIUM,
    )
    write(admin, made, title="Delta", severity="medium")
    return made


def test_findings_are_filtered_sorted_and_counted(
    admin: TestClient, several: dict[str, Any]
) -> None:
    made = several
    assert numbers(admin, made) == [2, 4, 3, 1]  # severity, then newest
    assert numbers(admin, made, sort="severity", order="asc") == [1, 4, 3, 2]
    assert numbers(admin, made, sort="number", order="asc") == [1, 2, 3, 4]
    assert numbers(admin, made, sort="title", order="asc") == [1, 2, 3, 4]
    assert numbers(admin, made, sort="cvss") == [2, 3, 4, 1]
    assert numbers(admin, made, sort="updated", order="asc")[0] == 1
    assert numbers(admin, made, severity=["medium", "low"]) == [4, 3, 1]
    admin.post(
        url(made, f"/{listing(admin, made)['items'][0]['id']}/status"), json={"status": "fixed"}
    )
    assert numbers(admin, made, status=["fixed"]) == [2]
    assert sorted(numbers(admin, made, status=["new", "fixed"])) == [1, 2, 3, 4]
    assert numbers(admin, made, test="WSTG-CONF-07", order="asc", sort="number") == [1, 3]
    assert numbers(admin, made, target="HTTPS://a", sort="number", order="asc") == [1, 3]
    for query in ("alpha", "plain http", "cwe-319", "F-3", "wstg-athn", "3"):
        assert numbers(admin, made, q=query, sort="number", order="asc")[0] in {1, 2, 3}, query
    assert numbers(admin, made, q="nothing like it") == []
    page = listing(admin, made, limit=2, offset=1)
    assert (page["total"], len(page["items"])) == (4, 2)
    assert page["severities"] == {"low": 1, "critical": 1, "medium": 2}
    assert page["statuses"] == {"new": 3, "fixed": 1}
    first = page["items"][0]
    assert {"number", "title", "category", "evidence_count", "cvss4_score"} <= set(first)
    assert admin.get(url(made), params={"status": "bogus"}).status_code == 422


def test_findings_are_grouped_by_category_target_or_severity(
    admin: TestClient, several: dict[str, Any]
) -> None:
    made = several
    groups = {
        by: {g["key"]: g["count"] for g in listing(admin, made, group_by=by)["groups"]}
        for by in ("category", "target", "severity")
    }
    assert groups["category"] == {"ATHN": 1, "CONF": 2, "Other": 1}
    assert groups["target"] == {"https://a/": 2, "https://b/": 1, "No target": 1}
    assert groups["severity"] == {"critical": 1, "low": 1, "medium": 2}
    assert listing(admin, made)["groups"] == []


def test_findings_get_the_status_and_the_trash_in_bulk(
    admin: TestClient, several: dict[str, Any]
) -> None:
    made = several
    ids = {one["number"]: one["id"] for one in listing(admin, made)["items"]}
    bulk = url(made, "/bulk")
    moved = admin.post(
        bulk, json={"ids": [ids[1], ids[2], ids[3]], "action": "set_status", "status": "confirmed"}
    )
    assert moved.json() == {"changed": 3, "skipped": 0}
    again = admin.post(
        bulk, json={"ids": [ids[1], ids[4]], "action": "set_status", "status": "fixed"}
    )
    assert again.json() == {"changed": 2, "skipped": 0}
    stuck = admin.post(
        bulk, json={"ids": [ids[1], ids[2]], "action": "set_status", "status": "new"}
    )
    assert stuck.json() == {"changed": 0, "skipped": 2}
    refused = admin.post(bulk, json={"ids": [ids[1]], "action": "set_status"})
    assert (refused.status_code, refused.json()["code"]) == (422, "status_needed")
    deleted = admin.post(bulk, json={"ids": [ids[1], ids[2], GHOST], "action": "delete"})
    assert deleted.json() == {"changed": 2, "skipped": 1}
    assert numbers(admin, made, view="trash", sort="number", order="asc") == [1, 2]
    skipped = admin.post(
        bulk, json={"ids": [ids[1]], "action": "set_status", "status": "confirmed"}
    )
    assert skipped.json()["changed"] == 0
    restored = admin.post(bulk, json={"ids": [ids[1], ids[2], ids[3]], "action": "restore"})
    assert restored.json() == {"changed": 2, "skipped": 1}
    assert admin.post(bulk, json={"ids": [], "action": "delete"}).status_code == 422


def test_a_finding_goes_to_the_trash_and_comes_back(admin: TestClient, database_url: str) -> None:
    made = make(admin)
    one = write(admin, made)
    base = url(made, f"/{one['id']}")
    assert admin.delete(base).status_code == 204
    trashed = admin.get(base).json()
    assert trashed["deleted"] is True
    for attempt in (
        admin.delete(base),
        admin.patch(base, json={"title": "x"}),
        admin.post(base + "/status", json={"status": "confirmed"}),
        admin.post(base + "/verification", json={"outcome": "confirmed"}),
        admin.post(base + "/retest"),
        admin.post(base + "/comments", json={"body": "x"}),
        admin.post(base + "/evidence", json={"kind": "note", "title": "x", "body": "y"}),
    ):
        assert (attempt.status_code, attempt.json()["code"]) == (409, "in_trash")
    assert numbers(admin, made) == []
    back = admin.post(base + "/restore")
    assert back.json()["deleted"] is False
    twice = admin.post(base + "/restore")
    assert (twice.status_code, twice.json()["code"]) == (409, "not_in_trash")
    assert {"finding.delete", "finding.restore"} <= set(audited(database_url))
    assert [e["kind"] for e in back.json()["timeline"][:2]] == ["restored", "deleted"]


# -- export and import --------------------------------------------------------------------------


def test_an_export_never_carries_sealed_evidence_or_a_secret(admin: TestClient) -> None:
    made = make(admin)
    one = write(
        admin,
        made,
        title="=cmd|' /C calc'!A0",
        description="line one\nline two",
        target="https://shop/",
        test_ids=["WSTG-CONF-07"],
        cwe=["CWE-319"],
    )
    evidence(admin, made, one, kind="request_response", title="Request", body=SECRET_LINE)
    evidence(admin, made, one, title="Loose", body=SECRET_LINE, sealed=False)
    evidence(admin, made, one, kind="screenshot", title="Shot", body=PNG, mime="image/png")
    for format_ in ("json", "csv", "sarif"):
        answer = admin.get(url(made, "/export"), params={"format": format_})
        assert answer.status_code == 200
        assert "abcdefghij0123456789" not in answer.text, format_
        assert answer.headers["content-disposition"].startswith("attachment; filename=")
        assert answer.headers["x-content-type-options"] == "nosniff"
    exported = admin.get(url(made, "/export")).json()
    item = exported["findings"][0]
    assert exported["blindspot_findings"] == 1
    first = item["evidence"][0]
    assert (first["kind"], first["sealed"], first["body"]) == (
        "request_response",
        True,
        "••••••••",
    )
    assert item["evidence"][2]["body"] is None
    csv_text = admin.get(url(made, "/export"), params={"format": "csv"}).text
    assert "'=cmd" in csv_text
    assert csv_text.splitlines()[0].startswith("number,title,severity")
    sarif = admin.get(url(made, "/export"), params={"format": "sarif"}).json()
    assert sarif["version"] == "2.1.0"
    result = sarif["runs"][0]["results"][0]
    assert (result["ruleId"], result["level"]) == ("CWE-319", "note")
    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "https://shop/"
    assert admin.get(url(made, "/export"), params={"format": "pdf"}).status_code == 422


def test_an_export_of_findings_without_a_cwe_or_target_still_makes_a_rule(
    admin: TestClient,
) -> None:
    made = make(admin)
    write(admin, made, title="Odd title!", severity="critical")
    sarif = admin.get(url(made, "/export"), params={"format": "sarif"}).json()
    result = sarif["runs"][0]["results"][0]
    assert result["ruleId"] == "BLINDSPOT-odd-title-"
    assert (result["level"], "locations" in result) == ("error", False)
    assert admin.get(url(made, "/export"), params={"view": "trash"}).json()["findings"] == []


def test_an_export_can_be_imported_again_without_doubling_anything(admin: TestClient) -> None:
    made, fresh = make(admin), make(admin)
    write(admin, made, title="One", target="https://a/", cvss4_vector=V4_CRITICAL, cwe=["CWE-1"])
    two = write(admin, made, title="Two", severity="medium")
    admin.post(url(made, f"/{two['id']}/status"), json={"status": "false_positive"})
    exported = admin.get(url(made, "/export")).text
    answer = admin.post(url(fresh, "/import"), json={"format": "json", "content": exported})
    assert (answer.status_code, answer.json()) == (201, {"created": 2, "skipped": 0})
    again = admin.post(url(fresh, "/import"), json={"format": "json", "content": exported})
    assert again.json() == {"created": 0, "skipped": 2}
    by_title = {one["title"]: one for one in listing(admin, fresh)["items"]}
    assert (by_title["One"]["source"], by_title["One"]["cvss4_score"]) == ("import", "9.3")
    assert by_title["Two"]["status"] == "false_positive"


def test_a_list_of_findings_and_a_file_with_unusable_ones_can_be_imported(
    admin: TestClient,
) -> None:
    made = make(admin)
    content = (
        '[{"title": "Fine", "severity": "low"}, {"severity": "low"}, {"title": "No rating"},'
        ' {"title": "Bad vector", "severity": "low", "cvss4_vector": "nope"}]'
    )
    answer = admin.post(url(made, "/import"), json={"format": "json", "content": content})
    assert answer.json() == {"created": 1, "skipped": 3}
    for content in ("not json", "42", '{"findings": 3}', "[1, 2]"):
        refused = admin.post(url(made, "/import"), json={"format": "json", "content": content})
        if content == "[1, 2]":
            assert refused.status_code == 422
        else:
            assert (refused.status_code, refused.json()["code"]) == (422, "unreadable_import"), (
                content
            )


def test_too_many_findings_in_one_file_are_refused(
    admin: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.findings import exchange  # noqa: PLC0415

    monkeypatch.setattr(exchange, "MAX_IMPORTED", 1)
    made = make(admin)
    content = '[{"title": "a", "severity": "low"}, {"title": "b", "severity": "low"}]'
    refused = admin.post(url(made, "/import"), json={"format": "json", "content": content})
    assert (refused.status_code, refused.json()["code"]) == (422, "too_many_to_import")


SARIF = """{
  "version": "2.1.0",
  "runs": [{
    "tool": {"driver": {"name": "scanner", "rules": [
      {"id": "R1", "helpUri": "https://rules.example/r1",
       "properties": {"tags": ["external/cwe/cwe-79"], "security-severity": "9.1"}},
      {"id": "R2", "properties": {"security-severity": "7.5"}},
      {"id": "R3", "properties": {"security-severity": "5"}},
      {"id": "R4", "properties": {"security-severity": "2"}},
      {"id": "R5", "properties": {"security-severity": "0"}},
      {"id": "R6", "properties": {"security-severity": "high-ish"}},
      {"id": "CWE-89"}
    ]}},
    "results": [
      {"ruleId": "R1", "level": "error", "message": {"text": "Reflected XSS\\nIn the search box"},
       "locations": [{"physicalLocation": {"artifactLocation": {"uri": "https://shop/search"}}}]},
      {"ruleId": "R2", "message": {"text": "Seven five"}},
      {"ruleId": "R3", "message": {"text": "Five"}},
      {"ruleId": "R4", "message": {"text": "Two"}},
      {"ruleId": "R5", "message": {"text": "Zero"}},
      {"ruleId": "R6", "level": "note", "message": {"text": "Not a number"}},
      {"ruleId": "CWE-89", "level": "none", "message": {"text": "Named after a CWE"},
       "properties": {"severity": "critical"}},
      {"ruleId": "R7", "level": "warning", "message": {"text": ""}}
    ]
  }]
}"""


def test_a_sarif_report_becomes_findings(admin: TestClient) -> None:
    made = make(admin)
    answer = admin.post(url(made, "/import"), json={"format": "sarif", "content": SARIF})
    assert answer.json() == {"created": 8, "skipped": 0}
    found = {one["title"]: one for one in listing(admin, made, limit=50)["items"]}
    assert (found["Reflected XSS"]["severity"], found["Reflected XSS"]["target"]) == (
        "critical",
        "https://shop/search",
    )
    levels = {
        t: found[t]["severity"]
        for t in ("Seven five", "Five", "Two", "Zero", "Not a number", "Named after a CWE", "R7")
    }
    assert levels == {
        "Seven five": "high",
        "Five": "medium",
        "Two": "low",
        "Zero": "info",
        "Not a number": "low",
        "Named after a CWE": "critical",
        "R7": "medium",
    }
    detail = admin.get(url(made, f"/{found['Reflected XSS']['id']}")).json()
    assert (detail["cwe"], detail["references"]) == (["CWE-79"], ["https://rules.example/r1"])
    assert admin.get(url(made, f"/{found['Named after a CWE']['id']}")).json()["cwe"] == ["CWE-89"]
    refused = admin.post(url(made, "/import"), json={"format": "sarif", "content": '{"runs": 1}'})
    assert (refused.status_code, refused.json()["code"]) == (422, "unreadable_import")


# -- results become findings ---------------------------------------------------------------------


def test_the_issues_of_a_result_become_findings_with_the_result_as_evidence(
    admin: TestClient, with_issues: None, database_url: str
) -> None:
    made = make(admin)
    answer, result = promoted(admin, made)
    assert answer.status_code == 201, answer.text
    items = answer.json()
    assert [(i["title"], i["severity"], i["source"], i["evidence_count"]) for i in items] == [
        ("Open admin panel", "high", "result", 2),
        ("Old TLS", "medium", "result", 1),
        ("Banner", "info", "result", 1),
    ]
    detail = admin.get(url(made, f"/{items[0]['id']}")).json()
    assert (detail["target"], detail["test_ids"], detail["result_id"]) == (
        "https://shop/admin",
        ["WSTG-CONF-06"],
        result["id"],
    )
    assert detail["references"] == ["https://example.org/a"]
    assert [(e["kind"], e["sealed"]) for e in detail["evidence"]] == [
        ("result", False),
        ("note", True),
    ]
    assert "hunter2hunter2" not in admin.get(url(made, f"/{items[0]['id']}")).text
    assert admin.get(url(made, f"/{items[1]['id']}")).json()["references"] == []
    again = admin.post(f"/api/pentests/{made['id']}/results/{result['id']}/promote", json={})
    assert again.json() == []
    assert "finding.promote" in audited(database_url)


def test_only_the_chosen_issues_are_promoted_and_a_result_must_have_them(
    admin: TestClient, with_issues: None
) -> None:
    made = make(admin)
    answer, result = promoted(admin, made, issues=[1, 1, 99])
    assert [i["title"] for i in answer.json()] == ["Old TLS"]
    path = f"/api/pentests/{made['id']}/results/{result['id']}/promote"
    refused = admin.post(path, json={"issues": [50]})
    assert (refused.status_code, refused.json()["code"]) == (422, "no_issues")
    note = admin.post(f"/api/pentests/{made['id']}/results", json={"title": "Note"}).json()
    refused = admin.post(f"/api/pentests/{made['id']}/results/{note['id']}/promote", json={})
    assert (refused.status_code, refused.json()["code"]) == (422, "no_issues")
    other = make(admin)
    refused = admin.post(f"/api/pentests/{other['id']}/results/{result['id']}/promote", json={})
    assert (refused.status_code, refused.json()["code"]) == (404, "result_not_found")
    assert (
        admin.post(f"/api/pentests/{made['id']}/results/{GHOST}/promote", json={}).status_code
        == 404
    )


# -- who may do what ------------------------------------------------------------------------------


def test_a_viewer_reads_and_exports_but_changes_nothing(admin: TestClient) -> None:
    made = make(admin)
    one = write(admin, made)
    shot = evidence(admin, made, one, kind="screenshot", title="s", body=PNG, mime="image/png")
    add_account(admin, "vic")
    viewer = another_browser(admin, "vic")
    base = url(made, f"/{one['id']}")
    for path in (
        "",
        f"/{one['id']}",
        "/export",
        f"/{one['id']}/evidence/{shot['evidence'][0]['id']}/image",
    ):
        assert viewer.get(url(made, path)).status_code == 200, path
    assert viewer.get("/api/cvss/score", params={"vector": V4_CRITICAL}).status_code == 200
    for attempt in (
        viewer.post(url(made), json={"title": "x", "severity": "low"}),
        viewer.patch(base, json={"title": "x"}),
        viewer.delete(base),
        viewer.post(base + "/status", json={"status": "fixed"}),
        viewer.post(base + "/evidence/" + shot["evidence"][0]["id"] + "/reveal"),
        viewer.post(url(made, "/bulk"), json={"ids": [one["id"]], "action": "delete"}),
        viewer.post(url(made, "/import"), json={"format": "json", "content": "[]"}),
    ):
        assert attempt.status_code == 403


def test_a_pentest_that_is_archived_keeps_its_findings_read_only(admin: TestClient) -> None:
    made = make(admin)
    one = write(admin, made)
    assert admin.post(f"/api/pentests/{made['id']}/archive").status_code == 200
    refused = admin.post(url(made), json={"title": "late", "severity": "low"})
    assert (refused.status_code, refused.json()["code"]) == (409, "archived")
    assert admin.delete(url(made, f"/{one['id']}")).status_code == 409
    assert admin.get(url(made, f"/{one['id']}")).status_code == 200
    assert listing(admin, made)["total"] == 1


def test_findings_belong_to_one_pentest(admin: TestClient) -> None:
    made, other = make(admin), make(admin)
    one = write(admin, made)
    for method, tail in (("get", ""), ("patch", ""), ("delete", ""), ("post", "/restore")):
        answer = admin.request(method, url(other, f"/{one['id']}{tail}"), json={})
        assert (answer.status_code, answer.json()["code"]) == (404, "finding_not_found"), tail
    assert admin.get(f"/api/pentests/{GHOST}/findings").status_code == 404
    assert admin.get(url(made, f"/{GHOST}")).status_code == 404


def test_a_pentest_keeps_a_bounded_number_of_findings(
    admin: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(findings_service, "MAX_FINDINGS_PER_PENTEST", 1)
    made = make(admin)
    write(admin, made)
    refused = admin.post(url(made), json={"title": "one more", "severity": "low"})
    assert (refused.status_code, refused.json()["code"]) == (409, "too_many_findings")


def test_two_findings_made_at_once_get_two_numbers(admin: TestClient) -> None:
    made = make(admin)
    ids = [write(admin, made, title=f"F{n}")["number"] for n in range(3)]
    assert ids == [1, 2, 3]
    assert uuid.UUID(made["id"])
    assert {"image/png", "image/jpeg", "image/webp"} == findings_routes.IMAGE_TYPES


def test_helpers_of_the_service() -> None:
    assert findings_service.category_of(["WSTG-CONF-07"]) == "CONF"
    assert findings_service.category_of(["custom"]) == "Other"
    assert findings_service.category_of([]) == "Other"
    assert findings_service.confidence_of("certain") == "certain"
    assert findings_service.confidence_of("medium") == "firm"
    assert findings_service.looks_secret(SECRET_LINE)
    assert not findings_service.looks_secret("Server: nginx")
