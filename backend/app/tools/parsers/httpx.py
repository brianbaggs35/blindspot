"""ProjectDiscovery httpx's JSON Lines output (`-json`): live web servers, with the title, the
server and the technologies it recognised."""

from app.tools.parsers.base import (
    Collector,
    JsonObject,
    ParseError,
    as_list,
    clip,
    json_lines,
    number,
)
from app.tools.parsers.schema import HttpResponse, Technology, ToolResult


def _response(line: JsonObject) -> HttpResponse | None:
    url = clip(line.get("url"), 4000)
    status = number(line.get("status_code"))
    if url is None:
        return None
    return HttpResponse(
        url=url,
        status=status if status is not None and 100 <= status <= 599 else None,
        length=number(line.get("content_length")),
        words=number(line.get("words")),
        lines=number(line.get("lines")),
        content_type=clip(line.get("content_type")),
        redirect=clip(line.get("location"), 4000),
        title=clip(line.get("title")),
        server=clip(line.get("webserver")),
    )


def parse_httpx_jsonl(data: bytes) -> ToolResult:
    """A response for each live address and a technology for each one httpx named."""
    lines, bad = json_lines(data)
    if not lines and bad:
        raise ParseError("The output is not httpx JSON Lines")
    found = Collector()
    responses: list[HttpResponse] = []
    technologies: list[Technology] = []
    for line in lines:
        response = _response(line)
        if response is None:
            bad += 1
            continue
        if not found.add(responses, response):
            break
        for name in as_list(line.get("tech")) or []:
            label = clip(name, 100)
            if label:
                found.add(technologies, Technology(name=label, target=response.url[:300]))
    if bad:
        found.warn(f"{bad} lines were not results and were left out")
    return ToolResult(
        tool="p.pd",
        parser="httpx_jsonl",
        http=responses,
        technologies=technologies,
        truncated=found.truncated,
        warnings=found.warnings,
    )
