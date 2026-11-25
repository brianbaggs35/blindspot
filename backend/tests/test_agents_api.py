"""The missions API and the supervisor that keeps missions running: who may start and steer a
mission, what it needs, and how a person answers a step that waits for them."""

import asyncio
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from tests.agents_helpers import (
    SCAN_TEST,
    HeldBrain,
    Runner,
    ScriptedBrain,
    done,
    lookup,
)
from tests.conftest import add_account, another_browser, app_of
from tests.pentest_helpers import make
from tests.test_agents_engine import NMAP
from tests.test_pentest_gate import authorized, move

from app.agents.engine import MissionEngine
from app.agents.supervisor import MissionSupervisor
from app.db.events import connection_string

TERMINAL = ("completed", "cancelled", "failed")


class Agents:
    def __init__(self, brain: ScriptedBrain, runner: Runner, supervisor: MissionSupervisor) -> None:
        self.brain = brain
        self.runner = runner
        self.supervisor = supervisor


class Held(Agents):
    """Agents whose brain waits to be let go."""

    def __init__(self, brain: HeldBrain, runner: Runner, supervisor: MissionSupervisor) -> None:
        super().__init__(brain, runner, supervisor)
        self.brain: HeldBrain = brain


def install(admin: TestClient, brain: ScriptedBrain) -> Agents:
    state = app_of(admin).state
    runner = Runner()
    supervisor = MissionSupervisor(
        MissionEngine(state.database.sessions, brain, runner, resolver=lookup)
    )
    state.missions = supervisor
    return Agents(brain, runner, supervisor)


@pytest.fixture
def agents(admin: TestClient) -> Iterator[Agents]:
    """Missions that run on a scripted brain; whatever is still running is stopped after."""
    installed = install(admin, ScriptedBrain())
    yield installed
    admin.portal.call(installed.supervisor.stop)  # type: ignore[union-attr]


@pytest.fixture
def held(admin: TestClient) -> Iterator[Held]:
    """Missions whose agents wait to be let go (`held.brain.release.set()`)."""
    brain = HeldBrain()
    installed = install(admin, brain)
    yield Held(brain, installed.runner, installed.supervisor)
    admin.portal.call(installed.supervisor.stop)  # type: ignore[union-attr]


def running(admin: TestClient) -> dict[str, Any]:
    made = authorized(admin)
    assert move(admin, made, "running").status_code == 200
    return made


def base(made: dict[str, Any], tail: str = "") -> str:
    return f"/api/pentests/{made['id']}/missions{tail}"


def start(admin: TestClient, made: dict[str, Any], **body: Any) -> dict[str, Any]:
    answer = admin.post(base(made), json={"confirmed": True, **body})
    assert answer.status_code == 201, answer.text
    return answer.json()


def detail(admin: TestClient, made: dict[str, Any], mission: dict[str, Any]) -> dict[str, Any]:
    answer = admin.get(base(made, f"/{mission['id']}"))
    assert answer.status_code == 200, answer.text
    return answer.json()


