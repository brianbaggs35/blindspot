"""How a tool is run: where (Local, in the container, or Docker), and under which limits.

An administrator chooses a default for every tool and can set each tool apart. The code here turns
those choices and what the machine really has into one answer for a tool: where it runs and
whether it can. Two rules hold:

- Nothing is switched silently. A tool set to Local, or the default "Docker only", that cannot run
  there is reported as not ready, with the reason and the other way offered as a choice a person
  makes. Only the defaults that say "prefer" may use the other way, and the answer says they did.
- Looking never runs anything. Finding a program is a look at the file system; a program only runs
  when an administrator presses Test.
"""

import os
import shutil
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSetting, ToolSetting
from app.tools.manifest import RISK_ORDER, Manifest, Tier, ToolRisk

RUN_MODE_KEY = "tools.run_mode"


class RunMode(StrEnum):
    """The default for every tool that has no choice of its own."""

    AUTO = "auto"
    PREFER_LOCAL = "prefer_local"
    PREFER_DOCKER = "prefer_docker"
    DOCKER_ONLY = "docker_only"


class Where(StrEnum):
    LOCAL = "local"
    DOCKER = "docker"
    BUILTIN = "builtin"


class Status(StrEnum):
    READY = "ready"
    DISABLED = "disabled"
    BINARY_NOT_FOUND = "binary_not_found"
    DOCKER_UNREACHABLE = "docker_unreachable"
    IMAGE_MISSING = "image_missing"


@dataclass(frozen=True)
class DockerState:
    """Whether Docker can be used, and if not, why in words."""

    reachable: bool
    note: str


class Probe(Protocol):
    """What the machine has. A probe only looks."""

    def locate(self, binary: str) -> str | None:
        """The path of the program, or None."""

    def docker(self) -> DockerState: ...


class SystemProbe:
    """The real machine. There is no Docker connection yet: the Docker runner is its own ticket,
    which replaces `docker()` with a real check."""

    def locate(self, binary: str) -> str | None:
        if "/" in binary:
            return binary if os.path.isfile(binary) and os.access(binary, os.X_OK) else None
        return shutil.which(binary)

    def docker(self) -> DockerState:
        return DockerState(
            False, "Blindspot is not connected to Docker; the Docker runner is not installed yet."
        )


@dataclass(frozen=True)
class Resolution:
    """Where a tool runs, whether it can, and what to say. `mode` is None when it cannot run.
    `fell_back` is set when a "prefer" default used its second choice, `offer` is the other way
    when it would work and the person has not chosen it."""

    mode: Where | None
    status: Status
    problem: str
    fell_back: bool
    offer: Where | None
    path: str | None


@dataclass(frozen=True)
class Limits:
    """What a run is held to. CPU and memory are only enforced for Docker."""

    cpus: float | None
    memory_mb: int | None
    timeout_s: int
    max_output_mb: int
    rate_per_s: int | None
    max_risk: ToolRisk


def bundled_in_image(manifest: Manifest) -> bool:
    """Whether the program comes with the image (a built-in or a core tool), or a custom tool
    that has no image to pull. Those run Local under "Auto"."""
    return manifest.tier in (Tier.BUILTIN, Tier.CORE) or manifest.image is None


def _order(manifest: Manifest, setting: ToolSetting | None, default: RunMode) -> list[Where]:
    """The ways to run a tool, best first. One entry means there is no other way to try."""
    if setting is not None and setting.mode is not None:
        return [Where(setting.mode)]
    if default is RunMode.PREFER_LOCAL:
        return [Where.LOCAL, Where.DOCKER]
    if default is RunMode.PREFER_DOCKER:
        return [Where.DOCKER, Where.LOCAL]
    if default is RunMode.DOCKER_ONLY:
        return [Where.DOCKER]
    return [Where.LOCAL] if bundled_in_image(manifest) else [Where.DOCKER]


def image_of(manifest: Manifest, setting: ToolSetting | None) -> str | None:
    return (setting.image if setting else None) or manifest.image


def binary_of(manifest: Manifest, setting: ToolSetting | None) -> str | None:
    return (setting.binary_path if setting else None) or manifest.binary


def _local(manifest: Manifest, setting: ToolSetting | None, probe: Probe) -> tuple[str | None, str]:
    """The program's path, or None with what is wrong."""
    wanted = binary_of(manifest, setting)
    found = probe.locate(wanted) if wanted else None
    return found, ("" if found else f"The program {wanted} was not found.")


