"""The Agents page and the settings behind it: the hierarchy with how each agent has done, the caps
and presets a mission starts from, the versions of the prompts, and what a start shows before it is
confirmed."""

import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from tests.agents_helpers import HEADERS_TEST, SCAN_TEST, ScriptedBrain, done
from tests.conftest import add_account, another_browser
from tests.pentest_helpers import make
from tests.test_agents_api import Agents, base, install, running, start, wait_for
from tests.test_agents_api import settled as mission_settled
from tests.test_pentest_gate import authorized, move

from app.agents.prompts import BUILTIN
from app.db.events import connection_string

ROOT = "/api/agents"
TEXT = "You are a careful tester. Work one test at a time and cite every step you rely on."


@pytest.fixture
def agents(admin: TestClient) -> Iterator[Agents]:
    installed = install(admin, ScriptedBrain())
    yield installed
    admin.portal.call(installed.supervisor.stop)  # type: ignore[union-attr]


def actions(database_url: str) -> list[str]:
    with psycopg.connect(connection_string(database_url)) as connection:
        return [
            row[0]
            for row in connection.execute(
                "SELECT action FROM audit_event WHERE action LIKE 'agents.%' ORDER BY id"
            )
        ]


def node(tree: dict[str, Any], ref: str) -> dict[str, Any]:
    for category in tree["children"]:
        if category["id"] == ref:
            return category
        for test in category["children"]:
            if test["id"] == ref:
                return test
    raise AssertionError(ref)


# ---------------------------------------------------------------------------- the hierarchy


def test_the_hierarchy_lists_every_agent_with_nothing_run_yet(admin: TestClient) -> None:
    found = admin.get(f"{ROOT}/overview").json()
    assert found["methodology_id"] == "wstg"
    assert [one["id"] for one in found["methodologies"]] == ["wstg"]
    assert found["runner_ready"] is False
    tree = found["commander"]
    assert (tree["kind"], tree["stats"]["runs"], tree["stats"]["success_rate"]) == (
        "commander",
        0,
        None,
    )
    assert tree["children"][0]["kind"] == "category"
    test = node(tree, SCAN_TEST)
    assert test["kind"] == "test"
    assert test["risk_class"] in ("safe", "active", "intrusive")
    assert test["tools"]
    assert test["stats"]["last_run"] is None
    assert test["stats"]["active"] is False
    again = admin.get(f"{ROOT}/overview", params={"methodology": "wstg"}).json()
    assert again["commander"]["id"] == "commander"


def test_an_unknown_methodology_is_not_found_and_none_enabled_shows_an_empty_page(
    admin: TestClient,
) -> None:
    assert admin.get(f"{ROOT}/overview", params={"methodology": "nope"}).status_code == 404
    assert admin.get(f"{ROOT}/overview", params={"methodology": "Bad Id"}).status_code == 422
    assert admin.patch("/api/methodologies/wstg", json={"enabled": False}).status_code == 200
    try:
        empty = admin.get(f"{ROOT}/overview").json()
        assert (empty["methodology_id"], empty["commander"], empty["methodologies"]) == (
            None,
            None,
            [],
        )
    finally:
        assert admin.patch("/api/methodologies/wstg", json={"enabled": True}).status_code == 200


def test_the_hierarchy_shows_how_each_agent_has_done(
    admin: TestClient, agents: Agents, database_url: str
) -> None:
    made = running(admin)
    agents.brain.turns = {SCAN_TEST: [done("passed")]}
    mission = start(admin, made)
    wait_for(admin, made, mission, mission_settled)
    tree = admin.get(f"{ROOT}/overview").json()["commander"]
    ran = node(tree, SCAN_TEST)["stats"]
    assert (ran["runs"], ran["succeeded"], ran["failed"], ran["success_rate"]) == (1, 1, 0, 1.0)
    assert ran["last_run"]
    assert tree["stats"]["runs"] == 1
    with psycopg.connect(connection_string(database_url), autocommit=True) as connection:
        connection.execute(
            "UPDATE mission_task SET status = 'failed', "
            "spent = '{\"cost_usd\": 0.5}'::jsonb WHERE ref = %s",
            (SCAN_TEST,),
        )
        connection.execute(
            "UPDATE mission_task SET status = 'running' WHERE ref = %s", (HEADERS_TEST,)
        )
    tree = admin.get(f"{ROOT}/overview").json()["commander"]
    failed = node(tree, SCAN_TEST)["stats"]
    assert (failed["runs"], failed["failed"], failed["success_rate"]) == (1, 1, 0.0)
    assert failed["cost_per_run_usd"] == 0.5
    assert node(tree, HEADERS_TEST)["stats"]["active"] is True
    assert node(tree, HEADERS_TEST)["stats"]["runs"] == 0


