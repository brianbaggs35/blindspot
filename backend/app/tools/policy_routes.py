"""The permission policy for administrators: what each agent role may do with each tool, and the
switch that stops every tool at once.

Anyone signed in can read the policy. Only administrators change it, and every change is in the
audit trail. Nothing a model writes comes through here.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.roles import AgentRole
from app.auth import audit
from app.auth.deps import Admin, SignedIn
from app.db.models import Pentest, ToolGrant
from app.db.session import SessionDep
from app.errors import AppError
from app.tools.control import KILL_SWITCH_KEY, kill_switch_on, set_kill_switch, to_grant
from app.tools.manifest import ToolRisk
from app.tools.policy import ANY, CEILING, DEFAULT_MODES, ApprovalMode
from app.tools.registry import load_registry

router = APIRouter(prefix="/api/tools/policy", tags=["tools"])

MAX_GRANTS = 500
ROLES = (ANY, *(role.value for role in AgentRole))


class GrantIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = ANY
    tool: Annotated[str, StringConstraints(pattern=r"^(\*|[a-z]\.[a-z0-9]{1,30})$")] = ANY
    max_risk: ToolRisk
    mode: ApprovalMode
    pentest_id: uuid.UUID | None = None

    @field_validator("role")
    @classmethod
    def _known_role(cls, role: str) -> str:
        if role not in ROLES:
            raise ValueError(f"role must be one of {', '.join(ROLES)}")
        return role


class GrantOut(GrantIn):
    id: uuid.UUID


class Default(BaseModel):
    risk: ToolRisk
    mode: ApprovalMode


class PolicyOut(BaseModel):
    kill_switch: bool
    defaults: list[Default]
    grants: list[GrantOut]


class KillSwitchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on: bool


def _out(row: ToolGrant) -> GrantOut:
    grant = to_grant(row)
    return GrantOut(
        id=row.id,
        role=row.role,
        tool=grant.tool,
        max_risk=grant.max_risk,
        mode=grant.mode,
        pentest_id=grant.pentest_id,
    )


async def _rows(session: AsyncSession) -> list[ToolGrant]:
    return list((await session.scalars(select(ToolGrant).order_by(ToolGrant.created_at))).all())


@router.get("")
async def read_policy(_who: SignedIn, session: SessionDep) -> PolicyOut:
    """The kill switch, what happens with no rule, and every rule."""
    return PolicyOut(
        kill_switch=await kill_switch_on(session),
        defaults=[Default(risk=risk, mode=mode) for risk, mode in DEFAULT_MODES.items()],
        grants=[_out(row) for row in await _rows(session)],
    )


async def _check_grant(session: AsyncSession, body: GrantIn) -> None:
    if body.max_risk is ToolRisk.DESTRUCTIVE and body.mode is not ApprovalMode.DENY:
        raise AppError(422, "grant_destructive", "Destructive tools cannot be allowed")
    ceiling = CEILING.get(body.max_risk)
    if ceiling is not None and body.mode is ApprovalMode.AUTO and ceiling is not ApprovalMode.AUTO:
        raise AppError(
            422, "grant_needs_a_person", "Intrusive tools always need a person to say yes"
        )
    if body.tool != ANY and (await load_registry(session)).get(body.tool) is None:
        raise AppError(404, "tool_not_found", "There is no such tool")
    if body.pentest_id is not None and await session.get(Pentest, body.pentest_id) is None:
        raise AppError(404, "pentest_not_found", "There is no such pentest")


@router.put("/grants")
async def set_grant(body: GrantIn, request: Request, who: Admin, session: SessionDep) -> GrantOut:
    """Make a rule, or change the one for the same role, tool and pentest."""
    await _check_grant(session, body)
    existing = await session.scalar(
        select(ToolGrant).where(
            ToolGrant.role == body.role,
            ToolGrant.tool == body.tool,
            ToolGrant.pentest_id.is_(None)
            if body.pentest_id is None
            else ToolGrant.pentest_id == body.pentest_id,
        )
    )
    if existing is None:
        if len(await _rows(session)) >= MAX_GRANTS:
            raise AppError(409, "too_many_grants", f"At most {MAX_GRANTS} rules")
        existing = ToolGrant(
            role=body.role,
            tool=body.tool,
            max_risk=body.max_risk.value,
            mode=body.mode.value,
            pentest_id=body.pentest_id,
            created_by=who.user.id,
        )
        session.add(existing)
    else:
        existing.max_risk = body.max_risk.value
        existing.mode = body.mode.value
    audit.record(
        session,
        request,
        "tool.policy.grant",
        actor=who.user,
        target=("tool", body.tool),
        detail={
            "role": body.role,
            "max_risk": body.max_risk.value,
            "mode": body.mode.value,
            "pentest_id": str(body.pentest_id) if body.pentest_id else None,
        },
    )
    try:
        await session.flush()
    except IntegrityError:
        raise AppError(409, "grant_exists", "Another change made that rule first") from None
    return _out(existing)


@router.delete("/grants/{grant_id}", status_code=204)
async def delete_grant(
    grant_id: uuid.UUID, request: Request, who: Admin, session: SessionDep
) -> Response:
    """Remove a rule."""
    row = await session.get(ToolGrant, grant_id)
    if row is None:
        raise AppError(404, "grant_not_found", "There is no such rule")
    await session.delete(row)
    audit.record(session, request, "tool.policy.revoke", actor=who.user, target=("tool", row.tool))
    return Response(status_code=204)


@router.put("/kill-switch")
async def kill_switch(
    body: KillSwitchIn, request: Request, who: Admin, session: SessionDep
) -> KillSwitchIn:
    """Stop every tool at once, or let them run again."""
    await set_kill_switch(session, on=body.on)
    audit.record(
        session,
        request,
        "tool.policy.kill_switch",
        actor=who.user,
        target=("setting", KILL_SWITCH_KEY),
        detail={"on": body.on},
    )
    return body
