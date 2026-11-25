"""The one question the runner asks before it starts a tool: may this call run, and does a person
have to say yes first?

Three things must all be true, and each is decided by code that no model can talk to:

1. the call is for the tool it says (the manifest decides the risk class, never the call);
2. the permission policy lets this agent role use it, on this pentest, now (`policy.py`);
3. every target is inside the pentest's scope, looked up and checked address by address
   (`guard.py`).

A tool that is active or riskier and has no target cannot be held to the scope, so it is refused.
The answer is a `Verdict` whose reason is in plain words and is kept with the run.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.netguard import Resolver, system_resolver
from app.db.models import Pentest
from app.pentests.scope import DEFAULT_METHODS, CompiledScope, ScopeError
from app.tools.argv import Call
from app.tools.control import kill_switch_on, load_grants
from app.tools.guard import check_targets
from app.tools.manifest import RISK_ORDER, ToolRisk
from app.tools.policy import ApprovalMode, Standing, decide
from app.tools.registry import Tool


@dataclass(frozen=True)
class Verdict:
    """The answer. `mode` is `auto` (run it), `ask` (a person decides first) or `deny`."""

    mode: ApprovalMode
    reason: str

    @property
    def allowed(self) -> bool:
        return self.mode is not ApprovalMode.DENY

    def record(self) -> dict[str, str]:
        """What is stored with the run."""
        return {"decision": self.mode.value, "reason": self.reason}


def _denied(reason: str) -> Verdict:
    return Verdict(ApprovalMode.DENY, reason)


def compile_stored_scope(stored: dict[str, Any]) -> CompiledScope | None:
    """A pentest's scope as stored, compiled, or None when it cannot be read."""
    try:
        return CompiledScope.compile(
            stored.get("in_scope", []),
            stored.get("out_of_scope", []),
            stored.get("excluded_paths", []),
            stored.get("methods", DEFAULT_METHODS),
        )
    except ScopeError:
        return None


async def authorize(
    session: AsyncSession,
    pentest: Pentest,
    role: str,
    tool: Tool,
    call: Call,
    *,
    resolver: Resolver = system_resolver,
) -> Verdict:
    """May `role` run `call` of `tool` on `pentest`?"""
    manifest = tool.manifest
    if call.tool != manifest.id:
        return _denied("The call is for a different tool than the one it was checked against.")
    standing = Standing(await kill_switch_on(session), pentest.id, pentest.status)
    policy = decide(
        role, manifest.id, manifest.risk, standing, await load_grants(session, pentest.id)
    )
    if not policy.allowed_at_all:
        return _denied(policy.reason)
    scope = compile_stored_scope(pentest.scope)
    if scope is None:
        return _denied("The pentest's scope cannot be read, so nothing can be checked against it.")
    if not call.targets and RISK_ORDER.index(manifest.risk) > RISK_ORDER.index(ToolRisk.PASSIVE):
        return _denied("This tool names no target, so it cannot be held to the pentest's scope.")
    inside = await check_targets(scope, call.targets, resolver)
    if not inside.allowed:
        return _denied(f"Out of scope. {inside.reason}")
    return Verdict(policy.mode, policy.reason)
