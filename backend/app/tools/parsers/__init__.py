"""Parsers: a tool's raw output in, the one `ToolResult` out (see `schema.py`).

`parse_output` is what the runner calls, with the parser names a manifest lists. A parser that
fails never takes the run down: the failure is a `ParseError` with a message that is safe to show,
and the raw output is kept for a person to read.
"""

from app.tools.parsers.base import ParseError, Parser
from app.tools.parsers.ffuf import parse_ffuf_json
from app.tools.parsers.httpx import parse_httpx_jsonl
from app.tools.parsers.nikto import parse_nikto_csv
from app.tools.parsers.nmap import parse_nmap_xml
from app.tools.parsers.nuclei import parse_nuclei_jsonl
from app.tools.parsers.schema import ToolResult
from app.tools.parsers.testssl import parse_testssl_json
from app.tools.parsers.wafw00f import parse_wafw00f_json
from app.tools.parsers.whatweb import parse_whatweb_json

PARSERS: dict[str, Parser] = {
    "nmap_xml": parse_nmap_xml,
    "ffuf_json": parse_ffuf_json,
    "whatweb_json": parse_whatweb_json,
    "wafw00f_json": parse_wafw00f_json,
    "nikto_csv": parse_nikto_csv,
    "testssl_json": parse_testssl_json,
    "nuclei_jsonl": parse_nuclei_jsonl,
    "httpx_jsonl": parse_httpx_jsonl,
}


def parse_output(parser: str, tool_id: str, data: bytes) -> ToolResult:
    """The result a parser makes from a tool's output, recorded as the tool's own."""
    function = PARSERS.get(parser)
    if function is None:
        raise ParseError(f"There is no parser called {parser}")
    return function(data).model_copy(update={"tool": tool_id})


__all__ = ["PARSERS", "ParseError", "ToolResult", "parse_output"]
