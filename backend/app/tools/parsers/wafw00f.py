"""wafw00f's JSON output (`-f json`): whether a web application firewall stands in front of a
target, and which one."""

from app.tools.parsers.base import Collector, ParseError, as_list, as_object, clip, load_json
from app.tools.parsers.schema import Confidence, Issue, Severity, Technology, ToolResult


def parse_wafw00f_json(data: bytes) -> ToolResult:
    """A technology for each firewall detected. Finding none is an informational issue, because
    it changes how much a scan can be trusted to be noticed."""
    document = as_list(load_json(data))
    reports = [as_object(item) for item in document or []]
    if document is None or None in reports:
        raise ParseError("The output is not a wafw00f report")
    found = Collector()
    technologies: list[Technology] = []
    issues: list[Issue] = []
    for report in (r for r in reports if r is not None):
        target = clip(report.get("url"), 300)
        if report.get("detected") is True:
            name = clip(report.get("firewall"), 100) or "unknown firewall"
            found.add(
                technologies,
                Technology(name=name, category="web application firewall", target=target),
            )
        else:
            found.add(
                issues,
                Issue(
                    title="No web application firewall detected",
                    severity=Severity.INFO,
                    confidence=Confidence.TENTATIVE,
                    target=target,
                ),
            )
    return ToolResult(
        tool="p.waf",
        parser="wafw00f_json",
        technologies=technologies,
        issues=issues,
        truncated=found.truncated,
        warnings=found.warnings,
    )
