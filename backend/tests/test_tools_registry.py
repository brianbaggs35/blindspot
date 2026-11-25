"""Reading bundled manifests from disk."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from tests.tools_helpers import NMAP, manifest

from app.tools.manifest import Manifest
from app.tools.registry import (
    BUNDLED,
    Registry,
    Tool,
    ToolPackError,
    bundled_tools,
    fingerprint,
    read_manifest,
)


def write(folder: Path, name: str, document: dict[str, Any]) -> Path:
    path = folder / name
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def test_the_bundled_manifests_are_all_valid() -> None:
    """Whatever ships in the app must load, or the app would not start its tool list."""
    tools = bundled_tools()
    assert [tool.manifest.id for tool in tools] == sorted(tool.manifest.id for tool in tools)
    assert all(tool.origin == "bundled" for tool in tools)
    assert all(tool.manifest.tier.value != "custom" for tool in tools)
    assert BUNDLED.is_dir()


def test_a_folder_of_manifests_is_read_in_id_order(tmp_path: Path) -> None:
    write(tmp_path, "b.yaml", manifest(NMAP, id="c.zmap", name="Zmap"))
    write(tmp_path, "a.yaml", NMAP)
    found = bundled_tools.__wrapped__(tmp_path)
    assert [tool.manifest.id for tool in found] == ["c.nmap", "c.zmap"]
    assert found[0].fingerprint == fingerprint(Manifest.model_validate(NMAP))
    assert bundled_tools.__wrapped__(tmp_path / "nowhere") == ()


def test_the_fingerprint_changes_with_the_manifest() -> None:
    one = Manifest.model_validate(NMAP)
    two = Manifest.model_validate(manifest(NMAP, timeout_s=901))
    assert len(fingerprint(one)) == 16
    assert fingerprint(one) == fingerprint(Manifest.model_validate(NMAP))
    assert fingerprint(one) != fingerprint(two)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("id: [", "bad.yaml"),
        ("- a\n- b\n", "bad.yaml"),
        ("id: c.nmap\n", "bad.yaml"),
        ("x" * 200_001, "too large"),
    ],
)
def test_a_bad_file_is_an_error_that_names_it(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ToolPackError, match=message):
        read_manifest(path)


def test_a_bundled_manifest_cannot_be_custom(tmp_path: Path) -> None:
    custom = manifest(NMAP, id="x.nmap", tier="custom", binary="nmap", capabilities=[])
    with pytest.raises(ToolPackError, match="cannot be custom"):
        read_manifest(write(tmp_path, "c.yaml", custom))


def test_an_id_used_twice_is_refused(tmp_path: Path) -> None:
    write(tmp_path, "a.yaml", NMAP)
    write(tmp_path, "b.yaml", NMAP)
    with pytest.raises(ToolPackError, match="used twice"):
        bundled_tools.__wrapped__(tmp_path)


def test_a_registry_finds_tools_by_id() -> None:
    tool = Tool(Manifest.model_validate(NMAP), "bundled", "abc")
    registry = Registry([tool])
    assert registry.get("c.nmap") is tool
    assert registry.get("c.other") is None
    assert registry.all() == [tool]
