"""The results of a pentest: notes, imported output, the three views, filters, annotations, the
trash and secrets that stay masked until revealed."""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.conftest import add_account, another_browser
from tests.pentest_helpers import make

from app.db.events import connection_string
from app.results import routes as results_routes
from app.results import schemas as results_schemas
from app.results import service as results_service
from app.tools.parsers import PARSERS, ToolResult
from app.tools.parsers.schema import Credential, Issue, Severity

FIXTURES = Path(__file__).parent / "fixtures" / "tools"
NMAP = (FIXTURES / "nmap.xml").read_text()
SECRET = "hunter2-very-secret"


def url(made: dict[str, Any], tail: str = "") -> str:
    return f"/api/pentests/{made['id']}/results{tail}"


def note(admin: TestClient, made: dict[str, Any], **changes: Any) -> dict[str, Any]:
    answer = admin.post(url(made), json={"title": "Login page looks odd"} | changes)
    assert answer.status_code == 201, answer.text
    return answer.json()


def imported(admin: TestClient, made: dict[str, Any], **changes: Any) -> dict[str, Any]:
    document = {"parser": "nmap_xml", "content": NMAP} | changes
    answer = admin.post(url(made, "/import"), json=document)
    assert answer.status_code == 201, answer.text
    return answer.json()


def listing(admin: TestClient, made: dict[str, Any], **query: Any) -> dict[str, Any]:
    answer = admin.get(url(made), params=query)
    assert answer.status_code == 200, answer.text
    return answer.json()


def titles(admin: TestClient, made: dict[str, Any], **query: Any) -> list[str]:
    return [one["title"] for one in listing(admin, made, **query)["items"]]


def audit_actions(database_url: str) -> list[str]:
    with psycopg.connect(connection_string(database_url)) as connection:
        return [
            row[0]
            for row in connection.execute(
                "SELECT action FROM audit_event WHERE action LIKE 'result.%' ORDER BY id"
            )
        ]


@pytest.fixture
def with_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """A parser that finds a password, so a result can hold a secret."""

    def parse(data: bytes) -> ToolResult:
        return ToolResult(
            tool="x",
            parser="leaky",
            issues=[Issue(title="Default password", severity=Severity.HIGH, evidence=SECRET)],
            credentials=[
                Credential(target="10.0.0.5:22", username="root", secret=SECRET),  # pyright: ignore[reportArgumentType]
                Credential(target="10.0.0.5:80", kind="token", secret="second"),  # pyright: ignore[reportArgumentType]
            ],
        )

    monkeypatch.setitem(PARSERS, "leaky", parse)


def test_a_person_writes_a_note_and_it_is_listed(admin: TestClient, database_url: str) -> None:
    made = make(admin)
    one = note(admin, made, notes="Seen twice", tags=["login", "manual check"], severity="low")
    assert (one["source"], one["status"], one["top_severity"]) == ("manual", "manual", "low")
    assert one["tags"] == ["login", "manual check"]
    assert one["friendly"] is None
    assert one["technical"] is None
    assert one["has_raw"] is False
    assert [i["title"] for i in listing(admin, made)["items"]] == ["Login page looks odd"]
    assert "result.create" in audit_actions(database_url)


def test_pasted_nmap_output_is_read_and_shown_three_ways(admin: TestClient) -> None:
    made = make(admin)
    one = imported(admin, made, title="Nmap from the laptop", test_id="WSTG-INFO-02", tags=["nmap"])
    assert (one["source"], one["tool_id"], one["parser"]) == ("import", "c.nmap", "nmap_xml")
    assert one["summary"] == ["1 host answered, with 2 open ports."]
    friendly = one["friendly"]
    assert friendly["visuals"]["port_map"][0]["address"] == "127.0.0.1"
    assert {p["port"] for p in friendly["visuals"]["port_map"][0]["ports"]} >= {8081, 8443}
    assert one["technical"]["hosts"][0]["address"] == "127.0.0.1"
    assert "credentials" not in one["technical"]
    raw = admin.get(url(made, f"/{one['id']}/raw")).json()
    assert raw["output"] == NMAP
    assert raw["truncated"] is False
    assert raw["size"] == len(NMAP)
    assert raw["command"] == []
    assert raw["exit_code"] is None
    shown = admin.get(url(made, f"/{one['id']}")).json()
    assert shown == one


