"""WhatWeb's JSON log (`--log-json`): the technologies it recognised on each target."""

from app.tools.parsers.base import Collector, ParseError, as_list, as_object, clip, load_json
from app.tools.parsers.schema import Technology, ToolResult

# Plugins that report facts about the request, not a technology of the site.
_NOT_TECHNOLOGIES = frozenset({"Country", "IP", "HTTPServer", "X-Powered-By", "Title", "Cookies"})


def _versions(detail: object) -> list[str | None]:
    plugin = as_object(detail)
    listed = as_list(plugin.get("version")) if plugin is not None else None
    versions = [clip(v, 100) for v in listed] if listed is not None else []
    return versions or [None]


def parse_whatweb_json(data: bytes) -> ToolResult:
    """The technologies found, one per name and version, for each target."""
    document = load_json(data)
    entries = as_list(document)
    found = Collector()
    technologies: list[Technology] = []
    seen = 0
    for entry in entries if entries is not None else [document]:
        report = as_object(entry)
        plugins = as_object(report.get("plugins")) if report is not None else None
        if report is None or plugins is None:
            continue
        seen += 1
        target = clip(report.get("target"))
        for name, detail in plugins.items():
            if name in _NOT_TECHNOLOGIES:
                continue
            for version in _versions(detail):
                tech = Technology(name=clip(name, 100) or "unknown", version=version, target=target)
                if not found.add(technologies, tech):
                    break
    if not seen:
        raise ParseError("The output is not a WhatWeb report")
    return ToolResult(
        tool="o.whatweb",
        parser="whatweb_json",
        technologies=technologies,
        truncated=found.truncated,
        warnings=found.warnings,
    )
