"""Tools: list them, read a manifest, and (for administrators) see the exact command a set of
values would make and define, change and remove custom tools.

Anyone signed in can read. Everything else needs an administrator, goes through the same checks
as a bundled manifest, and a change is in the audit trail. Nothing here runs a tool.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import audit
from app.auth.deps import Admin, SignedIn
from app.db.models import CustomTool
from app.db.session import SessionDep
from app.errors import AppError
from app.methodology.spec import ToolId
from app.tools.argv import build_call
from app.tools.manifest import Manifest, Tier
from app.tools.params import ToolInputError
from app.tools.registry import Tool, fingerprint, load_registry

router = APIRouter(prefix="/api", tags=["tools"])

MAX_CUSTOM_TOOLS = 100


class ToolSummary(BaseModel):
    id: str
    name: str
    tier: str
    origin: str
    execution: str
    risk: str
    capabilities: list[str]
    explain: str


class ToolDetail(ToolSummary):
    fingerprint: str
    targets: list[str]
    manifest: Manifest


class PreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, Any] = Field(default_factory=dict)


class Preview(BaseModel):
    argv: list[str]
    targets: list[str]


def _summary(tool: Tool) -> ToolSummary:
    manifest = tool.manifest
    return ToolSummary(
        id=manifest.id,
        name=manifest.name,
        tier=manifest.tier.value,
        origin=tool.origin,
        execution=manifest.execution,
        risk=manifest.risk.value,
        capabilities=[capability.value for capability in manifest.capabilities],
        explain=manifest.explain,
    )


def _detail(tool: Tool) -> ToolDetail:
    return ToolDetail(
        **_summary(tool).model_dump(),
        fingerprint=tool.fingerprint,
        targets=tool.manifest.target_params(),
        manifest=tool.manifest,
    )


def _explain(error: ValidationError) -> str:
    """The first few mistakes in a manifest, in words."""
    found = [
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()
    ]
    return "; ".join(found[:5])


def _manifest_from(body: dict[str, Any]) -> Manifest:
    """A custom tool's manifest from what was sent. The tier is always custom, so it is not asked
    for."""
    try:
        return Manifest.model_validate({**body, "tier": Tier.CUSTOM.value})
    except ValidationError as error:
        raise AppError(
            422, "invalid_tool", "That tool definition is not valid", _explain(error)
        ) from None


async def _find(session: AsyncSession, tool_id: str) -> Tool:
    found = (await load_registry(session)).get(tool_id)
    if found is None:
        raise AppError(404, "tool_not_found", "There is no such tool")
    return found


async def _custom_row(session: AsyncSession, tool_id: str) -> CustomTool:
    row = await session.scalar(select(CustomTool).where(CustomTool.tool_id == tool_id))
    if row is None:
        raise AppError(404, "tool_not_found", "There is no such custom tool")
    return row


@router.get("/tools")
async def list_tools(_who: SignedIn, session: SessionDep) -> list[ToolSummary]:
    """Every tool, bundled and custom, by id."""
    return [_summary(tool) for tool in (await load_registry(session)).all()]


@router.get("/tools/{tool_id}")
async def get_tool(tool_id: ToolId, _who: SignedIn, session: SessionDep) -> ToolDetail:
    """One tool with its whole manifest."""
    return _detail(await _find(session, tool_id))


@router.post("/tools/{tool_id}/preview")
async def preview(tool_id: ToolId, body: PreviewIn, _who: Admin, session: SessionDep) -> Preview:
    """The exact argument list a call would run and the targets it touches. It checks the values
    the way a run does, and runs nothing."""
    tool = await _find(session, tool_id)
    try:
        call = build_call(tool.manifest, body.values)
    except ToolInputError as error:
        raise AppError(
            422, "invalid_tool_input", "Those values do not fit the tool", str(error)
        ) from None
    return Preview(argv=list(call.argv), targets=list(call.targets))


@router.post("/tools/custom", status_code=201)
async def create_custom(
    body: Annotated[dict[str, Any], Field(max_length=40)],
    request: Request,
    who: Admin,
    session: SessionDep,
) -> ToolDetail:
    """Define a custom tool. Its id starts with `x.`."""
    manifest = _manifest_from(body)
    registry = await load_registry(session)
    if registry.get(manifest.id) is not None:
        raise AppError(409, "tool_exists", "A tool with that id already exists")
    count = await session.scalar(select(func.count()).select_from(CustomTool))
    if (count or 0) >= MAX_CUSTOM_TOOLS:
        raise AppError(409, "too_many_tools", f"At most {MAX_CUSTOM_TOOLS} custom tools")
    session.add(
        CustomTool(
            tool_id=manifest.id,
            manifest=manifest.model_dump(mode="json"),
            created_by=who.user.id,
        )
    )
    audit.record(
        session,
        request,
        "tool.custom.create",
        actor=who.user,
        target=("tool", manifest.id),
        detail=_audit_detail(manifest),
    )
    return _detail(Tool(manifest, "custom", fingerprint(manifest)))


def _audit_detail(manifest: Manifest) -> dict[str, Any]:
    return {"risk": manifest.risk.value, "binary": manifest.binary, "name": manifest.name}


@router.put("/tools/custom/{tool_id}")
async def replace_custom(
    tool_id: ToolId,
    body: Annotated[dict[str, Any], Field(max_length=40)],
    request: Request,
    who: Admin,
    session: SessionDep,
) -> ToolDetail:
    """Replace a custom tool's definition. Its id cannot change."""
    row = await _custom_row(session, tool_id)
    manifest = _manifest_from(body)
    if manifest.id != tool_id:
        raise AppError(422, "tool_id_changed", "A tool's id cannot be changed")
    row.manifest = manifest.model_dump(mode="json")
    audit.record(
        session,
        request,
        "tool.custom.update",
        actor=who.user,
        target=("tool", tool_id),
        detail=_audit_detail(manifest),
    )
    return _detail(Tool(manifest, "custom", fingerprint(manifest)))


@router.delete("/tools/custom/{tool_id}", status_code=204)
async def delete_custom(
    tool_id: ToolId, request: Request, who: Admin, session: SessionDep
) -> Response:
    """Remove a custom tool."""
    row = await _custom_row(session, tool_id)
    await session.delete(row)
    audit.record(session, request, "tool.custom.delete", actor=who.user, target=("tool", tool_id))
    return Response(status_code=204)