# ---------------------------------------------------------------------------- the settings


def test_the_settings_start_from_the_built_in_caps_and_three_presets(admin: TestClient) -> None:
    found = admin.get(f"{ROOT}/settings").json()
    assert found["budget"] == found["built_in_budget"]
    assert [one["id"] for one in found["presets"]] == ["passive-recon", "safe-full", "deep-dive"]
    passive, safe, deep = found["presets"]
    assert (passive["max_risk"], safe["max_risk"], deep["max_risk"]) == (
        "safe",
        "active",
        "intrusive",
    )
    assert passive["budget"]["steps_per_test"] == 6
    assert safe["budget"] == found["budget"]
    assert deep["budget"]["steps_per_test"] == 25
    assert [one["agent"] for one in found["prompts"]] == ["test-agent", "verifier"]
    first = found["prompts"][0]
    assert (first["active"], [one["version"] for one in first["versions"]]) == (0, [0])
    assert first["versions"][0]["note"] == "Built in"
    assert found["max_prompt"] > 1000


def test_an_administrator_changes_the_caps_and_it_is_audited(
    admin: TestClient, database_url: str
) -> None:
    caps = admin.get(f"{ROOT}/settings").json()["budget"] | {"steps": 120, "concurrency": 4}
    saved = admin.put(f"{ROOT}/settings/budget", json=caps)
    assert saved.status_code == 200
    found = admin.get(f"{ROOT}/settings").json()
    assert (found["budget"]["steps"], found["budget"]["concurrency"]) == (120, 4)
    assert found["built_in_budget"]["steps"] == 300
    assert found["presets"][1]["budget"]["steps"] == 120  # presets build on the defaults
    assert admin.put(f"{ROOT}/settings/budget", json=caps | {"steps": 0}).status_code == 422
    assert admin.put(f"{ROOT}/settings/budget", json=caps | {"extra": 1}).status_code == 422
    assert actions(database_url) == ["agents.budget"]
    with psycopg.connect(connection_string(database_url)) as connection:
        detail = connection.execute(
            "SELECT detail FROM audit_event WHERE action = 'agents.budget'"
        ).fetchone()
    assert detail is not None
    assert detail[0]["changed"] == {"steps": 120, "concurrency": 4}


def test_caps_that_no_longer_fit_fall_back_to_the_built_in_ones(
    admin: TestClient, database_url: str
) -> None:
    with psycopg.connect(connection_string(database_url), autocommit=True) as connection:
        connection.execute(
            "INSERT INTO app_setting (key, value) VALUES ('agents.budget', '{\"steps\": -1}')"
        )
    assert admin.get(f"{ROOT}/settings").json()["budget"]["steps"] == 300


def test_only_an_administrator_changes_settings_and_prompts(
    admin: TestClient, database_url: str
) -> None:
    add_account(admin, "vic")
    viewer = another_browser(admin, "vic")
    caps = admin.get(f"{ROOT}/settings").json()["budget"]
    assert viewer.get(f"{ROOT}/settings").status_code == 200
    assert viewer.get(f"{ROOT}/overview").status_code == 200
    assert viewer.put(f"{ROOT}/settings/budget", json=caps).status_code == 403
    assert viewer.post(f"{ROOT}/prompts/test-agent", json={"body": TEXT}).status_code == 403
    assert (
        viewer.post(f"{ROOT}/prompts/test-agent/activate", json={"version": 0}).status_code == 403
    )
    assert viewer.get(f"{ROOT}/prompts/test-agent/0").status_code == 200


# ---------------------------------------------------------------------------- the prompts


