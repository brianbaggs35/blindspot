"""Nuclei's JSON Lines output (`-jsonl`): one line for each template that matched."""

from app.tools.parsers.base import (
    Collector,
    JsonObject,
    ParseError,
    as_list,
    as_object,
    clip,
    json_lines,
)
from app.tools.parsers.schema import Confidence, Issue, Severity, ToolResult

_SEVERITY = {s.value: s for s in Severity}


def _cves(info: JsonObject) -> list[str]:
    classification = as_object(info.get("classification"))
    raw = classification.get("cve-id") if classification is not None else None
    listed = as_list(raw) if not isinstance(raw, str) else [raw]
    return [c for c in listed if isinstance(c, str)] if listed is not None else []


def _issue(line: JsonObject) -> Issue | None:
    info = as_object(line.get("info"))
    template = clip(line.get("template-id"), 300)
    if info is None or template is None:
        return None
    cves = _cves(info)
    extracted = as_list(line.get("extracted-results")) or []
    tags = as_list(info.get("tags")) or []
    return Issue(
        title=clip(info.get("name")) or template,
        severity=_SEVERITY.get(str(info.get("severity", "")).lower(), Severity.INFO),
        confidence=Confidence.FIRM,
        target=clip(line.get("matched-at") or line.get("host"), 4000),
        detail=clip(info.get("description"), 4000),
        reference=cves[0] if cves else template,
        evidence=clip(", ".join(str(e) for e in extracted[:10]), 4000),
        tags=[t for t in tags if isinstance(t, str)][:20],
    )


def parse_nuclei_jsonl(data: bytes) -> ToolResult:
    """An issue for each match. Lines that are not matches (banners, progress) are counted and
    mentioned, not fatal; output with no JSON object in it at all is an error."""
    lines, bad = json_lines(data)
    if not lines and bad:
        raise ParseError("The output is not nuclei JSON Lines")
    found = Collector()
    issues: list[Issue] = []
    for line in lines:
        issue = _issue(line)
        if issue is None:
            bad += 1
        elif not found.add(issues, issue):
            break
    if bad:
        found.warn(f"{bad} lines were not matches and were left out")
    return ToolResult(
        tool="c.nuclei",
        parser="nuclei_jsonl",
        issues=issues,
        truncated=found.truncated,
        warnings=found.warnings,
    )
