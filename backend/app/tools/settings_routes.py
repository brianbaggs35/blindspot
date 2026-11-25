"""The Tools settings: how each tool is run, and a button that checks one.

Anyone signed in can read. Changing a setting and testing a tool need an administrator, and a
change is in the audit trail. Reading never runs a program; Test runs one tool's version check
(the arguments of its manifest, as a list, never through a shell) when its mode is Local.
"""

import asyncio
import os
import re
import time
from decimal import Decimal
from typing import Annotated, Literal, Self

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import audit
from app.auth.deps import Admin, SignedIn
from app.db.models import ToolSetting
from app.db.session import SessionDep
from app.errors import AppError
from app.methodology.spec import Strict, ToolId
from app.redact import redact
from app.tools.manifest import INTERPRETERS, RISK_ORDER, SHELLS, Binary, Image, Manifest, ToolRisk
from app.tools.registry import Tool, load_registry
from app.tools.settings import (
    DockerState,
    Limits,
    Probe,
    Resolution,
    RunMode,
    Status,
    SystemProbe,
    Where,
    binary_of,
    image_of,
    limits_of,
    resolve,
    run_mode,
    set_run_mode,
    settings_by_tool,
)

router = APIRouter(prefix="/api/tools/settings", tags=["tools"])

TEST_SECONDS = 10
TEST_OUTPUT = 4000
_SAFE_ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C"}


def get_probe() -> Probe:
    """What the machine has. Tests replace this."""
    return SystemProbe()


ProbeDep = Annotated[Probe, Depends(get_probe)]


class GlobalIn(Strict):
    mode: RunMode


class SettingIn(Strict):
    """Everything an administrator can set for one tool. What is left empty is the manifest's."""

    enabled: bool = True
    mode: Literal["local", "docker"] | None = None
    binary_path: Binary | None = None
    image: Image | None = None
    cpus: Annotated[Decimal, Field(ge=Decimal("0.1"), le=64, decimal_places=2)] | None = None
    memory_mb: Annotated[int, Field(ge=16, le=1_048_576)] | None = None
    timeout_s: Annotated[int, Field(ge=1, le=86_400)] | None = None
    max_output_mb: Annotated[int, Field(ge=1, le=512)] | None = None
    rate_per_s: Annotated[int, Field(ge=1, le=10_000)] | None = None
    max_risk: ToolRisk | None = None

    @field_validator("binary_path")
    @classmethod
    def _plain_program(cls, path: str | None) -> str | None:
        if path is None:
            return None
        name = path.rsplit("/", 1)[-1]
        if ".." in path.split("/") or name.lower() in SHELLS or INTERPRETERS.match(name.lower()):
            raise ValueError("that cannot be a tool: no shells or interpreters, and no '..'")
        return path

    @model_validator(mode="after")
    def _one_way(self) -> Self:
        if self.mode == "docker" and self.binary_path:
            raise ValueError("a program path is for Local, so it cannot be set with Docker")
        if self.mode == "local" and self.image:
            raise ValueError("an image is for Docker, so it cannot be set with Local")
        return self


class ResolutionOut(BaseModel):
    mode: Where | None
    status: Status
    problem: str
    fell_back: bool
    offer: Where | None
    path: str | None


class LimitsOut(BaseModel):
    cpus: float | None
    memory_mb: int | None
    timeout_s: int
    max_output_mb: int
    rate_per_s: int | None
    max_risk: ToolRisk


class ToolSettingOut(BaseModel):
    id: str
    name: str
    tier: str
    origin: str
    execution: str
    risk: ToolRisk
    explain: str
    enabled: bool
    mode: Literal["local", "docker"] | None
    binary_path: str | None
    image: str | None
    default_binary: str | None
    default_image: str | None
    limits: LimitsOut
    overrides: SettingIn
    effective: ResolutionOut


class SettingsOut(BaseModel):
    run_mode: RunMode
    docker: DockerStateOut
    tools: list[ToolSettingOut]


class DockerStateOut(BaseModel):
    reachable: bool
    note: str


class TestOut(BaseModel):
    mode: Where
    command: list[str]
    exit_code: int | None
    output: str
    duration_ms: int
    version: str | None
    timed_out: bool


SettingsOut.model_rebuild()


def _limits(limits: Limits) -> LimitsOut:
    return LimitsOut(**limits.__dict__)


def _overrides(row: ToolSetting | None) -> SettingIn:
    if row is None:
        return SettingIn()
    return SettingIn.model_construct(
        enabled=row.enabled,
        mode=row.mode,  # pyright: ignore[reportArgumentType]
        binary_path=row.binary_path,
        image=row.image,
        cpus=row.cpus,
        memory_mb=row.memory_mb,
        timeout_s=row.timeout_s,
        max_output_mb=row.max_output_mb,
        rate_per_s=row.rate_per_s,
        max_risk=ToolRisk(row.max_risk) if row.max_risk else None,
    )


def _out(tool: Tool, row: ToolSetting | None, default: RunMode, probe: Probe) -> ToolSettingOut:
    manifest = tool.manifest
    found: Resolution = resolve(manifest, row, default, probe)
    return ToolSettingOut(
        id=manifest.id,
        name=manifest.name,
        tier=manifest.tier.value,
        origin=tool.origin,
        execution=manifest.execution,
        risk=manifest.risk,
        explain=manifest.explain,
        enabled=row.enabled if row else True,
        mode=row.mode if row else None,  # pyright: ignore[reportArgumentType]
        binary_path=binary_of(manifest, row),
        image=image_of(manifest, row),
        default_binary=manifest.binary,
        default_image=manifest.image,
        limits=_limits(limits_of(manifest, row)),
        overrides=_overrides(row),
        effective=ResolutionOut(**found.__dict__),
    )