def test_output_that_cannot_be_read_is_refused_with_a_reason(admin: TestClient) -> None:
    made = make(admin)
    answer = admin.post(url(made, "/import"), json={"parser": "nmap_xml", "content": "<html/>"})
    assert (answer.status_code, answer.json()["code"]) == (422, "unreadable_output")
    answer = admin.post(url(made, "/import"), json={"parser": "nope", "content": "x"})
    assert (answer.status_code, answer.json()["code"]) == (422, "unknown_parser")
    answer = admin.post(url(made, "/import"), json={"parser": "nmap_xml", "content": ""})
    assert answer.status_code == 422
    assert listing(admin, made)["total"] == 0


def test_every_parser_belongs_to_a_bundled_tool() -> None:
    assert {results_routes.tool_for_parser(p) for p in PARSERS} == {
        "c.nmap",
        "p.ffuf",
        "o.whatweb",
        "p.waf",
        "p.testssl",
        "o.nikto",
        "c.nuclei",
        "p.pd",
    }


def test_the_list_filters_and_searches(admin: TestClient) -> None:
    made = make(admin)
    note(admin, made, title="Alpha", tags=["one"], test_id="WSTG-INFO-01")
    note(admin, made, title="Bravo", notes="found a Needle here", severity="high")
    imported(admin, made, title="Charlie")
    imported(admin, made, title="Delta", tool_id="x.mine")
    assert titles(admin, made) == ["Delta", "Charlie", "Bravo", "Alpha"]
    assert titles(admin, made, tool="c.nmap") == ["Charlie"]
    assert titles(admin, made, test="WSTG-INFO-01") == ["Alpha"]
    assert titles(admin, made, severity="high") == ["Bravo"]
    assert titles(admin, made, q="needle") == ["Bravo"]
    assert titles(admin, made, q="ONE") == ["Alpha"]
    assert titles(admin, made, q="c.nmap") == ["Charlie"]
    assert titles(admin, made, q="wstg-info") == ["Alpha"]
    assert titles(admin, made, q="100%") == []
    assert titles(admin, made, since="2999-01-01T00:00:00Z") == []
    assert titles(admin, made, until="2000-01-01T00:00:00Z") == []
    assert len(titles(admin, made, since="2000-01-01T00:00:00Z", until="2999-01-01T00:00:00Z")) == 4
    assert titles(admin, made, limit=2) == ["Delta", "Charlie"]
    assert titles(admin, made, limit=2, offset=2) == ["Bravo", "Alpha"]
    everything = listing(admin, made, limit=1)
    assert everything["total"] == 4
    assert everything["tools"] == ["c.nmap", "x.mine"]
    assert everything["agents"] == []


def test_annotations_change_and_the_output_does_not(admin: TestClient, database_url: str) -> None:
    made = make(admin)
    one = imported(admin, made)
    answer = admin.patch(
        url(made, f"/{one['id']}"),
        json={"title": "Renamed", "notes": "Checked", "tags": ["b", "a", "a"], "test_id": "T-1"},
    )
    assert answer.status_code == 200, answer.text
    changed = answer.json()
    assert (changed["title"], changed["notes"], changed["tags"]) == (
        "Renamed",
        "Checked",
        ["a", "b"],
    )
    assert changed["test_id"] == "T-1"
    assert changed["technical"] == one["technical"]
    cleared = admin.patch(url(made, f"/{one['id']}"), json={"test_id": None}).json()
    assert (cleared["test_id"], cleared["title"]) == (None, "Renamed")
    untouched = admin.patch(url(made, f"/{one['id']}"), json={}).json()
    assert untouched["tags"] == ["a", "b"]
    for bad in ({"output": "x"}, {"title": ""}, {"tags": ["Bad Tag!"]}, {"notes": "x" * 8001}):
        assert admin.patch(url(made, f"/{one['id']}"), json=bad).status_code == 422
    assert audit_actions(database_url).count("result.update") == 3


def test_delete_goes_to_the_trash_and_restore_brings_it_back(admin: TestClient) -> None:
    made = make(admin)
    one = note(admin, made)
    assert admin.delete(url(made, f"/{one['id']}")).status_code == 204
    assert listing(admin, made)["total"] == 0
    trashed = listing(admin, made, view="trash")["items"]
    assert [(i["id"], i["deleted"]) for i in trashed] == [(one["id"], True)]
    again = admin.delete(url(made, f"/{one['id']}"))
    assert (again.status_code, again.json()["code"]) == (409, "in_trash")
    back = admin.post(url(made, f"/{one['id']}/restore"))
    assert back.status_code == 200
    assert back.json()["deleted"] is False
    assert listing(admin, made)["total"] == 1
    twice = admin.post(url(made, f"/{one['id']}/restore"))
    assert (twice.status_code, twice.json()["code"]) == (409, "not_in_trash")


