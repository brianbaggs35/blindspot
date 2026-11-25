"""The permission policy: defaults, rules, and what no rule can change."""

import uuid

import pytest

from app.tools.manifest import ToolRisk
from app.tools.policy import ANY, ApprovalMode, Grant, Standing, decide

PENTEST = uuid.uuid4()
OTHER_PENTEST = uuid.uuid4()
RUNNING = Standing(kill_switch=False, pentest_id=PENTEST, pentest_status="running")
AUTO, ASK, DENY = ApprovalMode.AUTO, ApprovalMode.ASK, ApprovalMode.DENY


def grant(
    mode: ApprovalMode,
    max_risk: ToolRisk = ToolRisk.INTRUSIVE,
    *,
    role: str = ANY,
    tool: str = ANY,
    pentest_id: uuid.UUID | None = None,
) -> Grant:
    return Grant(role, tool, max_risk, mode, pentest_id)


@pytest.mark.parametrize(
    ("risk", "mode"),
    [
        (ToolRisk.PASSIVE, AUTO),
        (ToolRisk.ACTIVE, ASK),
        (ToolRisk.INTRUSIVE, ASK),
        (ToolRisk.DESTRUCTIVE, DENY),
    ],
)
def test_with_no_rule_the_defaults_apply(risk: ToolRisk, mode: ApprovalMode) -> None:
    answer = decide("test-agent", "c.nmap", risk, RUNNING, [])
    assert answer.mode is mode
    assert answer.reason.endswith(".")
    assert answer.allowed_at_all is (mode is not DENY)


def test_the_reasons_are_plain_words() -> None:
    assert decide("chat", "b.http", ToolRisk.PASSIVE, RUNNING, []).reason == (
        "Passive tools run on their own."
    )
    assert decide("chat", "b.http", ToolRisk.ACTIVE, RUNNING, []).reason == (
        "Active tools need a person to say yes."
    )
    assert "cannot be turned on" in decide("chat", "b.x", ToolRisk.DESTRUCTIVE, RUNNING, []).reason


def test_a_rule_can_let_an_active_tool_run_on_its_own_or_close_a_passive_one() -> None:
    allow = grant(AUTO, ToolRisk.ACTIVE, role="test-agent", tool="c.nmap")
    assert decide("test-agent", "c.nmap", ToolRisk.ACTIVE, RUNNING, [allow]).mode is AUTO
    assert (
        "the test-agent may use c.nmap (auto)"
        in decide("test-agent", "c.nmap", ToolRisk.ACTIVE, RUNNING, [allow]).reason
    )
    shut = grant(DENY, ToolRisk.PASSIVE, tool="b.http")
    assert decide("chat", "b.http", ToolRisk.PASSIVE, RUNNING, [shut]).mode is DENY
    assert (
        "any agent may use b.http (deny)"
        in decide("chat", "b.http", ToolRisk.PASSIVE, RUNNING, [shut]).reason
    )


def test_a_rule_does_not_reach_past_its_role_tool_or_risk() -> None:
    allow = grant(AUTO, ToolRisk.ACTIVE, role="test-agent", tool="c.nmap")
    for role, tool, risk in [
        ("chat", "c.nmap", ToolRisk.ACTIVE),
        ("test-agent", "c.other", ToolRisk.ACTIVE),
        ("test-agent", "c.nmap", ToolRisk.INTRUSIVE),
    ]:
        assert decide(role, tool, risk, RUNNING, [allow]).mode is not AUTO


def test_a_rule_for_another_pentest_does_not_apply() -> None:
    elsewhere = grant(AUTO, ToolRisk.ACTIVE, pentest_id=OTHER_PENTEST)
    assert decide("chat", "c.nmap", ToolRisk.ACTIVE, RUNNING, [elsewhere]).mode is ASK
    here = grant(AUTO, ToolRisk.ACTIVE, pentest_id=PENTEST)
    assert decide("chat", "c.nmap", ToolRisk.ACTIVE, RUNNING, [here]).mode is AUTO


def test_an_intrusive_tool_always_needs_a_person_whatever_the_rule_says() -> None:
    for allow in (grant(AUTO), grant(AUTO, tool="c.sqlmap", role="test-agent", pentest_id=PENTEST)):
        answer = decide("test-agent", "c.sqlmap", ToolRisk.INTRUSIVE, RUNNING, [allow])
        assert answer.mode is ASK
        assert "always need a person" in answer.reason
    assert decide("chat", "c.x", ToolRisk.INTRUSIVE, RUNNING, [grant(ASK)]).mode is ASK


def test_a_destructive_tool_cannot_be_turned_on_by_any_rule() -> None:
    every = [grant(AUTO, ToolRisk.DESTRUCTIVE), grant(ASK, ToolRisk.DESTRUCTIVE, tool="c.wipe")]
    answer = decide("commander", "c.wipe", ToolRisk.DESTRUCTIVE, RUNNING, every)
    assert answer.mode is DENY


def test_the_most_specific_rule_wins() -> None:
    broad = grant(ASK, ToolRisk.ACTIVE)
    by_role = grant(AUTO, ToolRisk.ACTIVE, role="test-agent")
    by_tool = grant(ASK, ToolRisk.ACTIVE, tool="c.nmap")
    by_pentest = grant(AUTO, ToolRisk.ACTIVE, pentest_id=PENTEST)
    rules = [broad, by_role, by_tool, by_pentest]
    assert decide("test-agent", "c.nmap", ToolRisk.ACTIVE, RUNNING, rules).mode is ASK
    assert decide("test-agent", "c.other", ToolRisk.ACTIVE, RUNNING, rules).mode is AUTO


def test_a_deny_rule_beats_every_allow_rule() -> None:
    rules = [
        grant(AUTO, ToolRisk.ACTIVE, role="test-agent", tool="c.nmap", pentest_id=PENTEST),
        grant(DENY, ToolRisk.ACTIVE),
    ]
    assert decide("test-agent", "c.nmap", ToolRisk.ACTIVE, RUNNING, rules).mode is DENY


@pytest.mark.parametrize("risk", [ToolRisk.PASSIVE, ToolRisk.ACTIVE, ToolRisk.DESTRUCTIVE])
def test_the_kill_switch_stops_everything(risk: ToolRisk) -> None:
    standing = Standing(kill_switch=True, pentest_id=PENTEST, pentest_status="running")
    answer = decide("chat", "b.http", risk, standing, [grant(AUTO, ToolRisk.ACTIVE)])
    assert answer.mode is DENY
    assert "switched off every tool" in answer.reason


@pytest.mark.parametrize("status", ["draft", "complete", "paused"])
def test_tools_run_only_in_a_pentest_that_is_authorized_or_running(status: str) -> None:
    standing = Standing(kill_switch=False, pentest_id=PENTEST, pentest_status=status)
    answer = decide("chat", "b.http", ToolRisk.PASSIVE, standing, [grant(AUTO)])
    assert answer.mode is DENY
    assert ("paused" if status == "paused" else "authorized") in answer.reason
    authorized = Standing(kill_switch=False, pentest_id=PENTEST, pentest_status="authorized")
    assert decide("chat", "b.http", ToolRisk.PASSIVE, authorized, []).mode is AUTO