def test_a_prompt_gets_a_new_version_that_is_never_edited(
    admin: TestClient, database_url: str
) -> None:
    added = admin.post(f"{ROOT}/prompts/test-agent", json={"body": TEXT, "note": "Shorter"})
    assert added.status_code == 201
    assert added.json()["active"] == 1
    versions = added.json()["versions"]
    assert [(one["version"], one["active"]) for one in versions] == [(0, False), (1, True)]
    assert (versions[1]["note"], versions[1]["created_by"]) == ("Shorter", "admin")
    second = admin.post(
        f"{ROOT}/prompts/test-agent", json={"body": TEXT + " Again.", "activate": False}
    )
    assert second.json()["active"] == 1  # added, but not chosen
    assert [one["version"] for one in second.json()["versions"]] == [0, 1, 2]
    text = admin.get(f"{ROOT}/prompts/test-agent/1").json()
    assert (text["body"], text["note"], text["version"]) == (TEXT, "Shorter", 1)
    builtin = admin.get(f"{ROOT}/prompts/test-agent/0").json()
    assert builtin["body"] == BUILTIN["test-agent"]
    assert actions(database_url) == [
        "agents.prompt_add",
        "agents.prompt_activate",
        "agents.prompt_add",
    ]
    # The verifier's prompt has its own numbering.
    other = admin.post(f"{ROOT}/prompts/verifier", json={"body": TEXT})
    assert [one["version"] for one in other.json()["versions"]] == [0, 1]


def test_a_version_can_be_chosen_and_the_built_in_one_put_back(
    admin: TestClient, database_url: str
) -> None:
    admin.post(f"{ROOT}/prompts/test-agent", json={"body": TEXT})
    admin.post(f"{ROOT}/prompts/test-agent", json={"body": TEXT + " Second."})
    back = admin.post(f"{ROOT}/prompts/test-agent/activate", json={"version": 1})
    assert back.json()["active"] == 1
    reset = admin.post(f"{ROOT}/prompts/test-agent/activate", json={"version": 0})
    assert (reset.json()["active"], reset.json()["versions"][0]["active"]) == (0, True)
    assert admin.post(f"{ROOT}/prompts/test-agent/activate", json={"version": 9}).status_code == 404
    assert admin.get(f"{ROOT}/settings").json()["prompts"][0]["active"] == 0
    assert actions(database_url).count("agents.prompt_activate") == 4


def test_prompts_are_checked(admin: TestClient) -> None:
    assert admin.post(f"{ROOT}/prompts/test-agent", json={"body": "short"}).status_code == 422
    assert admin.post(f"{ROOT}/prompts/test-agent", json={"body": "x" * 20_001}).status_code == 422
    assert admin.post(f"{ROOT}/prompts/test-agent", json={"body": TEXT, "x": 1}).status_code == 422
    assert admin.post(f"{ROOT}/prompts/nobody", json={"body": TEXT}).status_code == 404
    assert admin.post(f"{ROOT}/prompts/nobody/activate", json={"version": 0}).status_code == 404
    assert admin.get(f"{ROOT}/prompts/nobody/0").status_code == 404
    assert admin.get(f"{ROOT}/prompts/test-agent/7").status_code == 404
    assert (
        admin.post(f"{ROOT}/prompts/test-agent/activate", json={"version": -1}).status_code == 422
    )


# ---------------------------------------------------------------------------- starting


def test_a_start_is_previewed_before_it_is_confirmed(admin: TestClient) -> None:
    made = running(admin)
    seen = admin.post(base(made, "/preview"), json={})
    assert seen.status_code == 200
    body = seen.json()
    assert body["runner_ready"] is False  # a preview needs no runner
    assert body["max_risk"] == "active"  # the pentest's own limit
    assert body["in_scope"]
    assert body["budget"]["steps"] == 300
    summary = body["summary"]
    assert summary["runs"] > 0
    assert summary["runs"] + summary["skipped"] == sum(
        c["runs"] + c["skipped"] for c in summary["categories"]
    )
    assert set(summary["risk"]) == {"safe", "active", "intrusive"}
    assert summary["tools"]
    assert all(one["tests"] > 0 for one in summary["skips"])
    assert body["prompts"] == {"test-agent": 0, "verifier": 0}