def test_bulk_actions_change_only_what_they_can(admin: TestClient) -> None:
    made = make(admin)
    first, second = note(admin, made, title="A"), note(admin, made, title="B", tags=["x"])
    ids = [first["id"], second["id"]]
    assert admin.post(
        url(made, "/bulk"), json={"ids": ids, "action": "tag", "tag": "x"}
    ).json() == {"changed": 1}
    assert admin.post(
        url(made, "/bulk"), json={"ids": ids, "action": "untag", "tag": "x"}
    ).json() == {"changed": 2}
    assert admin.post(
        url(made, "/bulk"), json={"ids": ids, "action": "untag", "tag": "x"}
    ).json() == {"changed": 0}
    assert (
        admin.post(url(made, "/bulk"), json={"ids": ids, "action": "delete"}).json()["changed"] == 2
    )
    assert (
        admin.post(url(made, "/bulk"), json={"ids": ids, "action": "delete"}).json()["changed"] == 0
    )
    assert (
        admin.post(url(made, "/bulk"), json={"ids": ids[:1], "action": "restore"}).json()["changed"]
        == 1
    )
    assert (
        admin.post(url(made, "/bulk"), json={"ids": ids[:1], "action": "restore"}).json()["changed"]
        == 0
    )
    assert titles(admin, made) == ["A"]
    missing = admin.post(url(made, "/bulk"), json={"ids": ids, "action": "tag"})
    assert (missing.status_code, missing.json()["code"]) == (422, "tag_needed")
    assert admin.post(url(made, "/bulk"), json={"ids": [], "action": "delete"}).status_code == 422
    other = make(admin)
    assert (
        admin.post(url(other, "/bulk"), json={"ids": ids, "action": "delete"}).json()["changed"]
        == 0
    )


def test_a_secret_a_tool_found_is_masked_sealed_and_revealed_only_on_request(
    admin: TestClient, database_url: str, with_secret: None
) -> None:
    made = make(admin)
    one = imported(admin, made, parser="leaky", content="whatever", tool_id="c.sshcheck")
    assert [(c["index"], c["target"], c["username"], c["secret"]) for c in one["credentials"]] == [
        (0, "10.0.0.5:22", "root", "••••••••"),
        (1, "10.0.0.5:80", None, "••••••••"),
    ]
    reading = admin.get(url(made, f"/{one['id']}")).text + admin.get(url(made)).text
    assert "second" not in reading
    assert "credentials" not in one["technical"]
    with psycopg.connect(connection_string(database_url)) as connection:
        stored = connection.execute(
            "SELECT credentials, raw_output, normalized::text FROM pentest_result"
        ).fetchone()
    assert stored is not None
    assert not any(SECRET in str(column) or "second" in str(column) for column in stored[:2])
    assert stored[2] is not None
    assert "second" not in stored[2]
    revealed = admin.post(url(made, f"/{one['id']}/credentials/1/reveal"))
    assert revealed.json() == {"secret": "second"}
    assert admin.post(url(made, f"/{one['id']}/credentials/2/reveal")).status_code == 404
    assert admin.post(url(made, f"/{one['id']}/credentials/-1/reveal")).status_code == 404
    with psycopg.connect(connection_string(database_url)) as connection:
        events = connection.execute(
            "SELECT action, detail::text FROM audit_event WHERE action = 'result.reveal'"
        ).fetchall()
    assert [e[0] for e in events] == ["result.reveal"]
    assert "second" not in str(events)


def test_a_viewer_reads_and_changes_nothing(admin: TestClient, with_secret: None) -> None:
    made = make(admin)
    one = imported(admin, made, parser="leaky", content="x", tool_id="c.sshcheck")
    add_account(admin, "vic")
    viewer = another_browser(admin, "vic")
    assert viewer.get(url(made)).status_code == 200
    assert viewer.get(url(made, f"/{one['id']}")).status_code == 200
    assert viewer.get(url(made, f"/{one['id']}/raw")).status_code == 200
    writes = [
        viewer.post(url(made), json={"title": "x"}),
        viewer.post(url(made, "/import"), json={"parser": "nmap_xml", "content": NMAP}),
        viewer.post(url(made, "/bulk"), json={"ids": [one["id"]], "action": "delete"}),
        viewer.patch(url(made, f"/{one['id']}"), json={"title": "x"}),
        viewer.delete(url(made, f"/{one['id']}")),
        viewer.post(url(made, f"/{one['id']}/restore")),
        viewer.post(url(made, f"/{one['id']}/credentials/0/reveal")),
    ]
    assert [w.status_code for w in writes] == [403] * 7


