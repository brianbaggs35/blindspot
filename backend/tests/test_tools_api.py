"""The tool routes: reading, previewing the command, and custom tools."""

from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from tests.conftest import add_account, another_browser
from tests.tools_helpers import CUSTOM, NMAP, manifest

from app.db.events import connection_string
from app.tools import registry
from app.tools.manifest import Manifest
from app.tools.registry import Tool, fingerprint


@pytest.fixture(autouse=True)
def _with_nmap(monkeypatch: pytest.MonkeyPatch) -> None:
    """One bundled tool, so the routes have something to list."""
    parsed = Manifest.model_validate(NMAP)
    monkeypatch.setattr(
        registry, "bundled_tools", lambda: (Tool(parsed, "bundled", fingerprint(parsed)),)
    )


def actions(database_url: str) -> list[tuple[str, str | None]]:
    with psycopg.connect(connection_string(database_url)) as connection:
        return [
            (row[0], row[1])
            for row in connection.execute(
                "SELECT action, target_id FROM audit_event WHERE action LIKE 'tool.%' ORDER BY id"
            )
        ]


def make(admin: TestClient, **changes: Any) -> dict[str, Any]:
    answer = admin.post("/api/tools/custom", json=manifest(CUSTOM, **changes))
    assert answer.status_code == 201, answer.text
    return answer.json()


def test_the_list_has_every_tool_with_where_it_came_from(admin: TestClient) -> None:
    make(admin)
    listed = admin.get("/api/tools").json()
    assert [(tool["id"], tool["origin"], tool["tier"]) for tool in listed] == [
        ("c.nmap", "bundled", "core"),
        ("x.headers", "custom", "custom"),
    ]
    assert listed[0]["risk"] == "active"
    assert listed[0]["capabilities"] == ["NET_RAW"]
    assert listed[0]["execution"] == "process"


def test_a_tool_is_read_with_its_whole_manifest(admin: TestClient) -> None:
    detail = admin.get("/api/tools/c.nmap").json()
    assert detail["targets"] == ["targets"]
    assert detail["manifest"]["binary"] == "nmap"
    assert detail["manifest"]["params"]["scan"]["values"] == ["connect", "syn", "version"]
    assert len(detail["fingerprint"]) == 16
    assert admin.get("/api/tools/c.missing").status_code == 404
    assert admin.get("/api/tools/Not-An-Id").status_code == 422


def test_the_preview_shows_the_exact_command_and_what_it_touches(admin: TestClient) -> None:
    answer = admin.post(
        "/api/tools/c.nmap/preview",
        json={"values": {"targets": ["shop.example.com"], "scan": "syn"}},
    )
    assert answer.json() == {
        "argv": ["nmap", "-oX", "-", "-sS", "-p", "top-1000", "shop.example.com"],
        "targets": ["shop.example.com"],
    }


def test_a_preview_refuses_values_that_do_not_fit(admin: TestClient) -> None:
    answer = admin.post(
        "/api/tools/c.nmap/preview", json={"values": {"targets": ["a.example.com; id"]}}
    )
    assert answer.status_code == 422
    assert answer.json()["code"] == "invalid_tool_input"
    assert "spaces" in answer.json()["detail"]
    assert admin.post("/api/tools/c.nmap/preview", json={"values": {}, "x": 1}).status_code == 422
    assert admin.post("/api/tools/c.missing/preview", json={}).status_code == 404


def test_a_custom_tool_is_defined_read_changed_and_removed(
    admin: TestClient, database_url: str
) -> None:
    made = make(admin)
    assert made["origin"] == "custom"
    assert made["tier"] == "custom"
    assert admin.get("/api/tools/x.headers").json()["manifest"]["binary"] == "curl"
    shown = admin.post(
        "/api/tools/x.headers/preview", json={"values": {"url": "https://shop.example.com/"}}
    ).json()
    assert shown["argv"] == ["curl", "--head", "--silent", "https://shop.example.com/"]

    changed = admin.put("/api/tools/custom/x.headers", json=manifest(CUSTOM, risk="active"))
    assert changed.json()["risk"] == "active"
    assert changed.json()["fingerprint"] != made["fingerprint"]
    assert admin.get("/api/tools/x.headers").json()["risk"] == "active"

    assert admin.delete("/api/tools/custom/x.headers").status_code == 204
    assert admin.get("/api/tools/x.headers").status_code == 404
    assert actions(database_url) == [
        ("tool.custom.create", "x.headers"),
        ("tool.custom.update", "x.headers"),
        ("tool.custom.delete", "x.headers"),
    ]


