"""The policy routes: read by anyone signed in, changed only by administrators, and audited."""

import uuid
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import add_account, another_browser
from tests.pentest_helpers import make as make_pentest
from tests.tools_helpers import NMAP

from app.db.events import connection_string
from app.tools import policy_routes, registry
from app.tools.manifest import Manifest
from app.tools.registry import Tool, fingerprint

POLICY = "/api/tools/policy"
GRANTS = f"{POLICY}/grants"


@pytest.fixture(autouse=True)
def _with_nmap(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = Manifest.model_validate(NMAP)
    monkeypatch.setattr(
        registry, "bundled_tools", lambda: (Tool(parsed, "bundled", fingerprint(parsed)),)
    )


def grant(**changes: Any) -> dict[str, Any]:
    return {"role": "test-agent", "tool": "c.nmap", "max_risk": "active", "mode": "auto"} | changes


def actions(database_url: str) -> list[tuple[str, str | None]]:
    with psycopg.connect(connection_string(database_url)) as connection:
        return [
            (row[0], row[1])
            for row in connection.execute(
                "SELECT action, target_id FROM audit_event WHERE action LIKE 'tool.policy.%' "
                "ORDER BY id"
            )
        ]


def test_the_policy_starts_with_the_defaults_and_no_rules(admin: TestClient) -> None:
    answer = admin.get(POLICY)
    assert answer.status_code == 200
    assert answer.json() == {
        "kill_switch": False,
        "defaults": [
            {"risk": "passive", "mode": "auto"},
            {"risk": "active", "mode": "ask"},
            {"risk": "intrusive", "mode": "ask"},
            {"risk": "destructive", "mode": "deny"},
        ],
        "grants": [],
    }


def test_an_administrator_makes_changes_and_removes_a_rule(
    admin: TestClient, database_url: str
) -> None:
    made = admin.put(GRANTS, json=grant())
    assert made.status_code == 200, made.text
    rule = made.json()
    assert rule | {"id": None} == grant() | {"id": None, "pentest_id": None}
    # The same role, tool and pentest is one rule, changed in place.
    changed = admin.put(GRANTS, json=grant(mode="ask", max_risk="passive")).json()
    assert changed["id"] == rule["id"]
    assert (changed["mode"], changed["max_risk"]) == ("ask", "passive")
    # Another pentest, or every role, is another rule.
    pentest = make_pentest(admin)
    scoped = admin.put(GRANTS, json=grant(pentest_id=pentest["id"])).json()
    any_role = admin.put(GRANTS, json=grant(role="*", tool="*")).json()
    assert len({rule["id"], scoped["id"], any_role["id"]}) == 3
    assert len(admin.get(POLICY).json()["grants"]) == 3
    assert admin.delete(f"{GRANTS}/{rule['id']}").status_code == 204
    assert admin.delete(f"{GRANTS}/{rule['id']}").status_code == 404
    assert [g["id"] for g in admin.get(POLICY).json()["grants"]] == [scoped["id"], any_role["id"]]
    assert [name for name, _ in actions(database_url)] == [
        "tool.policy.grant",
        "tool.policy.grant",
        "tool.policy.grant",
        "tool.policy.grant",
        "tool.policy.revoke",
    ]


def test_a_rule_that_could_let_a_dangerous_tool_through_is_refused(admin: TestClient) -> None:
    refused = admin.put(GRANTS, json=grant(max_risk="destructive", mode="auto"))
    assert (refused.status_code, refused.json()["code"]) == (422, "grant_destructive")
    assert admin.put(GRANTS, json=grant(max_risk="destructive", mode="ask")).status_code == 422
    assert admin.put(GRANTS, json=grant(max_risk="destructive", mode="deny")).status_code == 200
    intrusive = admin.put(GRANTS, json=grant(max_risk="intrusive", mode="auto"))
    assert (intrusive.status_code, intrusive.json()["code"]) == (422, "grant_needs_a_person")
    assert admin.put(GRANTS, json=grant(max_risk="intrusive", mode="ask")).status_code == 200


@pytest.mark.parametrize(
    ("changes", "status", "code"),
    [
        ({"tool": "c.unknown"}, 404, "tool_not_found"),
        ({"pentest_id": str(uuid.uuid4())}, 404, "pentest_not_found"),
        ({"role": "root"}, 422, "validation_failed"),
        ({"tool": "../etc"}, 422, "validation_failed"),
        ({"mode": "always"}, 422, "validation_failed"),
        ({"max_risk": "scary"}, 422, "validation_failed"),
        ({"approved": True}, 422, "validation_failed"),
    ],
)
def test_a_rule_that_does_not_make_sense_is_refused(
    admin: TestClient, changes: dict[str, Any], status: int, code: str
) -> None:
    answer = admin.put(GRANTS, json=grant(**changes))
    assert (answer.status_code, answer.json()["code"]) == (status, code)
    assert admin.get(POLICY).json()["grants"] == []


def test_the_number_of_rules_is_bounded(admin: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(policy_routes, "MAX_GRANTS", 1)
    assert admin.put(GRANTS, json=grant()).status_code == 200
    assert admin.put(GRANTS, json=grant()).status_code == 200  # the same rule, changed
    full = admin.put(GRANTS, json=grant(role="chat"))
    assert (full.status_code, full.json()["code"]) == (409, "too_many_grants")


def test_the_kill_switch_is_read_set_and_audited(admin: TestClient, database_url: str) -> None:
    assert admin.put(f"{POLICY}/kill-switch", json={"on": True}).json() == {"on": True}
    assert admin.get(POLICY).json()["kill_switch"] is True
    assert admin.put(f"{POLICY}/kill-switch", json={"on": True}).status_code == 200
    assert admin.put(f"{POLICY}/kill-switch", json={"on": False}).json() == {"on": False}
    assert admin.get(POLICY).json()["kill_switch"] is False
    assert admin.put(f"{POLICY}/kill-switch", json={"on": "maybe"}).status_code == 422
    assert [name for name, _ in actions(database_url)] == ["tool.policy.kill_switch"] * 3


def test_a_viewer_can_read_the_policy_and_change_nothing(admin: TestClient) -> None:
    rule = admin.put(GRANTS, json=grant()).json()
    add_account(admin, "vic", role="viewer")
    viewer = another_browser(admin, "vic")
    assert viewer.get(POLICY).status_code == 200
    assert viewer.put(GRANTS, json=grant(mode="ask")).status_code == 403
    assert viewer.delete(f"{GRANTS}/{rule['id']}").status_code == 403
    assert viewer.put(f"{POLICY}/kill-switch", json={"on": True}).status_code == 403
    assert admin.get(POLICY).json()["kill_switch"] is False


def test_signed_out_people_read_nothing(api: TestClient) -> None:
    assert api.get(POLICY).status_code == 401
    assert api.put(GRANTS, json=grant()).status_code == 401


def test_two_changes_at_once_to_the_same_rule_lose_cleanly(
    admin: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def collide(_self: AsyncSession, *_args: object, **_kwargs: object) -> None:
        raise IntegrityError("INSERT", {}, Exception("duplicate"))

    monkeypatch.setattr(AsyncSession, "flush", collide)
    answer = admin.put(GRANTS, json=grant())
    assert (answer.status_code, answer.json()["code"]) == (409, "grant_exists")
