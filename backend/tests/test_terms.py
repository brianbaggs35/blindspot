"""The terms of use: reading them, accepting them, and what needs them accepted."""

import runpy
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from tests.conftest import accept_terms, add_account, another_browser, set_up
from tests.pentest_helpers import make

from app.db.events import connection_string
from app.pentests.attestation import ATTESTATION_VERSION
from app.terms import __main__ as terms_main
from app.terms import routes as terms_routes
from app.terms.text import SECTIONS, TITLE, VERSION, render_markdown

ROOT = Path(__file__).resolve().parents[2]


def test_the_text_has_a_fingerprint_version_and_every_part() -> None:
    assert len(VERSION) == 12
    assert [section.id for section in SECTIONS] == [
        "permission",
        "responsibility",
        "agents",
        "liability",
        "changes",
    ]
    text = render_markdown()
    assert text.startswith(f"# {TITLE}\n")
    assert f"`{VERSION}`" in text
    assert "## 4. No warranty and no liability" in text
    assert text.endswith("\n")


def test_disclaimer_md_is_the_terms_as_they_are() -> None:
    written = (ROOT / "DISCLAIMER.md").read_text(encoding="utf-8")
    assert written == render_markdown(), "Run `make terms` to write DISCLAIMER.md again"


def test_the_file_writer_writes_where_it_is_told(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "terms.md"
    assert terms_main.main([str(target)]) == 0
    assert target.read_text(encoding="utf-8") == render_markdown()
    assert str(target) in capsys.readouterr().out
    assert terms_main.DEFAULT_PATH == ROOT / "DISCLAIMER.md"


@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_it_can_be_run_as_a_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "terms.md"
    monkeypatch.setattr("sys.argv", ["app.terms", str(target)])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("app.terms", run_name="__main__")
    assert stopped.value.code == 0
    assert target.read_text(encoding="utf-8") == render_markdown()
    assert str(target) in capsys.readouterr().out


def test_a_visitor_cannot_read_or_accept_them(api: TestClient) -> None:
    assert api.get("/api/terms").status_code == 401
    assert api.post("/api/terms/accept", json={"version": VERSION}).status_code == 401


def test_a_new_account_has_not_accepted_and_can_read_the_terms(api: TestClient) -> None:
    set_up(api)
    me = api.get("/api/auth/me").json()
    assert me["terms_accepted"] is False
    terms = api.get("/api/terms").json()
    assert terms["version"] == VERSION
    assert terms["accepted"] is False
    assert terms["accepted_at"] is None
    assert terms["title"] == TITLE
    assert terms["sections"][0]["id"] == "permission"
    assert terms["sections"][0]["paragraphs"]


def test_accepting_is_kept_shown_and_written_to_the_audit_log(
    api: TestClient, database_url: str
) -> None:
    set_up(api)
    answer = api.post("/api/terms/accept", json={"version": VERSION})
    assert answer.status_code == 200
    assert answer.json()["accepted"] is True
    assert answer.json()["accepted_at"] is not None
    assert api.get("/api/auth/me").json()["terms_accepted"] is True
    # Accepting again changes nothing and adds nothing to the trail.
    assert api.post("/api/terms/accept", json={"version": VERSION}).status_code == 200
    with psycopg.connect(connection_string(database_url)) as connection:
        rows = connection.execute(
            "SELECT actor_name, detail FROM audit_event WHERE action = 'terms.accept'"
        ).fetchall()
    assert rows == [("admin", {"version": VERSION})]


def test_an_answer_to_other_words_is_refused(api: TestClient) -> None:
    set_up(api)
    answer = api.post("/api/terms/accept", json={"version": "old-words"})
    assert answer.status_code == 409
    assert answer.json()["code"] == "terms_changed"
    assert api.get("/api/terms").json()["accepted"] is False
    assert api.post("/api/terms/accept", json={}).status_code == 422
    assert api.post("/api/terms/accept", json={"version": VERSION, "extra": 1}).status_code == 422


def test_a_viewer_accepts_for_themself(admin: TestClient) -> None:
    add_account(admin, "reader")
    reader = another_browser(admin, "reader")
    assert reader.get("/api/terms").json()["accepted"] is False
    assert reader.post("/api/terms/accept", json={"version": VERSION}).status_code == 200
    assert reader.get("/api/terms").json()["accepted"] is True
    # Accepting for one account does not accept for another.
    assert admin.get("/api/terms").json()["accepted"] is True
    others = {one["username"]: one["terms_accepted"] for one in admin.get("/api/users").json()}
    assert others == {"admin": True, "reader": True}


def test_changed_words_are_asked_for_again(
    admin: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert admin.get("/api/terms").json()["accepted"] is True
    monkeypatch.setattr(terms_routes, "VERSION", "a-new-version")
    monkeypatch.setattr("app.db.models.TERMS_VERSION", "a-new-version")
    now = admin.get("/api/terms").json()
    assert now["version"] == "a-new-version"
    assert now["accepted"] is False
    assert now["accepted_at"] is None
    assert admin.get("/api/auth/me").json()["terms_accepted"] is False


def attest(client: TestClient, made: dict[str, Any]) -> Any:
    document = {"confirmation": made["name"], "text_version": ATTESTATION_VERSION}
    return client.post(f"/api/pentests/{made['id']}/attest", json=document)


def test_permission_cannot_be_confirmed_until_the_terms_are_accepted(api: TestClient) -> None:
    set_up(api)
    made = make(api)
    refused = attest(api, made)
    assert refused.status_code == 403
    assert refused.json()["code"] == "terms_not_accepted"
    accept_terms(api)
    assert attest(api, made).status_code == 200


def test_a_pentest_cannot_start_until_the_terms_are_accepted(
    admin: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = make(admin)
    assert attest(admin, made).status_code == 200
    monkeypatch.setattr("app.db.models.TERMS_VERSION", "a-new-version")
    refused = admin.post(f"/api/pentests/{made['id']}/status", json={"to": "running"})
    assert refused.status_code == 403
    assert refused.json()["code"] == "terms_not_accepted"