def _docker(
    manifest: Manifest, setting: ToolSetting | None, probe: Probe
) -> tuple[bool, Status, str]:
    state = probe.docker()
    if not state.reachable:
        return False, Status.DOCKER_UNREACHABLE, state.note
    if image_of(manifest, setting) is None:
        return (
            False,
            Status.IMAGE_MISSING,
            "This tool has no Docker image. Set one with its digest.",
        )
    return True, Status.READY, ""


def _availability(
    manifest: Manifest, setting: ToolSetting | None, probe: Probe
) -> tuple[dict[Where, str | None], dict[Where, tuple[Status, str]]]:
    path, local_problem = _local(manifest, setting, probe)
    usable, docker_status, docker_problem = _docker(manifest, setting, probe)
    available = {Where.LOCAL: path, Where.DOCKER: "docker" if usable else None}
    problems = {
        Where.LOCAL: (Status.BINARY_NOT_FOUND, local_problem),
        Where.DOCKER: (docker_status, docker_problem),
    }
    return available, problems


def _other_available(failed: Where, available: dict[Where, str | None]) -> Where | None:
    return next(
        (
            where
            for where in (Where.LOCAL, Where.DOCKER)
            if where is not failed and available[where]
        ),
        None,
    )


def resolve(
    manifest: Manifest, setting: ToolSetting | None, default: RunMode, probe: Probe
) -> Resolution:
    """Where `manifest` runs under these choices, and whether it can."""
    if setting is not None and not setting.enabled:
        return Resolution(None, Status.DISABLED, "This tool is switched off.", False, None, None)
    if manifest.execution == "builtin":
        return Resolution(Where.BUILTIN, Status.READY, "", False, None, None)
    order = _order(manifest, setting, default)
    available, problems = _availability(manifest, setting, probe)
    for index, where in enumerate(order):
        path = available[where]
        if path is not None:
            return Resolution(
                where,
                Status.READY,
                "",
                index > 0,
                None,
                path if where is Where.LOCAL else None,
            )
    first = order[0]
    status, why = problems[first]
    return Resolution(None, status, why, False, _other_available(first, available), None)


def limits_of(manifest: Manifest, setting: ToolSetting | None) -> Limits:
    """The limits a run is held to: the manifest's, unless an administrator changed them. A tool
    can be held to a lower risk class than its manifest, never a higher one."""
    chosen = ToolRisk(setting.max_risk) if setting and setting.max_risk else manifest.risk
    return Limits(
        cpus=float(setting.cpus) if setting and setting.cpus is not None else None,
        memory_mb=setting.memory_mb if setting else None,
        timeout_s=(setting.timeout_s if setting and setting.timeout_s else None)
        or manifest.timeout_s,
        max_output_mb=(setting.max_output_mb if setting and setting.max_output_mb else None)
        or manifest.max_output_mb,
        rate_per_s=setting.rate_per_s if setting else None,
        max_risk=min(chosen, manifest.risk, key=RISK_ORDER.index),
    )


def refusal(manifest: Manifest, setting: ToolSetting | None) -> str | None:
    """Why a call must not run whatever else is true: the tool is off, or its risk class is above
    what the administrator allows. None when the settings have no objection."""
    if setting is None:
        return None
    if not setting.enabled:
        return "This tool is switched off in the Tools settings."
    if setting.max_risk and RISK_ORDER.index(manifest.risk) > RISK_ORDER.index(
        ToolRisk(setting.max_risk)
    ):
        return f"This tool is limited to {setting.max_risk} actions in the Tools settings."
    return None


async def run_mode(session: AsyncSession) -> RunMode:
    """The default for every tool. A damaged value is treated as Auto."""
    row = await session.get(AppSetting, RUN_MODE_KEY)
    try:
        return RunMode(row.value) if row else RunMode.AUTO
    except ValueError:
        return RunMode.AUTO


async def set_run_mode(session: AsyncSession, mode: RunMode) -> None:
    await session.execute(
        insert(AppSetting)
        .values(key=RUN_MODE_KEY, value=mode.value)
        .on_conflict_do_update(index_elements=["key"], set_={"value": mode.value})
    )


async def settings_by_tool(session: AsyncSession) -> dict[str, ToolSetting]:
    return {row.tool_id: row for row in (await session.scalars(select(ToolSetting))).all()}
