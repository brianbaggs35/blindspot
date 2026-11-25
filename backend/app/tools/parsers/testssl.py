"""testssl.sh's JSON file (`--jsonfile`): protocols, ciphers, certificate and known TLS flaws."""

from app.tools.parsers.base import (
    Collector,
    JsonObject,
    ParseError,
    as_list,
    as_object,
    clip,
    load_json,
    number,
)
from app.tools.parsers.schema import Confidence, Issue, Severity, TlsFinding, ToolResult

_SEVERITY = {
    "OK": Severity.INFO,
    "INFO": Severity.INFO,
    "LOW": Severity.LOW,
    "WARN": Severity.LOW,
    "MEDIUM": Severity.MEDIUM,
    "HIGH": Severity.HIGH,
    "CRITICAL": Severity.CRITICAL,
}


def _finding(item: JsonObject) -> TlsFinding | None:
    severity = _SEVERITY.get(str(item.get("severity", "")).upper())
    identifier = clip(item.get("id"), 100)
    if severity is None or identifier is None:
        return None  # DEBUG and FATAL lines say nothing about the target
    address = clip(item.get("ip"), 100)
    port = number(item.get("port"))
    return TlsFinding(
        id=identifier,
        severity=severity,
        finding=clip(item.get("finding"), 4000) or "",
        host=address.split("/")[-1] if address else None,
        port=port if port is not None and 0 <= port <= 65535 else None,
        cve=[c for c in str(item.get("cve", "")).split() if c.startswith("CVE-")][:20],
    )


def _unwrapped(items: list[object]) -> list[object]:
    """Newer versions wrap the findings of each scanned address in a `scanResult` list."""
    nested = [as_object(item) for item in items]
    if nested and all(n is not None and "scanResult" in n for n in nested):
        return [e for n in nested if n for e in (as_list(n.get("scanResult")) or [])]
    return items


def _issue(finding: TlsFinding) -> Issue:
    return Issue(
        title=f"TLS: {finding.id}",
        severity=finding.severity,
        confidence=Confidence.FIRM,
        target=f"{finding.host}:{finding.port}" if finding.host else None,
        detail=finding.finding,
        reference=finding.cve[0] if finding.cve else None,
        tags=["tls"],
    )


def parse_testssl_json(data: bytes) -> ToolResult:
    """Every TLS finding, and an issue for each one that is a weakness."""
    document = load_json(data)
    wrapper = as_object(document)
    items = as_list(wrapper.get("scanResult") if wrapper is not None else document)
    if items is None:
        raise ParseError("The output is not a testssl.sh report")
    items = _unwrapped(items)
    found = Collector()
    findings: list[TlsFinding] = []
    issues: list[Issue] = []
    for item in items:
        entry = as_object(item)
        finding = _finding(entry) if entry is not None else None
        if finding is None:
            continue
        if not found.add(findings, finding):
            break
        if finding.severity is not Severity.INFO:
            found.add(issues, _issue(finding))
    return ToolResult(
        tool="p.testssl",
        parser="testssl_json",
        tls=findings,
        issues=issues,
        truncated=found.truncated,
        warnings=found.warnings,
    )
