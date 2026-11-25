"""The permission policy: whether an agent may run a tool at all, and whether a person must say yes
first.

Plain code decides this, never a model. A model chooses which tool to ask for and with which
values; what the tool is (its risk class) comes from the manifest, who is asking (the agent's role)
from the runtime, and the rules from administrators. Nothing a model writes reaches the rules.

Without any rule: passive tools run on their own, active tools ask a person, intrusive tools always
ask and destructive tools are off. A rule (a grant) is for an agent role, a tool, up to a risk
class, and for one pentest or all of them. A rule can make a tool run on its own, ask first or be
denied, but it can never skip the ask for an intrusive tool or turn a destructive tool on. Stronger
than any rule: an administrator's kill switch stops every tool, and a pentest that is not
authorized or running, or is paused, runs none.

Each answer comes with a reason in plain words, kept with the run.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.tools.manifest import RISK_ORDER, ToolRisk

ANY = "*"


class ApprovalMode(StrEnum):
    """What happens when an agent asks to run a tool."""

    AUTO = "auto"
    ASK = "ask"
    DENY = "deny"


DEFAULT_MODES: dict[ToolRisk, ApprovalMode] = {
    ToolRisk.PASSIVE: ApprovalMode.AUTO,
    ToolRisk.ACTIVE: ApprovalMode.ASK,
    ToolRisk.INTRUSIVE: ApprovalMode.ASK,
    ToolRisk.DESTRUCTIVE: ApprovalMode.DENY,
}
# The most a rule may allow for each risk class that a rule can act on (a destructive tool is
# never allowed, so it is not here).
CEILING: dict[ToolRisk, ApprovalMode] = {
    ToolRisk.PASSIVE: ApprovalMode.AUTO,
    ToolRisk.ACTIVE: ApprovalMode.AUTO,
    ToolRisk.INTRUSIVE: ApprovalMode.ASK,
}
# From the most open answer to the most closed.
_OPENNESS = (ApprovalMode.AUTO, ApprovalMode.ASK, ApprovalMode.DENY)
# Pentests that tools may run for.
RUNNABLE = frozenset({"authorized", "running"})


@dataclass(frozen=True)
class Grant:
    """One rule. `role` and `tool` are `ANY` for every role or tool; `pentest_id` is None for every
    pentest. It covers tools up to `max_risk`."""

    role: str
    tool: str
    max_risk: ToolRisk
    mode: ApprovalMode
    pentest_id: uuid.UUID | None = None

    def applies(self, role: str, tool: str, pentest_id: uuid.UUID) -> bool:
        return (
            self.role in (ANY, role)
            and self.tool in (ANY, tool)
            and self.pentest_id in (None, pentest_id)
        )

    def covers(self, risk: ToolRisk) -> bool:
        return RISK_ORDER.index(risk) <= RISK_ORDER.index(self.max_risk)

    def specificity(self) -> int:
        """A rule for one tool beats one for a role, which beats one for every pentest."""
        return (
            (4 if self.tool != ANY else 0)
            + (2 if self.role != ANY else 0)
            + (1 if self.pentest_id is not None else 0)
        )

    def describe(self) -> str:
        who = "any agent" if self.role == ANY else f"the {self.role}"
        what = "any tool" if self.tool == ANY else self.tool
        return f"An administrator's rule says {who} may use {what} ({self.mode.value})"


@dataclass(frozen=True)
class Standing:
    """What the policy needs to know about the world, none of it from a model."""

    kill_switch: bool
    pentest_id: uuid.UUID
    pentest_status: str


@dataclass(frozen=True)
class PolicyDecision:
    """The mode, and why."""

    mode: ApprovalMode
    reason: str

    @property
    def allowed_at_all(self) -> bool:
        return self.mode is not ApprovalMode.DENY


def _stopped(standing: Standing) -> str | None:
    """Why no tool may run at all, or None."""
    if standing.kill_switch:
        return "An administrator has switched off every tool."
    if standing.pentest_status == "paused":
        return "This pentest is paused."
    if standing.pentest_status not in RUNNABLE:
        return "Tools run only once the pentest is authorized."
    return None


def _clamp(mode: ApprovalMode, risk: ToolRisk) -> ApprovalMode:
    """No more open than the risk class allows."""
    ceiling = CEILING[risk]
    return ceiling if _OPENNESS.index(mode) < _OPENNESS.index(ceiling) else mode


def _default(risk: ToolRisk) -> PolicyDecision:
    mode = DEFAULT_MODES[risk]
    if mode is ApprovalMode.AUTO:
        return PolicyDecision(mode, f"{risk.value.capitalize()} tools run on their own.")
    if mode is ApprovalMode.ASK:
        return PolicyDecision(mode, f"{risk.value.capitalize()} tools need a person to say yes.")
    return PolicyDecision(mode, "Destructive tools are off and cannot be turned on.")


def decide(
    role: str, tool: str, risk: ToolRisk, standing: Standing, grants: list[Grant]
) -> PolicyDecision:
    """May this role run this tool, and must a person say yes first?"""
    if (why := _stopped(standing)) is not None:
        return PolicyDecision(ApprovalMode.DENY, why)
    if risk is ToolRisk.DESTRUCTIVE:
        return _default(risk)
    found = [
        grant
        for grant in grants
        if grant.applies(role, tool, standing.pentest_id) and grant.covers(risk)
    ]
    if denied := [grant for grant in found if grant.mode is ApprovalMode.DENY]:
        return PolicyDecision(ApprovalMode.DENY, f"{denied[0].describe()}.")
    if not found:
        return _default(risk)
    chosen = max(found, key=Grant.specificity)
    mode = _clamp(chosen.mode, risk)
    if mode is not chosen.mode:
        return PolicyDecision(
            mode, f"{risk.value.capitalize()} tools always need a person to say yes."
        )
    return PolicyDecision(mode, f"{chosen.describe()}.")
