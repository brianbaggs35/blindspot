"""The methodology routes: browsing, playbook changes and reviewed updates."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
import psycopg
import pytest
import yaml
from fastapi.testclient import TestClient
from tests.conftest import add_account, another_browser, app_of, set_up
from tests.methodology_helpers import METHODOLOGY, PLAYBOOK, TOOLS, playbook, write_pack

from app.ai.adapters.factory import get_http_client_factory
from app.config import get_settings
from app.db.events import connection_string
from app.methodology import routes
from app.methodology.packs import BUNDLED, WSTG_UPSTREAM
from app.methodology.routes import get_packs_dir
from app.methodology.spec import MethodologySpec

UPSTREAM_HOST = "raw.githubusercontent.com"


def upstream_document() -> dict[str, Any]:
    return json.loads((BUNDLED / "wstg" / "checklist.json").read_text())


def no_methodologies() -> list[MethodologySpec]:
    return []


def replying(status: int, content: bytes) -> Callable[[httpx2.Request], httpx2.Response]:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, content=content)

    return handler


def serve(api: TestClient, handler: Callable[[httpx2.Request], httpx2.Response]) -> list[str]:
    """Answer the app's outgoing requests with `handler`; returns the URLs asked for."""
    asked: list[str] = []

    def factory() -> httpx2.AsyncClient:
        def record(request: httpx2.Request) -> httpx2.Response:
            asked.append(str(request.url))
            return handler(request)

        return httpx2.AsyncClient(transport=httpx2.MockTransport(record))

    app_of(api).dependency_overrides[get_http_client_factory] = lambda: factory
    return asked


def serve_json(api: TestClient, document: object) -> list[str]:
    return serve(api, lambda _request: httpx2.Response(200, content=json.dumps(document).encode()))


def packs_in(api: TestClient, folder: Path) -> Path:
    app_of(api).dependency_overrides[get_packs_dir] = lambda: folder
    return folder


@pytest.fixture
def admin(api: TestClient) -> TestClient:
    set_up(api)
    return api


def test_the_first_look_stores_wstg_and_listing_is_idempotent(admin: TestClient) -> None:
    first = admin.get("/api/methodologies").json()
    again = admin.get("/api/methodologies").json()
    assert first == again
    (wstg,) = first
    assert wstg["id"] == "wstg"
    assert (wstg["categories"], wstg["tests"], wstg["version_number"]) == (13, 133, 1)
    assert wstg["origin"] == "bundled"
    assert wstg["license"] == "CC BY-SA 4.0"
    assert wstg["authored_playbooks"] == 10
    assert wstg["custom_playbooks"] == 0
    assert wstg["manual_review_tests"] == 13
    assert wstg["can_update_from_upstream"] is True
    assert wstg["enabled"] is True
    assert len(wstg["content_hash"]) == 64


def test_the_detail_is_an_outline_of_every_category_and_test(admin: TestClient) -> None:
    detail = admin.get("/api/methodologies/wstg").json()
    assert [category["id"] for category in detail["category_list"]][:2] == [
        "WSTG-INFO",
        "WSTG-CONF",
    ]
    first = detail["category_list"][0]["tests"][0]
    assert first["id"] == "WSTG-INFO-01"
    assert first["risk_class"] == "safe"
    assert first["playbook_source"] == "generated"
    assert "playbook" not in first
    assert admin.get("/api/methodologies/nothing").status_code == 404


def test_a_test_comes_with_its_playbook_and_its_category(admin: TestClient) -> None:
    body = admin.get("/api/methodologies/wstg/tests/WSTG-INJT-04").json()
    assert body["category_id"] == "WSTG-INJT"
    assert body["category_name"] == "Injection"
    assert body["test"]["name"] == "SQL Injection"
    assert body["test"]["playbook"]["intrusive_steps"]
    assert admin.get("/api/methodologies/wstg/tests/WSTG-NOPE-01").status_code == 404
    assert admin.get("/api/methodologies/nothing/tests/WSTG-INJT-04").status_code == 404


def test_a_viewer_can_read_everything_and_change_nothing(admin: TestClient) -> None:
    add_account(admin, "vic")
    viewer = another_browser(admin, "vic")
    assert viewer.get("/api/methodologies").status_code == 200
    assert viewer.get("/api/methodologies/wstg/tests/WSTG-INFO-01").status_code == 200
    assert viewer.get("/api/methodologies/wstg/versions").status_code == 200
    for method, path in [
        ("PATCH", "/api/methodologies/wstg"),
        ("PUT", "/api/methodologies/wstg/tests/WSTG-INFO-01/playbook"),
        ("DELETE", "/api/methodologies/wstg/tests/WSTG-INFO-01/playbook"),
        ("GET", "/api/methodologies/wstg/updates"),
        ("POST", "/api/methodologies/wstg/updates"),
        ("POST", "/api/methodologies/reload"),
    ]:
        answer = viewer.request(method, path, json={})
        assert answer.status_code == 403, (method, path)