def wait_for(
    admin: TestClient,
    made: dict[str, Any],
    mission: dict[str, Any],
    ready: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    found = detail(admin, made, mission)
    while time.monotonic() < deadline:
        found = detail(admin, made, mission)
        if ready(found["mission"]):
            return found
        time.sleep(0.05)
    pytest.fail(f"the mission did not get there: {found['mission']}")


def settled(found: dict[str, Any]) -> bool:
    return found["status"] in TERMINAL


def audit_actions(database_url: str) -> list[str]:
    with psycopg.connect(connection_string(database_url)) as connection:
        return [
            row[0]
            for row in connection.execute(
                "SELECT action FROM audit_event WHERE action LIKE 'mission.%' ORDER BY id"
            )
        ]


# ---------------------------------------------------------------------------- starting


def test_missions_need_a_connected_runner(admin: TestClient) -> None:
    made = running(admin)
    answer = admin.post(base(made), json={})
    assert answer.status_code == 409
    assert answer.json()["code"] == "no_runner"
    fake = f"steps/{uuid.uuid4()}"
    for tail in ("pause", "resume", "cancel", f"{fake}/approve", f"{fake}/deny"):
        again = admin.post(base(made, f"/{uuid.uuid4()}/{tail}"), json={})
        assert again.json()["code"] == "no_runner", tail
    assert admin.get(base(made)).json() == {"missions": []}  # reading never needs a runner


def test_a_mission_only_starts_on_a_running_pentest(admin: TestClient, agents: Agents) -> None:
    assert agents
    draft = make(admin)
    assert admin.post(base(draft), json={}).json()["code"] == "pentest_not_running"
    approved = authorized(admin)
    answer = admin.post(base(approved), json={})
    assert (answer.status_code, answer.json()["code"]) == (409, "pentest_not_running")
    gone = admin.post(f"/api/pentests/{uuid.uuid4()}/missions", json={})
    assert gone.status_code == 404
    archived = running(admin)
    assert admin.post(f"/api/pentests/{archived['id']}/archive").status_code in (200, 204)
    assert admin.post(base(archived), json={}).json()["code"] == "archived"


def test_a_mission_runs_to_the_end_and_everything_can_be_read(
    admin: TestClient, agents: Agents, database_url: str
) -> None:
    made = running(admin)
    agents.brain.turns = {SCAN_TEST: [done("passed", summary="Nothing to see.")]}
    mission = start(admin, made, budget={"concurrency": 8, "steps": 50})
    assert mission["status"] == "running"
    assert mission["budget"]["concurrency"] == 8
    assert mission["plan"]["runs"] > 0
    finished = wait_for(admin, made, mission, settled)
    assert finished["mission"]["status"] == "completed"
    assert finished["mission"]["finished_at"]
    kinds = [one["kind"] for one in finished["tasks"]]
    assert kinds[0] == "commander"
    assert set(kinds) == {"commander", "category", "test"}
    scan = next(one for one in finished["tasks"] if one["ref"] == SCAN_TEST)
    assert (scan["status"], scan["summary"]) == ("done", "Nothing to see.")
    assert admin.get(base(made)).json()["missions"][0]["id"] == mission["id"]
    steps = admin.get(base(made, f"/{mission['id']}/steps")).json()
    assert steps == {"steps": []}
    again = start(admin, made)  # a finished mission does not block the next
    assert again["id"] != mission["id"]
    wait_for(admin, made, again, settled)
    assert audit_actions(database_url) == ["mission.start", "mission.start"]


def test_the_log_can_be_followed_from_a_cursor(admin: TestClient, agents: Agents) -> None:
    made = running(admin)
    mission = start(admin, made)
    wait_for(admin, made, mission, settled)
    page = admin.get(base(made, f"/{mission['id']}/events"), params={"limit": 3}).json()
    assert page["events"][0]["type"] == "mission_started"
    assert len(page["events"]) == 3
    assert page["next_after"] == page["events"][-1]["id"]
    rest = admin.get(
        base(made, f"/{mission['id']}/events"), params={"after": page["next_after"], "limit": 500}
    ).json()
    assert rest["events"][-1]["type"] == "mission_completed"
    assert all(one["id"] > page["next_after"] for one in rest["events"])
    end = admin.get(
        base(made, f"/{mission['id']}/events"), params={"after": rest["next_after"]}
    ).json()
    assert end == {"events": [], "next_after": rest["next_after"]}
    assert (
        admin.get(base(made, f"/{mission['id']}/events"), params={"after": -1}).status_code == 422
    )
    assert agents


def test_a_mission_belongs_to_one_pentest(admin: TestClient, agents: Agents) -> None:
    made, other = running(admin), running(admin)
    mission = start(admin, made)
    wait_for(admin, made, mission, settled)
    for tail in ("", "/steps", "/events"):
        answer = admin.get(base(other, f"/{mission['id']}{tail}"))
        assert (answer.status_code, answer.json()["code"]) == (404, "mission_not_found"), tail
    assert admin.get(base(made, f"/{uuid.uuid4()}")).status_code == 404
    assert admin.get(f"/api/pentests/{uuid.uuid4()}/missions").status_code == 404
    assert admin.get(base(made, f"/{uuid.uuid4()}/steps")).status_code == 404
    assert agents


def test_anyone_signed_in_can_watch_but_only_an_administrator_steers(
    admin: TestClient, agents: Agents
) -> None:
    made = running(admin)
    mission = start(admin, made)
    wait_for(admin, made, mission, settled)
    add_account(admin, "vic")
    viewer = another_browser(admin, "vic")
    assert viewer.get(base(made)).status_code == 200
    assert viewer.get(base(made, f"/{mission['id']}")).status_code == 200
    assert viewer.post(base(made), json={}).status_code == 403
    for tail in ("pause", "resume", "cancel"):
        assert viewer.post(base(made, f"/{mission['id']}/{tail}"), json={}).status_code == 403
    assert agents


# ---------------------------------------------------------------------------- steering


def test_pause_resume_and_cancel(admin: TestClient, held: Held, database_url: str) -> None:
    made = running(admin)
    mission = start(admin, made)
    blocked = admin.post(base(made), json={"confirmed": True})
    assert (blocked.status_code, blocked.json()["code"]) == (409, "mission_active")
    paused = admin.post(base(made, f"/{mission['id']}/pause"))
    assert (paused.status_code, paused.json()["status"]) == (200, "paused")
    assert paused.json()["stop_reason"] == "Paused by a person."
    assert admin.post(base(made, f"/{mission['id']}/pause")).json()["code"] == "not_running"
    again = admin.post(base(made), json={"confirmed": True})
    assert again.json()["code"] == "mission_active"  # paused is not over
    plain = admin.post(base(made, f"/{mission['id']}/resume"), json={})
    assert plain.json()["budget"]["steps"] == 300  # no new caps: the old ones stay
    assert admin.post(base(made, f"/{mission['id']}/pause")).status_code == 200
    held.brain.release.set()
    time.sleep(0.5)
    assert detail(admin, made, mission)["mission"]["status"] == "paused"  # held, not finished
    resumed = admin.post(base(made, f"/{mission['id']}/resume"), json={"budget": {"steps": 77}})
    assert (resumed.status_code, resumed.json()["status"]) == (200, "running")
    assert resumed.json()["budget"]["steps"] == 77
    assert wait_for(admin, made, mission, settled)["mission"]["status"] == "completed"
    nothing = admin.post(base(made, f"/{mission['id']}/resume"), json={})
    assert (nothing.status_code, nothing.json()["code"]) == (409, "not_resumable")
    over = admin.post(base(made, f"/{mission['id']}/cancel"))
    assert (over.status_code, over.json()["code"]) == (409, "not_cancellable")
    assert audit_actions(database_url) == [
        "mission.start",
        "mission.pause",
        "mission.resume",
        "mission.pause",
        "mission.resume",
    ]


def test_cancel_while_running_ends_it_at_the_next_turn(
    admin: TestClient, held: Held, database_url: str
) -> None:
    made = running(admin)
    mission = start(admin, made)
    cancelled = admin.post(base(made, f"/{mission['id']}/cancel"))
    assert cancelled.json()["status"] == "cancelling"
    held.brain.release.set()
    done_ = wait_for(admin, made, mission, settled)
    assert done_["mission"]["status"] == "cancelled"
    assert "cancelled" in {one["status"] for one in done_["tasks"]}
    assert audit_actions(database_url) == ["mission.start", "mission.cancel"]


def test_cancel_with_nothing_running_it_closes_the_mission_at_once(
    admin: TestClient, held: Held
) -> None:
    made = running(admin)
    mission = start(admin, made)
    admin.post(base(made, f"/{mission['id']}/pause"))
    held.brain.release.set()
    time.sleep(0.5)
    admin.portal.call(held.supervisor.stop)  # type: ignore[union-attr]  # the server stops
    cancelled = admin.post(base(made, f"/{mission['id']}/cancel"))
    assert (cancelled.status_code, cancelled.json()["status"]) == (200, "cancelled")
    assert detail(admin, made, mission)["mission"]["finished_at"]


def test_resume_needs_a_running_pentest(admin: TestClient, held: Held) -> None:
    made = running(admin)
    mission = start(admin, made)
    admin.post(base(made, f"/{mission['id']}/pause"))
    assert move(admin, made, "paused").status_code == 200
    answer = admin.post(base(made, f"/{mission['id']}/resume"), json={})
    assert (answer.status_code, answer.json()["code"]) == (409, "pentest_not_running")
    held.brain.release.set()


def test_resume_rejects_caps_that_make_no_sense(admin: TestClient, held: Held) -> None:
    made = running(admin)
    mission = start(admin, made)
    admin.post(base(made, f"/{mission['id']}/pause"))
    bad = admin.post(base(made, f"/{mission['id']}/resume"), json={"budget": {"steps": 0}})
    assert bad.status_code == 422
    assert admin.post(base(made), json={"budget": {"surprise": 1}}).status_code == 422
    assert admin.post(base(made), json={}).json()["code"] == "confirm_required"
    held.brain.release.set()


# ---------------------------------------------------------------------------- approval


def test_a_step_that_waits_is_approved_by_a_person_and_runs_once(
    admin: TestClient, agents: Agents, database_url: str
) -> None:
    made = running(admin)
    agents.brain.turns = {SCAN_TEST: [NMAP, done("passed", summary="Scanned.")]}
    mission = start(admin, made)
    waiting = wait_for(admin, made, mission, lambda m: m["status"] == "paused")
    assert waiting["mission"]["stop_reason"] == "Waiting for a person to approve a step."
    asking = admin.get(
        base(made, f"/{mission['id']}/steps"), params={"status": "awaiting_approval"}
    )
    [step] = asking.json()["steps"]
    assert (step["tool"], step["verdict"]["decision"]) == ("c.nmap", "ask")
    assert step["request"]["values"] == {"targets": ["10.0.0.5"]}
    task_steps = admin.get(base(made, f"/{mission['id']}/steps"), params={"task": step["task_id"]})
    assert [one["id"] for one in task_steps.json()["steps"]] == [step["id"]]
    assert agents.runner.ran == []
    add_account(admin, "vic")
    viewer = another_browser(admin, "vic")
    assert (
        viewer.post(base(made, f"/{mission['id']}/steps/{step['id']}/approve")).status_code == 403
    )
    approved = admin.post(base(made, f"/{mission['id']}/steps/{step['id']}/approve"))
    assert (approved.status_code, approved.json()["status"]) == (200, "approved")
    assert "Approved by admin" in approved.json()["note"]
    assert wait_for(admin, made, mission, settled)["mission"]["status"] == "completed"
    assert [tool for tool, _ in agents.runner.ran] == ["c.nmap"]
    again = admin.post(base(made, f"/{mission['id']}/steps/{step['id']}/approve"))
    assert (again.status_code, again.json()["code"]) == (409, "not_waiting")
    assert audit_actions(database_url) == ["mission.start", "mission.approve"]


def test_a_step_that_is_denied_never_runs_and_the_agent_carries_on(
    admin: TestClient, agents: Agents, database_url: str
) -> None:
    made = running(admin)
    agents.brain.turns = {SCAN_TEST: [NMAP, done("blocked", summary="A person said no.")]}
    mission = start(admin, made)
    wait_for(admin, made, mission, lambda m: m["status"] == "paused")
    [step] = admin.get(
        base(made, f"/{mission['id']}/steps"), params={"status": "awaiting_approval"}
    ).json()["steps"]
    denied = admin.post(base(made, f"/{mission['id']}/steps/{step['id']}/deny"))
    assert (denied.status_code, denied.json()["status"]) == (200, "denied")
    assert wait_for(admin, made, mission, settled)["mission"]["status"] == "completed"
    assert agents.runner.ran == []
    seen = [c for c in agents.brain.asked if c.brief.test_id == SCAN_TEST][-1].history
    assert [(one.tool, one.status) for one in seen] == [("c.nmap", "denied")]
    assert audit_actions(database_url) == ["mission.start", "mission.deny"]


def test_a_step_is_found_only_through_its_own_mission(admin: TestClient, agents: Agents) -> None:
    made = running(admin)
    agents.brain.turns = {SCAN_TEST: [NMAP]}
    mission = start(admin, made)
    wait_for(admin, made, mission, lambda m: m["status"] == "paused")
    [step] = admin.get(base(made, f"/{mission['id']}/steps")).json()["steps"]
    other = running(admin)
    second = start(admin, other)
    wait_for(admin, other, second, settled)
    wrong = admin.post(base(other, f"/{second['id']}/steps/{step['id']}/approve"))
    assert (wrong.status_code, wrong.json()["code"]) == (404, "step_not_found")
    missing = admin.post(base(made, f"/{mission['id']}/steps/{uuid.uuid4()}/deny"))
    assert missing.status_code == 404
    unknown = admin.post(base(made, f"/{uuid.uuid4()}/steps/{step['id']}/approve"))
    assert (unknown.status_code, unknown.json()["code"]) == (404, "mission_not_found")


def test_approving_a_step_does_not_touch_a_mission_that_is_running_or_that_a_person_paused(
    admin: TestClient, held: Held, database_url: str
) -> None:
    made = running(admin)
    mission = start(admin, made)
    test_task = next(one for one in detail(admin, made, mission)["tasks"] if one["kind"] == "test")
    with psycopg.connect(connection_string(database_url), autocommit=True) as connection:
        for seq in (1, 2):
            connection.execute(
                "INSERT INTO mission_step (id, mission_id, task_id, seq, status, tool, request) "
                "VALUES (%s, %s, %s, %s, 'awaiting_approval', 'c.nmap', %s)",
                (uuid.uuid4(), mission["id"], test_task["id"], seq, Jsonb({"values": {}})),
            )
    first, second = admin.get(base(made, f"/{mission['id']}/steps")).json()["steps"]
    # While the mission runs, answering a step leaves its status alone.
    assert admin.post(base(made, f"/{mission['id']}/steps/{first['id']}/deny")).status_code == 200
    assert detail(admin, made, mission)["mission"]["status"] == "running"
    # A mission a person paused stays paused when a step is approved.
    admin.post(base(made, f"/{mission['id']}/pause"))
    assert (
        admin.post(base(made, f"/{mission['id']}/steps/{second['id']}/approve")).status_code == 200
    )
    assert detail(admin, made, mission)["mission"]["status"] == "paused"
    held.brain.release.set()


# ---------------------------------------------------------------------------- the supervisor


class FakeEngine:
    """Stands in for the engine: a run lasts until it is let go."""

    def __init__(self) -> None:
        self.runs: list[uuid.UUID] = []
        self.gate = asyncio.Event()
        self.recovered: list[uuid.UUID] = []

    async def run(self, mission_id: uuid.UUID) -> None:
        self.runs.append(mission_id)
        await self.gate.wait()

    async def recover(self) -> list[uuid.UUID]:
        return self.recovered


def supervisor_of(engine: FakeEngine) -> MissionSupervisor:
    return MissionSupervisor(engine)  # type: ignore[arg-type]


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_a_mission_runs_once_at_a_time_and_again_when_asked_late() -> None:
    engine = FakeEngine()
    supervisor = supervisor_of(engine)
    mission = uuid.uuid4()
    supervisor.launch(mission)
    await settle()
    assert supervisor.active(mission)
    supervisor.launch(mission)  # while it is running: remembered, not doubled
    await settle()
    assert engine.runs == [mission]
    engine.gate.set()
    await settle()
    assert engine.runs == [mission, mission]  # the late request got its own run
    await settle()
    assert not supervisor.active(mission)


async def test_a_launch_from_a_request_runs_on_the_servers_loop() -> None:
    engine = FakeEngine()
    supervisor = supervisor_of(engine)
    mission = uuid.uuid4()
    await supervisor.launch_after_response(mission)
    await settle()
    assert engine.runs == [mission]
    engine.gate.set()
    await settle()


async def test_after_a_restart_every_running_mission_carries_on_and_stop_cancels_them() -> None:
    engine = FakeEngine()
    engine.recovered = [uuid.uuid4(), uuid.uuid4()]
    supervisor = supervisor_of(engine)
    await supervisor.start()
    await settle()
    assert sorted(engine.runs) == sorted(engine.recovered)
    supervisor.launch(engine.recovered[0])  # asked again: would rerun once it ends
    await supervisor.stop()
    await settle()
    assert not any(supervisor.active(one) for one in engine.recovered)
    assert len(engine.runs) == 2  # a stopped run is not started again


async def test_stopping_with_nothing_running_is_fine() -> None:
    await supervisor_of(FakeEngine()).stop()
