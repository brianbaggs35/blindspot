"""The tool pack that ships in the app: every manifest is sound, safe and wired to real code."""

from typing import Any

import pytest
import yaml

from app.tools.analyzers import HANDLERS
from app.tools.argv import build_call
from app.tools.manifest import Capability, Manifest, Tier, ToolRisk
from app.tools.parsers import PARSERS
from app.tools.registry import BUNDLED, bundled_tools

TOOLS = {tool.manifest.id: tool.manifest for tool in bundled_tools()}

# One valid request for each tool.
EXAMPLES: dict[str, dict[str, Any]] = {
    "c.nmap": {"targets": ["10.0.0.5", "app.example.com"], "scan": "syn", "rate": 100},
    "c.sqlmap": {"url": "https://app.example.com/item?id=1", "parameter": "id", "data": "a=1"},
    "c.nuclei": {"url": "https://app.example.com/", "min_severity": "high"},
    "p.ffuf": {"url": "https://app.example.com/FUZZ", "wordlist": "common.txt"},
    "p.testssl": {"target": "app.example.com:443"},
    "p.waf": {"url": "https://app.example.com/"},
    "o.whatweb": {"url": "https://app.example.com/", "aggression": 3},
    "o.nikto": {"url": "https://app.example.com/"},
    "p.pd": {"url": "https://app.example.com/"},
    "b.headers": {"url": "https://app.example.com/"},
    "b.jwt": {"token": "aaa.bbb.ccc"},
    "b.wellknown": {"url": "https://app.example.com/"},
    "b.spider": {"url": "https://app.example.com/", "max_pages": 10},
    "b.entropy": {"url": "https://app.example.com/", "cookie": "PHPSESSID", "samples": 5},
}


def test_the_core_pack_is_there() -> None:
    assert set(TOOLS) == set(EXAMPLES)


def test_the_pack_follows_the_id_prefixes_of_the_methodology() -> None:
    tiers = {"c": Tier.CORE, "p": Tier.PACK, "o": Tier.OPTIONAL, "b": Tier.BUILTIN}
    assert {tool: manifest.tier for tool, manifest in TOOLS.items()} == {
        tool: tiers[tool[0]] for tool in TOOLS
    }


def test_every_parser_a_manifest_names_exists_and_every_parser_is_used() -> None:
    named = {parser for manifest in TOOLS.values() for parser in manifest.parsers}
    assert named <= set(PARSERS)
    assert named == set(PARSERS)


def test_every_built_in_has_a_handler_and_every_handler_a_manifest() -> None:
    handlers = {m.handler for m in TOOLS.values() if m.execution == "builtin"}
    assert handlers == set(HANDLERS)
    assert all(m.parsers == [] for m in TOOLS.values() if m.execution == "builtin")


def test_tools_that_scan_a_host_ask_for_the_capability_they_need() -> None:
    assert TOOLS["c.nmap"].capabilities == [Capability.NET_RAW]
    others = [m.id for m in TOOLS.values() if m.capabilities and m.id != "c.nmap"]
    assert others == []


def test_risk_classes_are_honest() -> None:
    assert TOOLS["c.sqlmap"].risk is ToolRisk.INTRUSIVE
    assert not [m.id for m in TOOLS.values() if m.risk is ToolRisk.DESTRUCTIVE]
    passive = {tool for tool, m in TOOLS.items() if m.risk is ToolRisk.PASSIVE}
    assert passive == {"b.headers", "b.jwt", "b.wellknown", "p.pd"}


def test_every_tool_says_what_it_does_and_what_could_go_wrong() -> None:
    for manifest in TOOLS.values():
        assert len(manifest.explain) > 40
        assert len(manifest.could_go_wrong) > 20
        assert all(param.description for param in manifest.params.values()), manifest.id


@pytest.mark.parametrize("tool", sorted(EXAMPLES))
def test_each_tool_makes_a_call_from_a_valid_request(tool: str) -> None:
    call = build_call(TOOLS[tool], EXAMPLES[tool])
    assert call.tool == tool
    assert all(arg == arg.strip() and "\n" not in arg for arg in call.argv)
    assert bool(call.targets) == (tool != "b.jwt")


@pytest.mark.parametrize("tool", sorted(t for t in EXAMPLES if not t.startswith("b.")))
def test_a_value_cannot_become_an_option_of_any_tool(tool: str) -> None:
    manifest = TOOLS[tool]
    for name in manifest.target_params():
        bad = ["-oN /tmp/x"] if manifest.params[name].many else "-oN /tmp/x"
        values: dict[str, object] = {**EXAMPLES[tool], name: bad}
        with pytest.raises(ValueError, match=r"dash|spaces"):
            build_call(manifest, values)


def test_the_commands_are_the_ones_the_tools_expect() -> None:
    def argv(tool: str) -> list[str]:
        return list(build_call(TOOLS[tool], EXAMPLES[tool]).argv)

    assert argv("c.nmap")[:7] == ["nmap", "-oX", "-", "--open", "-n", "-sS", "--max-rate=100"]
    assert argv("c.nmap")[-2:] == ["10.0.0.5", "app.example.com"]
    assert argv("c.nuclei")[-2:] == ["-severity", "high,critical"]
    assert "--risk=1" in argv("c.sqlmap")
    assert not any(a.startswith("--technique") and "S" in a for a in argv("c.sqlmap"))
    assert argv("p.ffuf")[:5] == ["ffuf", "-u", "https://app.example.com/FUZZ", "-w", "common.txt"]
    assert argv("o.nikto")[-2:] == ["-Tuning", "x6"]
    assert argv("p.waf") == ["wafw00f", "-f", "json", "-o", "-", "https://app.example.com/"]


def test_the_defaults_never_ask_for_the_gentlest_setting_to_be_exceeded() -> None:
    nuclei = build_call(TOOLS["c.nuclei"], {"url": "https://app.example.com/"}).argv
    assert "-etags" in nuclei
    assert nuclei[nuclei.index("-etags") + 1] == "dos,intrusive,fuzz,bruteforce"
    assert nuclei[nuclei.index("-severity") + 1] == "medium,high,critical"
    assert "-rate-limit" in nuclei
    sqlmap = build_call(TOOLS["c.sqlmap"], {"url": "https://app.example.com/?id=1"}).argv
    assert "--level=1" in sqlmap


def test_every_file_in_the_folder_is_a_manifest_named_for_its_id() -> None:
    files = sorted(BUNDLED.glob("*.yaml"))
    assert [f.stem for f in files] == sorted(TOOLS)
    for file in files:
        assert Manifest.model_validate(yaml.safe_load(file.read_text())).id == file.stem