def test_a_playbook_is_replaced_and_put_back_and_the_trail_records_it(
    admin: TestClient, database_url: str
) -> None:
    path = "/api/methodologies/wstg/tests/WSTG-INFO-01/playbook"
    original = admin.get("/api/methodologies/wstg/tests/WSTG-INFO-01").json()["test"]["playbook"]
    changed = admin.put(path, json=PLAYBOOK)
    assert changed.status_code == 200, changed.text
    assert changed.json()["test"]["playbook_source"] == "custom"
    assert changed.json()["test"]["playbook"]["summary"] == PLAYBOOK["summary"]
    listed = admin.get("/api/methodologies").json()[0]
    assert listed["custom_playbooks"] == 1
    outline = admin.get("/api/methodologies/wstg").json()["category_list"][0]["tests"][0]
    assert (outline["playbook_source"], outline["tools"]) == ("custom", ["b.osint"])
    # Changing it again replaces the change instead of adding a second one.
    assert admin.put(path, json=playbook(summary="Again")).status_code == 200
    assert admin.get("/api/methodologies").json()[0]["custom_playbooks"] == 1
    assert admin.delete(path).status_code == 204
    restored = admin.get("/api/methodologies/wstg/tests/WSTG-INFO-01").json()["test"]
    assert restored["playbook"] == original
    assert restored["playbook_source"] == "generated"
    assert admin.delete(path).status_code == 404
    with psycopg.connect(connection_string(database_url)) as connection:
        actions = [
            row[0]
            for row in connection.execute(
                "SELECT action FROM audit_event WHERE action LIKE 'methodology.%' ORDER BY id"
            )
        ]
    assert "methodology.playbook.change" in actions
    assert "methodology.playbook.reset" in actions


def test_a_playbook_that_is_not_valid_or_for_no_test_is_refused(admin: TestClient) -> None:
    path = "/api/methodologies/wstg/tests/WSTG-INFO-01/playbook"
    assert admin.put(path, json={"summary": "only this"}).status_code == 422
    assert admin.put(path, json=playbook(tools=[])).status_code == 422
    assert admin.put(path, json=playbook(colour="red")).status_code == 422
    assert admin.put(path.replace("INFO-01", "NOPE-01"), json=PLAYBOOK).status_code == 404
    assert (
        admin.put("/api/methodologies/nothing/tests/X-1/playbook", json=PLAYBOOK).status_code == 404
    )
    assert admin.delete("/api/methodologies/nothing/tests/X-1/playbook").status_code == 404


def test_a_methodology_can_be_turned_off_and_on(admin: TestClient) -> None:
    off = admin.patch("/api/methodologies/wstg", json={"enabled": False})
    assert off.json()["enabled"] is False
    assert admin.get("/api/methodologies").json()[0]["enabled"] is False
    assert admin.patch("/api/methodologies/wstg", json={"enabled": True}).json()["enabled"] is True
    assert admin.patch("/api/methodologies/wstg", json={"enabled": "maybe"}).status_code == 422
    assert admin.patch("/api/methodologies/nothing", json={"enabled": True}).status_code == 404


def test_the_versions_start_with_the_one_that_shipped(admin: TestClient) -> None:
    (only,) = admin.get("/api/methodologies/wstg/versions").json()
    assert (only["number"], only["source"], only["tests"]) == (1, "bundled", 133)
    assert only["label"] == "snapshot 2026-11-23"
    assert admin.get("/api/methodologies/nothing/versions").status_code == 404


def test_looking_for_an_update_changes_nothing_and_says_when_there_is_none(
    admin: TestClient,
) -> None:
    checked = admin.get("/api/methodologies/wstg/updates").json()
    assert checked["changed"] is False
    assert checked["current_hash"] == checked["candidate_hash"]
    assert checked["diff"]["added"] == []
    assert len(admin.get("/api/methodologies/wstg/versions").json()) == 1


