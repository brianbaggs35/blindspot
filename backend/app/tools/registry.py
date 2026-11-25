"""The tools the app knows: the bundled manifests (YAML files next to this module) and the ones
an administrator defined (stored in the database).

The registry is rebuilt from both whenever it is asked for, so a tool an administrator adds or
removes is seen by the next request with nothing to restart. A stored manifest that no longer
validates (the rules got stricter) is skipped and logged, not allowed to take the page down.
"""

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import structlog
import yaml
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CustomTool
from app.tools.manifest import Manifest, Tier

BUNDLED = Path(__file__).parent / "bundled"
MAX_FILE_BYTES = 200_000

log = structlog.get_logger()


class ToolPackError(ValueError):
    """A bundled manifest is wrong. Seen by the person building the app, never by a user."""


@dataclass(frozen=True)
class Tool:
    """A manifest and where it came from. `fingerprint` changes when the manifest does, so a run
    can record exactly which definition it used."""

    manifest: Manifest
    origin: Literal["bundled", "custom"]
    fingerprint: str


def fingerprint(manifest: Manifest) -> str:
    """The first 16 hex characters of a SHA-256 of the manifest written canonically."""
    text = json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def read_manifest(path: Path) -> Manifest:
    """One bundled manifest file, validated."""
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ToolPackError(f"{path.name} is too large")
    try:
        manifest = Manifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (ValidationError, yaml.YAMLError) as error:
        raise ToolPackError(f"{path.name}: {error}") from error
    if manifest.tier is Tier.CUSTOM:
        raise ToolPackError(f"{path.name}: a bundled tool cannot be custom")
    return manifest


@lru_cache
def bundled_tools(directory: Path = BUNDLED) -> tuple[Tool, ...]:
    """Every bundled tool, in id order."""
    found: dict[str, Tool] = {}
    for path in sorted(directory.glob("*.yaml")):
        manifest = read_manifest(path)
        if manifest.id in found:
            raise ToolPackError(f"{path.name}: the id {manifest.id} is used twice")
        found[manifest.id] = Tool(manifest, "bundled", fingerprint(manifest))
    return tuple(found[key] for key in sorted(found))


class Registry:
    """A set of tools by id."""

    def __init__(self, tools: list[Tool]) -> None:
        self._by_id = {
            tool.manifest.id: tool for tool in sorted(tools, key=lambda t: t.manifest.id)
        }

    def all(self) -> list[Tool]:
        return list(self._by_id.values())

    def get(self, tool_id: str) -> Tool | None:
        return self._by_id.get(tool_id)


async def load_registry(session: AsyncSession) -> Registry:
    """The bundled tools and the stored custom tools."""
    tools = list(bundled_tools())
    for row in (await session.scalars(select(CustomTool).order_by(CustomTool.tool_id))).all():
        try:
            manifest = Manifest.model_validate(row.manifest)
        except ValidationError:
            log.warning("custom_tool_invalid", tool=row.tool_id)
            continue
        tools.append(Tool(manifest, "custom", fingerprint(manifest)))
    return Registry(tools)