def test_a_custom_tool_gets_the_same_checks_as_a_bundled_one(admin: TestClient) -> None:
    bad = admin.post("/api/tools/custom", json=manifest(CUSTOM, binary="bash"))
    assert bad.status_code == 422
    assert bad.json()["code"] == "invalid_tool"
    assert "a shell" in bad.json()["detail"]
    assert (
        admin.post("/api/tools/custom", json=manifest(CUSTOM, binary="python3")).status_code == 422
    )
    assert admin.post("/api/tools/custom", json=manifest(CUSTOM, id="c.curl")).status_code == 422
    assert (
        admin.post("/api/tools/custom", json=manifest(CUSTOM, argv=["{nope}"])).status_code == 422
    )
    assert (
        admin.post("/api/tools/custom", json=manifest(CUSTOM, capabilities=["NET_RAW"])).status_code
        == 422
    )
    assert admin.post("/api/tools/custom", json={}).status_code == 422


def test_a_tier_in_the_request_cannot_make_a_custom_tool_look_bundled(admin: TestClient) -> None:
    made = make(admin, tier="core")
    assert made["tier"] == "custom"
    assert made["origin"] == "custom"


def test_an_id_is_used_once_and_the_number_of_tools_is_limited(
    admin: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    make(admin)
    again = admin.post("/api/tools/custom", json=manifest(CUSTOM))
    assert again.status_code == 409
    assert again.json()["code"] == "tool_exists"
    monkeypatch.setattr("app.tools.routes.MAX_CUSTOM_TOOLS", 1)
    full = admin.post("/api/tools/custom", json=manifest(CUSTOM, id="x.other"))
    assert full.status_code == 409
    assert full.json()["code"] == "too_many_tools"


def test_a_changed_id_or_a_missing_tool_is_refused(admin: TestClient) -> None:
    make(admin)
    renamed = admin.put("/api/tools/custom/x.headers", json=manifest(CUSTOM, id="x.other"))
    assert renamed.status_code == 422
    assert renamed.json()["code"] == "tool_id_changed"
    assert admin.put("/api/tools/custom/x.nope", json=manifest(CUSTOM)).status_code == 404
    assert (
        admin.put("/api/tools/custom/x.headers", json=manifest(CUSTOM, binary="sh")).status_code
        == 422
    )
    assert admin.delete("/api/tools/custom/x.nope").status_code == 404
    assert admin.delete("/api/tools/custom/c.nmap").status_code == 404


def test_a_viewer_can_read_but_change_nothing(admin: TestClient) -> None:
    make(admin)
    add_account(admin, "vic")
    viewer = another_browser(admin, "vic")
    assert viewer.get("/api/tools").status_code == 200
    assert viewer.get("/api/tools/x.headers").status_code == 200
    assert viewer.post("/api/tools/custom", json=manifest(CUSTOM, id="x.more")).status_code == 403
    assert viewer.put("/api/tools/custom/x.headers", json=manifest(CUSTOM)).status_code == 403
    assert viewer.delete("/api/tools/custom/x.headers").status_code == 403
    assert viewer.post("/api/tools/c.nmap/preview", json={}).status_code == 403


def test_signed_out_visitors_see_nothing(api: TestClient) -> None:
    assert api.get("/api/tools").status_code == 401
    assert api.get("/api/tools/c.nmap").status_code == 401


def test_a_stored_manifest_that_no_longer_validates_is_skipped(
    admin: TestClient, database_url: str
) -> None:
    make(admin)
    with psycopg.connect(connection_string(database_url), autocommit=True) as connection:
        connection.execute(
            'UPDATE custom_tool SET manifest = \'{"id": "x.headers"}\'::jsonb'
            " WHERE tool_id = 'x.headers'"
        )
    assert [tool["id"] for tool in admin.get("/api/tools").json()] == ["c.nmap"]