def test_an_upstream_update_shows_its_diff_and_is_applied_only_when_confirmed(
    admin: TestClient,
) -> None:
    document = upstream_document()
    tests = document["categories"]["Information Gathering"]["tests"]
    tests[0]["objectives"] = ["Changed upstream"]
    tests.append(
        {
            "id": "WSTG-INFO-10",
            "name": "A new test",
            "reference": "https://wstg.owasp.org/latest/x",
            "objectives": ["New"],
        }
    )
    asked = serve_json(admin, document)
    checked = admin.get("/api/methodologies/wstg/updates?source=upstream").json()
    assert asked == [WSTG_UPSTREAM]
    assert checked["changed"] is True
    assert checked["diff"]["added"] == ["WSTG-INFO-10"]
    assert checked["diff"]["changed"] == [
        {"id": "WSTG-INFO-01", "fields": ["objectives", "playbook"]}
    ]
    assert checked["candidate_label"].startswith("snapshot 20")
    assert admin.get("/api/methodologies").json()[0]["tests"] == 133, "looking changes nothing"

    wrong = admin.post(
        "/api/methodologies/wstg/updates",
        json={"source": "upstream", "candidate_hash": "0" * 64},
    )
    assert wrong.status_code == 409
    assert wrong.json()["code"] == "candidate_changed"
    assert admin.get("/api/methodologies").json()[0]["tests"] == 133

    body = {"source": "upstream", "candidate_hash": checked["candidate_hash"]}
    applied = admin.post("/api/methodologies/wstg/updates", json=body)
    assert applied.status_code == 200, applied.text
    assert (applied.json()["tests"], applied.json()["version_number"]) == (134, 2)
    # Applying the same update again changes nothing.
    again = admin.post("/api/methodologies/wstg/updates", json=body)
    assert again.json()["version_number"] == 2
    versions = admin.get("/api/methodologies/wstg/versions").json()
    assert [(v["number"], v["source"], v["tests"]) for v in versions] == [
        (2, "upstream", 134),
        (1, "bundled", 133),
    ]
    assert admin.get("/api/methodologies/wstg/updates?source=upstream").json()["changed"] is False


def test_a_playbook_changed_by_hand_survives_an_update(admin: TestClient) -> None:
    path = "/api/methodologies/wstg/tests/WSTG-INFO-01/playbook"
    admin.put(path, json=PLAYBOOK)
    document = upstream_document()
    document["categories"]["Information Gathering"]["tests"][0]["name"] = "Renamed"
    serve_json(admin, document)
    checked = admin.get("/api/methodologies/wstg/updates?source=upstream").json()
    body = {"source": "upstream", "candidate_hash": checked["candidate_hash"]}
    assert admin.post("/api/methodologies/wstg/updates", json=body).status_code == 200
    kept = admin.get("/api/methodologies/wstg/tests/WSTG-INFO-01").json()["test"]
    assert (kept["name"], kept["playbook_source"]) == ("Renamed", "custom")


@pytest.mark.parametrize(
    ("handler", "code", "status"),
    [
        (replying(404, b""), "upstream_failed", 502),
        (replying(200, b"x" * 2_100_000), "upstream_failed", 502),
        (replying(200, b"not json"), "pack_invalid", 422),
        (replying(200, b'{"categories": 3}'), "pack_invalid", 422),
    ],
)
def test_an_upstream_that_misbehaves_is_reported_and_nothing_changes(
    admin: TestClient,
    handler: Callable[[httpx2.Request], httpx2.Response],
    code: str,
    status: int,
) -> None:
    serve(admin, handler)
    answer = admin.get("/api/methodologies/wstg/updates?source=upstream")
    assert (answer.status_code, answer.json()["code"]) == (status, code)
    assert UPSTREAM_HOST not in json.dumps(answer.json()) or code == "upstream_failed"
    assert admin.get("/api/methodologies").json()[0]["version_number"] == 1