async def _tool(session: AsyncSession, tool_id: str) -> Tool:
    found = (await load_registry(session)).get(tool_id)
    if found is None:
        raise AppError(404, "tool_not_found", "There is no such tool")
    return found


@router.get("")
async def read_settings(_who: SignedIn, session: SessionDep, probe: ProbeDep) -> SettingsOut:
    """The default, the state of Docker and every tool with how it would run now."""
    default = await run_mode(session)
    rows = await settings_by_tool(session)
    state: DockerState = probe.docker()
    return SettingsOut(
        run_mode=default,
        docker=DockerStateOut(reachable=state.reachable, note=state.note),
        tools=[
            _out(tool, rows.get(tool.manifest.id), default, probe)
            for tool in (await load_registry(session)).all()
        ],
    )


@router.put("/default")
async def put_default(
    body: GlobalIn, request: Request, who: Admin, session: SessionDep
) -> GlobalIn:
    """Choose how tools run when a tool has no choice of its own."""
    await set_run_mode(session, body.mode)
    audit.record(
        session,
        request,
        "tool.settings.default",
        actor=who.user,
        target=("setting", "tools.run_mode"),
        detail={"mode": body.mode.value},
    )
    return body


def _check(manifest: Manifest, body: SettingIn) -> None:
    """What cannot be set on this tool."""
    if manifest.execution == "builtin" and (body.mode or body.binary_path or body.image):
        raise AppError(
            422, "builtin_tool", "A built-in tool runs inside the app, so it has no mode or image"
        )
    if body.max_risk and RISK_ORDER.index(body.max_risk) > RISK_ORDER.index(manifest.risk):
        raise AppError(
            422, "risk_above_manifest", "A tool cannot be allowed more than its manifest says"
        )


@router.put("/{tool_id}")
async def put_setting(
    tool_id: ToolId,
    body: SettingIn,
    request: Request,
    *,
    who: Admin,
    session: SessionDep,
    probe: ProbeDep,
) -> ToolSettingOut:
    """Set how one tool runs. Everything is replaced: what is left empty is the manifest's."""
    tool = await _tool(session, tool_id)
    _check(tool.manifest, body)
    row = await session.get(ToolSetting, tool_id)
    if row is None:
        row = ToolSetting(tool_id=tool_id)
        session.add(row)
    row.enabled = body.enabled
    row.mode = body.mode
    row.binary_path = body.binary_path
    row.image = body.image
    row.cpus = body.cpus
    row.memory_mb = body.memory_mb
    row.timeout_s = body.timeout_s
    row.max_output_mb = body.max_output_mb
    row.rate_per_s = body.rate_per_s
    row.max_risk = body.max_risk.value if body.max_risk else None
    row.updated_by = who.user.id
    audit.record(
        session,
        request,
        "tool.settings.update",
        actor=who.user,
        target=("tool", tool_id),
        detail=body.model_dump(mode="json", exclude_none=True),
    )
    await session.flush()
    return _out(tool, row, await run_mode(session), probe)


@router.delete("/{tool_id}", status_code=204)
async def reset_setting(
    tool_id: ToolId, request: Request, who: Admin, session: SessionDep
) -> Response:
    """Put a tool back to what its manifest and the default say."""
    await _tool(session, tool_id)
    row = await session.get(ToolSetting, tool_id)
    if row is not None:
        await session.delete(row)
    audit.record(session, request, "tool.settings.reset", actor=who.user, target=("tool", tool_id))
    return Response(status_code=204)


async def _run(path: str, args: list[str], limit: int) -> tuple[int | None, str, bool]:
    """Run one program with these arguments (no shell, no input, a bare environment) and read the
    start of what it printed. Returns the exit code, the output and whether it had to be stopped."""
    process = await asyncio.create_subprocess_exec(
        path,
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=_SAFE_ENV,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), TEST_SECONDS)
    except TimeoutError:
        process.kill()
        await process.wait()
        return None, "", True
    return process.returncode, stdout[:limit].decode("utf-8", errors="replace"), False


@router.post("/{tool_id}/test")
async def test_tool(
    tool_id: ToolId, request: Request, who: Admin, session: SessionDep, probe: ProbeDep
) -> TestOut:
    """Run the tool's version check the way a run would, and show the command, what it printed
    and how long it took. Only a Local tool that is ready can be tested; anything else says what
    is wrong and is never switched to another way."""
    tool = await _tool(session, tool_id)
    manifest = tool.manifest
    row = await session.get(ToolSetting, tool_id)
    found = resolve(manifest, row, await run_mode(session), probe)
    if found.mode is not Where.LOCAL or found.path is None:
        raise AppError(
            409,
            "cannot_test",
            "This tool cannot be tested here",
            found.problem or "Only a tool that runs Local can be tested for now.",
        )
    if manifest.version is None:
        raise AppError(409, "no_version_check", "This tool has no version check to run")
    args = list(manifest.version.args)
    started = time.monotonic()
    code, text, timed_out = await _run(found.path, args, TEST_OUTPUT)
    audit.record(
        session,
        request,
        "tool.settings.test",
        actor=who.user,
        target=("tool", tool_id),
        detail={"exit_code": code, "timed_out": timed_out},
    )
    match = re.search(manifest.version.pattern, text) if text else None
    return TestOut(
        mode=Where.LOCAL,
        command=[os.path.basename(found.path), *args],
        exit_code=code,
        output=redact(text),
        duration_ms=int((time.monotonic() - started) * 1000),
        version=match.group(1) if match else None,
        timed_out=timed_out,
    )