def test_a_preset_and_a_pick_narrow_what_a_start_runs(admin: TestClient) -> None:
    made = running(admin)
    whole = admin.post(base(made, "/preview"), json={}).json()["summary"]
    passive = admin.post(base(made, "/preview"), json={"preset": "passive-recon"}).json()
    assert passive["max_risk"] == "safe"
    assert passive["budget"]["steps_per_test"] == 6
    assert passive["summary"]["runs"] < whole["runs"]
    assert passive["summary"]["risk"]["active"] == 0
    one = admin.post(base(made, "/preview"), json={"only": [SCAN_TEST]}).json()["summary"]
    assert one["runs"] <= 1
    assert any(
        item["reason"] == "This test was not picked for this mission." for item in one["skips"]
    )
    category = whole["categories"][0]["id"]
    picked = admin.post(base(made, "/preview"), json={"only": [category]}).json()["summary"]
    assert [c["id"] for c in picked["categories"] if c["runs"] > 0] in ([category], [])
    own = {"steps": 5, "tokens": 5000, "steps_per_test": 2}
    explicit = admin.post(
        base(made, "/preview"), json={"preset": "deep-dive", "budget": own}
    ).json()
    assert explicit["budget"]["steps"] == 5  # a budget that was given is used as it is
    assert explicit["max_risk"] == "active"  # a preset cannot go past the pentest's limit
    lower = admin.post(base(made, "/preview"), json={"max_risk": "safe"}).json()
    assert lower["max_risk"] == "safe"
    assert (
        admin.post(base(made, "/preview"), json={"preset": "nope"}).json()["code"]
        == "unknown_preset"
    )
    assert admin.post(base(made, "/preview"), json={"only": ["bad id"]}).status_code == 422


def test_a_pentest_limit_is_never_raised_by_a_start(admin: TestClient) -> None:
    made = authorized(admin, rules={"max_risk": "safe", "requests_per_second": 2.5})
    assert move(admin, made, "running").status_code == 200
    seen = admin.post(base(made, "/preview"), json={"preset": "deep-dive", "max_risk": "intrusive"})
    assert seen.json()["max_risk"] == "safe"
    assert seen.json()["summary"]["risk"]["active"] == 0


def test_a_preview_needs_a_running_pentest_and_an_administrator(
    admin: TestClient, database_url: str
) -> None:
    draft = make(admin)
    assert admin.post(base(draft, "/preview"), json={}).json()["code"] == "pentest_not_running"
    made = running(admin)
    add_account(admin, "vic")
    viewer = another_browser(admin, "vic")
    assert viewer.post(base(made, "/preview"), json={}).status_code == 403
    assert admin.post(f"/api/pentests/{uuid.uuid4()}/missions/preview", json={}).status_code == 404


def test_a_mission_keeps_the_prompts_it_started_with(
    admin: TestClient, agents: Agents, database_url: str
) -> None:
    admin.post(f"{ROOT}/prompts/test-agent", json={"body": TEXT})
    made = running(admin)
    mission = start(admin, made, preset="safe-full", only=[SCAN_TEST, HEADERS_TEST])
    assert mission["prompts"] == {"test-agent": 1, "verifier": 0}
    assert mission["plan"]["max_risk"] == "active"
    assert mission["plan"]["runs"] == 2
    wait_for(admin, made, mission, mission_settled)
    admin.post(f"{ROOT}/prompts/test-agent/activate", json={"version": 0})
    detail = admin.get(base(made, f"/{mission['id']}")).json()["mission"]
    assert detail["prompts"] == {"test-agent": 1, "verifier": 0}
    assert {one.brief.test_id for one in agents.brain.asked} == {SCAN_TEST, HEADERS_TEST}
    assert agents.brain.asked[0].max_risk == "active"


def test_starting_needs_the_scope_to_be_confirmed(admin: TestClient, agents: Agents) -> None:
    assert agents
    made = running(admin)
    refused = admin.post(base(made), json={"preset": "safe-full"})
    assert (refused.status_code, refused.json()["code"]) == (422, "confirm_required")
    assert admin.get(base(made)).json() == {"missions": []}
