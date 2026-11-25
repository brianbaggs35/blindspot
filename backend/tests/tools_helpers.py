"""What the tool tests share: a manifest like the plan's example for nmap."""

import copy
from typing import Any

NMAP: dict[str, Any] = {
    "id": "c.nmap",
    "name": "Nmap",
    "tier": "core",
    "binary": "nmap",
    "risk": "active",
    "capabilities": ["NET_RAW"],
    "params": {
        "targets": {"type": "target", "required": True, "many": True},
        "ports": {"type": "ports", "default": "top-1000"},
        "scan": {"type": "enum", "values": ["connect", "syn", "version"], "default": "connect"},
        "rate": {"type": "integer", "minimum": 1, "maximum": 1000},
        "verbose": {"type": "boolean"},
    },
    "argv": [
        "-oX",
        "-",
        {"when": "scan", "equals": "syn", "args": ["-sS"]},
        {"when": "scan", "equals": "version", "args": ["-sV"]},
        {"when": "rate", "args": ["--max-rate={rate}"]},
        {"when": "verbose", "args": ["-v"]},
        "-p",
        "{ports}",
        "{targets...}",
    ],
    "version": {"args": ["--version"], "pattern": "Nmap version ([0-9.]+)"},
    "timeout_s": 900,
    "max_output_mb": 20,
    "parsers": ["nmap_xml"],
    "explain": "Looks for open network doors (ports) on a server and what listens behind them.",
    "could_go_wrong": "Active scanning can trigger alerts and, rarely, upset fragile devices.",
}

CUSTOM: dict[str, Any] = {
    "id": "x.headers",
    "name": "Header check",
    "binary": "curl",
    "risk": "passive",
    "params": {"url": {"type": "target", "required": True}},
    "argv": ["--head", "--silent", "{url}"],
    "explain": "Fetches only the headers of a page.",
    "could_go_wrong": "It makes one request to the target.",
}


def manifest(base: dict[str, Any] | None = None, **changes: Any) -> dict[str, Any]:
    """A copy of a manifest with some fields changed."""
    document = copy.deepcopy(base if base is not None else NMAP)
    document.update(changes)
    return document