def test_a_pentest_that_is_archived_or_in_the_trash_keeps_its_results_read_only(
    admin: TestClient,
) -> None:
    made = make(admin)
    one = note(admin, made)
    assert admin.post(f"/api/pentests/{made['id']}/archive").status_code == 200
    refused = admin.post(url(made), json={"title": "late"})
    assert (refused.status_code, refused.json()["code"]) == (409, "archived")
    assert admin.delete(url(made, f"/{one['id']}")).status_code == 409
    assert admin.get(url(made, f"/{one['id']}")).status_code == 200
    assert listing(admin, made)["total"] == 1


def test_results_belong_to_one_pentest(admin: TestClient) -> None:
    made, other = make(admin), make(admin)
    one = note(admin, made)
    for method, tail in (("get", ""), ("get", "/raw"), ("patch", ""), ("delete", "")):
        answer = admin.request(method, url(other, f"/{one['id']}{tail}"), json={})
        assert answer.status_code == 404, (method, tail)
        assert answer.json()["code"] == "result_not_found"
    ghost = "/api/pentests/00000000-0000-7000-8000-000000000000/results"
    assert admin.get(ghost).status_code == 404
    assert admin.get(url(made, "/00000000-0000-7000-8000-000000000000")).status_code == 404


def test_a_pentest_keeps_a_bounded_number_of_results(
    admin: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(results_service, "MAX_RESULTS_PER_PENTEST", 1)
    made = make(admin)
    note(admin, made)
    refused = admin.post(url(made), json={"title": "one too many"})
    assert (refused.status_code, refused.json()["code"]) == (409, "too_many_results")
    refused = admin.post(url(made, "/import"), json={"parser": "nmap_xml", "content": NMAP})
    assert refused.status_code == 409


def test_long_raw_output_is_cut_and_says_so(
    admin: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(results_service, "MAX_RAW_SHOWN", 100)
    monkeypatch.setattr(results_schemas, "MAX_RAW_SHOWN", 100)
    made = make(admin)
    one = imported(admin, made)
    raw = admin.get(url(made, f"/{one['id']}/raw")).json()
    assert (len(raw["output"]), raw["truncated"], raw["size"]) == (100, True, len(NMAP))


async def test_a_tool_run_is_stored_with_its_command_exit_code_and_time(
    admin: TestClient, database_url: str
) -> None:
    """The runner (BLI-55) stores its runs through `record_result`; this is what it will see."""
    made = make(admin)
    engine = create_async_engine(database_url)
    async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
        results_service.record_result(
            session,
            uuid.UUID(made["id"]),
            source="tool",
            title="Nmap run",
            result=ToolResult(tool="c.nmap", parser="nmap_xml"),
            raw="out",
            run=results_service.Run(
                tool_id="c.nmap",
                agent_role="recon",
                test_id="WSTG-INFO-02",
                command=["nmap", "-p", "80", "10.0.0.5"],
                exit_code=1,
                duration_ms=1234,
                ran_at=datetime(2026, 1, 2, tzinfo=UTC),
            ),
            status="failed",
        )
    await engine.dispose()
    (one,) = listing(admin, made)["items"]
    assert (one["source"], one["status"], one["agent_role"]) == ("tool", "failed", "recon")
    assert one["ran_at"].startswith("2026-01-02")
    assert listing(admin, made)["agents"] == ["recon"]
    assert titles(admin, made, agent="recon") == ["Nmap run"]
    assert titles(admin, made, agent="other") == []
    detail = admin.get(url(made, f"/{one['id']}")).json()
    assert (detail["command"], detail["exit_code"], detail["duration_ms"]) == (
        ["nmap", "-p", "80", "10.0.0.5"],
        1,
        1234,
    )
    assert admin.get(url(made, f"/{one['id']}/raw")).json()["output"] == "out"
    assert detail["summary"] == ["The tool ran and found nothing to report."]
