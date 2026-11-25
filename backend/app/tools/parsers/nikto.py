"""Nikto's CSV output (`-Format csv`): what it found on a web server.

Nikto does not grade its findings, so each is an informational issue for a person (or an agent) to
judge. Nikto 2.1.5 writes a stray `SCALAR(0x...)` and a misplaced quote into the address column
of some rows, which joins the address and port columns. The columns that matter are counted from
the end of the row, and the port is the one the banner line gave.
"""

import csv
import io

from app.tools.parsers.base import Collector, ParseError, clip, number, text_of
from app.tools.parsers.schema import Confidence, Issue, Severity, Technology, ToolResult

_BANNER_COLUMNS = 7
_MIN_COLUMNS = 6
_HEADER = "nikto - v"


def _issue(row: list[str], host: str | None, port: str | None) -> Issue | None:
    reference, method, path, message = row[-4:]
    if not message.strip() or not method.strip():
        return None
    target = f"{host or 'unknown'}:{port}{path}" if port else f"{host or 'unknown'}{path}"
    return Issue(
        title=clip(message, 300) or "Nikto finding",
        severity=Severity.INFO,
        confidence=Confidence.TENTATIVE,
        target=clip(target),
        reference=None if reference in ("", "OSVDB-0") else clip(reference),
        tags=[method.upper()[:10]],
    )


def parse_nikto_csv(data: bytes) -> ToolResult:
    """The server banner as a technology and every finding as an issue."""
    text = text_of(data)
    has_header = text.lstrip().lstrip('"').lower().startswith(_HEADER)
    found = Collector()
    issues: list[Issue] = []
    technologies: list[Technology] = []
    host: str | None = None
    port: str | None = None
    rows = 0
    for row in csv.reader(io.StringIO(text)):
        if len(row) < _MIN_COLUMNS:
            continue
        rows += 1
        if (
            len(row) == _BANNER_COLUMNS and not row[3] and not row[4]
        ):  # the line that names the host and its banner
            host, port = clip(row[0]), str(number(row[2]) or "") or None
            banner = clip(row[6], 100)
            if banner:
                name, _, version = banner.partition("/")
                found.add(
                    technologies,
                    Technology(
                        name=name,
                        version=version.strip() or None,
                        category="web server",
                        target=host,
                    ),
                )
            continue
        issue = _issue(row, host, port)
        if issue is not None and not found.add(issues, issue):
            break
    if not has_header and not rows:
        raise ParseError("The output is not a Nikto report")
    return ToolResult(
        tool="o.nikto",
        parser="nikto_csv",
        issues=issues,
        technologies=technologies,
        truncated=found.truncated,
        warnings=found.warnings,
    )
