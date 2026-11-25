"""ffuf's JSON output (`-of json`): the paths and values that got an interesting answer."""

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
from app.tools.parsers.schema import HttpResponse, ToolResult


def _first_input(item: JsonObject) -> str | None:
    values = as_object(item.get("input"))
    if values is None:
        return None
    for key, value in values.items():
        if key != "FFUFHASH":
            return clip(value)
    return None


def _response(item: JsonObject) -> HttpResponse | None:
    url = clip(item.get("url"), 4000)
    status = number(item.get("status"))
    if url is None or status is None or not 100 <= status <= 599:
        return None
    return HttpResponse(
        url=url,
        status=status,
        length=number(item.get("length")),
        words=number(item.get("words")),
        lines=number(item.get("lines")),
        content_type=clip(item.get("content-type")),
        redirect=clip(item.get("redirectlocation"), 4000),
        input=_first_input(item),
    )


def parse_ffuf_json(data: bytes) -> ToolResult:
    """Every result ffuf kept. A scan with no results is a valid, empty answer."""
    document = as_object(load_json(data))
    results = as_list(document.get("results")) if document is not None else None
    if results is None:
        raise ParseError("The output is not an ffuf report")
    found = Collector()
    responses: list[HttpResponse] = []
    skipped = 0
    for item in results:
        entry = as_object(item)
        response = _response(entry) if entry is not None else None
        if response is None:
            skipped += 1
        elif not found.add(responses, response):
            break
    if skipped:
        found.warn(f"{skipped} results could not be read and were left out")
    return ToolResult(
        tool="p.ffuf",
        parser="ffuf_json",
        http=responses,
        truncated=found.truncated,
        warnings=found.warnings,
    )