def test_an_upstream_that_cannot_be_reached_is_reported(admin: TestClient) -> None:
    def down(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route", request=request)

    serve(admin, down)
    answer = admin.get("/api/methodologies/wstg/updates?source=upstream")
    assert (answer.status_code, answer.json()["code"]) == (502, "upstream_failed")
    assert "Could not reach" in answer.json()["title"]


def test_only_a_pack_dropped_in_the_folder_is_added_by_reload(
    admin: TestClient, tmp_path: Path
) -> None:
    folder = packs_in(admin, tmp_path)
    write_pack(folder)
    (folder / "empty").mkdir()
    done = admin.post("/api/methodologies/reload")
    assert done.status_code == 200, done.text
    assert done.json() == {
        "added": ["ptes"],
        "updates_available": [],
        "problems": {"empty": "There is no methodology.yaml"},
    }
    listed = {item["id"]: item for item in admin.get("/api/methodologies").json()}
    assert listed["ptes"]["origin"] == "folder"
    assert (listed["ptes"]["categories"], listed["ptes"]["tests"]) == (2, 3)
    assert listed["ptes"]["can_update_from_upstream"] is False
    # Reading the folder again adds nothing.
    assert admin.post("/api/methodologies/reload").json()["added"] == []
    test = admin.get("/api/methodologies/ptes/tests/PTES-RECON-01").json()["test"]
    assert test["playbook_source"] == "authored"


def test_a_pack_cannot_take_the_id_of_a_methodology_that_ships(
    admin: TestClient, tmp_path: Path
) -> None:
    folder = packs_in(admin, tmp_path)
    clash = {**METHODOLOGY, "id": "wstg"}
    pack = write_pack(folder, **{"methodology.yaml": clash})
    pack.rename(folder / "wstg")
    answer = admin.post("/api/methodologies/reload").json()
    assert answer["added"] == []
    assert "ships with Blindspot" in answer["problems"]["wstg"]
    assert admin.get("/api/methodologies").json()[0]["origin"] == "bundled"


def test_a_pack_that_changed_is_reported_then_applied_after_its_diff(
    admin: TestClient, tmp_path: Path
) -> None:
    folder = packs_in(admin, tmp_path)
    write_pack(folder)
    admin.post("/api/methodologies/reload")
    tools = {"tests": {**TOOLS["tests"], "PTES-RECON-02": {"tools": ["c.nmap", "b.http"]}}}
    write_pack(folder, **{"tools.yaml": tools})
    assert admin.post("/api/methodologies/reload").json()["updates_available"] == ["ptes"]
    checked = admin.get("/api/methodologies/ptes/updates").json()
    assert checked["source"] == "origin"
    assert checked["changed"] is True
    assert [item["id"] for item in checked["diff"]["changed"]] == ["PTES-RECON-02"]
    body = {"candidate_hash": checked["candidate_hash"]}
    applied = admin.post("/api/methodologies/ptes/updates", json=body).json()
    assert applied["version_number"] == 2
    versions = admin.get("/api/methodologies/ptes/versions").json()
    assert versions[0]["source"] == "folder"
    assert admin.post("/api/methodologies/reload").json()["updates_available"] == []


def test_a_pack_that_is_broken_on_disk_cannot_be_checked_or_applied(
    admin: TestClient, tmp_path: Path
) -> None:
    folder = packs_in(admin, tmp_path)
    write_pack(folder)
    admin.post("/api/methodologies/reload")
    (folder / "ptes" / "tools.yaml").write_text(yaml.safe_dump({"tests": {}}))
    answer = admin.get("/api/methodologies/ptes/updates")
    assert (answer.status_code, answer.json()["code"]) == (422, "pack_invalid")
    assert "tools.yaml has no entry for" in answer.json()["title"]
    sent = admin.post("/api/methodologies/ptes/updates", json={"candidate_hash": "a" * 64})
    assert sent.status_code == 422


def test_only_wstg_has_an_upstream(admin: TestClient, tmp_path: Path) -> None:
    packs_in(admin, tmp_path)
    write_pack(tmp_path)
    admin.post("/api/methodologies/reload")
    answer = admin.get("/api/methodologies/ptes/updates?source=upstream")
    assert (answer.status_code, answer.json()["code"]) == (422, "no_upstream")
    assert admin.get("/api/methodologies/wstg/updates?source=elsewhere").status_code == 422


def test_a_release_that_stops_shipping_a_methodology_says_so(
    admin: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin.get("/api/methodologies")
    monkeypatch.setattr(routes, "bundled", no_methodologies)
    answer = admin.get("/api/methodologies/wstg/updates")
    assert (answer.status_code, answer.json()["code"]) == (404, "not_found")


def test_the_candidate_hash_must_look_like_a_hash(admin: TestClient) -> None:
    for bad in ("short", "G" * 64, "A" * 64):
        answer = admin.post("/api/methodologies/wstg/updates", json={"candidate_hash": bad})
        assert answer.status_code == 422


def test_the_default_packs_folder_is_under_the_data_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BLINDSPOT_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    assert get_packs_dir() == tmp_path / "methodologies"


def test_the_upstream_address_and_client_are_fixed(admin: TestClient) -> None:
    assert WSTG_UPSTREAM.startswith(f"https://{UPSTREAM_HOST}/OWASP/wstg/")
    assert get_http_client_factory() is not None
    assert PLAYBOOK
