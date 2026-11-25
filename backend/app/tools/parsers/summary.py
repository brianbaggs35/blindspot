"""A plain-words summary of a result, for the page a person reads before the details.

The summary is made from the result's shape alone, so every tool gets one, and it never repeats a
value a tool printed except names the tool itself reported (a technology, a port number).
"""

from app.tools.parsers.schema import Severity, ToolResult

_ORDER = (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO)


def _count(number: int, one: str, many: str | None = None) -> str:
    return f"{number} {one if number == 1 else many or one + 's'}"


def _severity_line(result: ToolResult) -> str | None:
    counts = {s: sum(1 for i in result.issues if i.severity is s) for s in _ORDER}
    parts = [f"{counts[s]} {s.value}" for s in _ORDER if counts[s]]
    if not parts:
        return None
    return f"{_count(len(result.issues), 'issue')} found: " + ", ".join(parts) + "."


def summarize(result: ToolResult) -> list[str]:
    """One sentence for each kind of thing the tool found, most serious first."""
    lines: list[str] = []
    if line := _severity_line(result):
        lines.append(line)
    if result.hosts:
        open_ports = sum(1 for h in result.hosts for s in h.services if s.state == "open")
        lines.append(
            f"{_count(len(result.hosts), 'host')} answered, with {_count(open_ports, 'open port')}."
        )
    if result.http:
        lines.append(f"{_count(len(result.http), 'web address', 'web addresses')} recorded.")
    if result.technologies:
        names = sorted({t.name for t in result.technologies})
        shown = ", ".join(names[:8]) + (" and more" if len(names) > 8 else "")
        lines.append(f"Recognised software: {shown}.")
    if result.tls:
        weak = sum(1 for t in result.tls if t.severity is not Severity.INFO)
        lines.append(f"{_count(len(result.tls), 'TLS check')} run, {weak} with a problem.")
    if result.credentials:
        lines.append(f"{_count(len(result.credentials), 'credential')} found (kept sealed).")
    if result.truncated:
        lines.append("The output was long, so only the first part is shown.")
    if not lines:
        lines.append("The tool ran and found nothing to report.")
    return lines
