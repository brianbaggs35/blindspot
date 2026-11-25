"""The whole check before a tool runs: policy, scope and the call itself, against a real pentest.

Each test is something an agent, or a model behind it, might try."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.pentest_helpers import SCOPE, make
from tests.test_pentest_gate import authorized, move
from tests.tools_helpers import CUSTOM, NMAP, manifest

from app.db.models import Pentest, ToolGrant, ToolSetting
from app.tools.argv import build_call
from app.tools.authorize import authorize, compile_stored_scope
from app.tools.control import load_grants, set_kill_switch
from app.tools.manifest import Manifest
from app.tools.params import ToolInputError
from app.tools.policy import ApprovalMode
from app.tools.registry import Tool, fingerprint

SHOP = "93.184.216.34"
AUTO, ASK, DENY = ApprovalMode.AUTO, ApprovalMode.ASK, ApprovalMode.DENY


async def lookup(host: str, port: int) -> list[str]:
    assert port
    return {"shop.example.com": [SHOP], "admin.shop.example.com": [SHOP]}.get(host, ["8.8.8.8"])


def tool_of(document: dict[str, Any]) -> Tool:
    tier = "custom" if document["id"].startswith("x.") else document["tier"]
    parsed = Manifest.model_validate(document | {"tier": tier})
    return Tool(parsed, "bundled", fingerprint(parsed))


HEADERS = tool_of(CUSTOM)  # passive, one target
SCANNER = tool_of(NMAP)  # active, many targets
HEADERS_NO_TARGET = tool_of(
    manifest(
        CUSTOM, id="x.noop", params={"text": {"type": "string", "required": True}}, argv=["{text}"]
    )
)
SCANNER_NO_TARGET = tool_of(
    manifest(
        NMAP,
        id="c.blind",
        params={"ports": {"type": "string", "default": "1"}},
        argv=["-p", "{ports}"],
    )
)


@pytest.fixture
async def sessions(
    admin: TestClient, database_url: str
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def pentest_row(sessions: async_sessionmaker[AsyncSession], made: dict[str, Any]) -> Pentest:
    async with sessions() as session:
        row = await session.get(Pentest, uuid.UUID(made["id"]))
        assert row is not None
        return row


def running(admin: TestClient) -> dict[str, Any]:
    made = authorized(admin)
    assert move(admin, made, "running").status_code == 200
    return made


async def verdict(
    sessions: async_sessionmaker[AsyncSession],
    made: dict[str, Any],
    tool: Tool,
    values: dict[str, Any],
    role: str = "test-agent",
) -> Any:
    row = await pentest_row(sessions, made)
    async with sessions() as session:
        return await authorize(
            session, row, role, tool, build_call(tool.manifest, values), resolver=lookup
        )


async def test_a_passive_call_on_an_in_scope_target_runs_on_its_own(
    admin: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    made = running(admin)
    answer = await verdict(sessions, made, HEADERS, {"url": "https://shop.example.com/cart"})
    assert answer.mode is AUTO
    assert answer.allowed
    assert answer.record() == {"decision": "auto", "reason": "Passive tools run on their own."}


async def test_the_tools_settings_can_switch_a_tool_off_or_hold_it_to_a_lower_risk(
    admin: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    made = running(admin)
    target = {"targets": ["10.0.0.5"]}
    async with sessions.begin() as session:
        session.add(ToolSetting(tool_id="c.nmap", enabled=False))
    off = await verdict(sessions, made, SCANNER, target)
    assert (off.mode, off.reason) == (DENY, "This tool is switched off in the Tools settings.")
    async with sessions.begin() as session:
        row = await session.get(ToolSetting, "c.nmap")
        assert row is not None
        row.enabled = True
        row.max_risk = "passive"
    held = await verdict(sessions, made, SCANNER, target)
    assert held.mode is DENY
    assert held.reason == "This tool is limited to passive actions in the Tools settings."
    async with sessions.begin() as session:
        row = await session.get(ToolSetting, "c.nmap")
        assert row is not None
        row.max_risk = "active"
    assert (await verdict(sessions, made, SCANNER, target)).allowed
    # Settings of another tool change nothing here.
    async with sessions.begin() as session:
        session.add(ToolSetting(tool_id="x.headers", enabled=False))
    assert (await verdict(sessions, made, SCANNER, target)).allowed


async def test_an_active_call_on_a_range_in_scope_asks_a_person(
    admin: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    made = running(admin)
    answer = await verdict(sessions, made, SCANNER, {"targets": ["10.0.0.0/25", "10.0.0.9"]})
    assert answer.mode is ASK
    assert answer.allowed


async def test_a_target_out_of_scope_is_denied_at_the_guard(
    admin: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    made = running(admin)
    for target in [
        "https://evil.example.org/",
        "https://admin.shop.example.com/",  # named out of scope
        "https://shop.example.com/billing/pay",  # an excluded path
        "http://127.0.0.1:8000/",  # the app itself
        "http://169.254.169.254/latest/meta-data",  # cloud metadata
    ]:
        answer = await verdict(sessions, made, HEADERS, {"url": target})
        assert answer.mode is DENY, target
        assert answer.reason.startswith("Out of scope. "), target


async def test_one_bad_target_among_good_ones_denies_the_call(
    admin: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    made = running(admin)
    answer = await verdict(sessions, made, SCANNER, {"targets": ["10.0.0.5", "10.0.1.5"]})
    assert answer.mode is DENY
    assert "10.0.1.5" in answer.reason


async def test_a_model_cannot_widen_the_scope_through_the_values_it_gives(
    admin: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    made = running(admin)
    # A user name is refused while the call is built, before the guard is asked.
    with pytest.raises(ToolInputError, match="no user name"):
        build_call(HEADERS.manifest, {"url": "https://shop.example.com@evil.example.org/"})
    for hostile in [
        {"url": "https://evil.example.org/#https://shop.example.com/"},
        {"url": "https://shop.example.com.evil.example.org/"},
        {"url": "https://evil.example.org/?next=https://shop.example.com/"},
    ]:
        answer = await verdict(sessions, made, HEADERS, hostile)
        assert answer.mode is DENY, hostile


async def test_a_model_cannot_name_a_different_tool_or_risk_than_the_one_checked(
    admin: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    made = running(admin)
    row = await pentest_row(sessions, made)
    call = build_call(SCANNER.manifest, {"targets": ["10.0.0.5"]})
    async with sessions() as session:
        # The call was built for the scanner; it is presented as the passive header tool.
        answer = await authorize(session, row, "test-agent", HEADERS, call, resolver=lookup)
    assert answer.mode is DENY
    assert "different tool" in answer.reason
    # The risk comes from the manifest: the same call is "active" however it is named.
    async with sessions() as session:
        honest = await authorize(session, row, "test-agent", SCANNER, call, resolver=lookup)
    assert honest.mode is ASK


async def test_a_model_cannot_skip_an_approval_or_give_itself_a_tool(
    admin: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    made = running(admin)
    # Nothing in a call can carry a rule: unknown values are refused while the call is built.
    with pytest.raises(ToolInputError, match="not a parameter"):
        build_call(SCANNER.manifest, {"targets": ["10.0.0.5"], "approve": True, "mode": "auto"})
    # And with no rule stored, an active tool asks.
    answer = await verdict(sessions, made, SCANNER, {"targets": ["10.0.0.5"]})
    assert answer.mode is ASK


async def test_a_call_to_an_active_tool_with_no_target_is_denied(
    admin: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    made = running(admin)
    answer = await verdict(sessions, made, SCANNER_NO_TARGET, {})
    assert answer.mode is DENY
    assert "names no target" in answer.reason
    # A passive tool that touches nothing may run.
    assert (await verdict(sessions, made, HEADERS_NO_TARGET, {"text": "hello"})).mode is AUTO


async def test_a_pentest_that_is_not_running_runs_no_tools(
    admin: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    draft = make(admin)
    answer = await verdict(sessions, draft, HEADERS, {"url": "https://shop.example.com/"})
    assert answer.mode is DENY
    assert "authorized" in answer.reason
    made = running(admin)
    assert move(admin, made, "paused").status_code == 200
    paused = await verdict(sessions, made, HEADERS, {"url": "https://shop.example.com/"})
    assert paused.mode is DENY
    assert paused.reason == "This pentest is paused."


async def test_the_kill_switch_stops_a_call_that_would_otherwise_run(
    admin: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    made = running(admin)
    async with sessions.begin() as session:
        await set_kill_switch(session, on=True)
    stopped = await verdict(sessions, made, HEADERS, {"url": "https://shop.example.com/"})
    assert stopped.mode is DENY
    assert "switched off" in stopped.reason
    async with sessions.begin() as session:
        await set_kill_switch(session, on=False)
    assert (
        await verdict(sessions, made, HEADERS, {"url": "https://shop.example.com/"})
    ).mode is AUTO


async def test_a_stored_rule_changes_the_answer_but_never_the_scope(
    admin: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    made = running(admin)
    async with sessions.begin() as session:
        session.add(ToolGrant(role="test-agent", tool="c.nmap", max_risk="active", mode="auto"))
    allowed = await verdict(sessions, made, SCANNER, {"targets": ["10.0.0.5"]})
    assert allowed.mode is AUTO
    still_out = await verdict(sessions, made, SCANNER, {"targets": ["10.0.9.9"]})
    assert still_out.mode is DENY
    other_role = await verdict(sessions, made, SCANNER, {"targets": ["10.0.0.5"]}, role="chat")
    assert other_role.mode is ASK


async def test_a_scope_that_cannot_be_read_denies_everything(
    admin: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    made = running(admin)
    row = await pentest_row(sessions, made)
    row.scope = {"in_scope": ["10.0.0.0/8"]}  # wider than a scope may be
    async with sessions() as session:
        answer = await authorize(
            session,
            row,
            "chat",
            HEADERS,
            build_call(HEADERS.manifest, {"url": "https://shop.example.com/"}),
            resolver=lookup,
        )
    assert answer.mode is DENY
    assert "cannot be read" in answer.reason


def test_a_stored_scope_is_compiled_with_its_defaults() -> None:
    compiled = compile_stored_scope({"in_scope": SCOPE["in_scope"]})
    assert compiled is not None
    assert compiled.methods == ("GET", "HEAD", "OPTIONS")
    assert compile_stored_scope({}) is not None
    assert compile_stored_scope({"in_scope": ["10.0.0.0/8"]}) is None


async def test_the_rules_can_be_read_for_one_pentest_or_for_all(
    admin: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    mine, other = running(admin), authorized(admin, name="Another")
    async with sessions.begin() as session:
        session.add_all(
            [
                ToolGrant(role="*", tool="*", max_risk="passive", mode="auto"),
                ToolGrant(
                    role="chat",
                    tool="*",
                    max_risk="passive",
                    mode="deny",
                    pentest_id=uuid.UUID(mine["id"]),
                ),
                ToolGrant(
                    role="chat",
                    tool="*",
                    max_risk="active",
                    mode="deny",
                    pentest_id=uuid.UUID(other["id"]),
                ),
            ]
        )
    async with sessions() as session:
        everything = await load_grants(session)
        for_mine = await load_grants(session, uuid.UUID(mine["id"]))
    assert len(everything) == 3
    assert [(g.max_risk.value, g.mode.value) for g in for_mine] == [
        ("passive", "auto"),
        ("passive", "deny"),
    ]
