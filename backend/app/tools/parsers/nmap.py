"""Nmap's XML output (`-oX -`): hosts, ports and the services found on them."""

from typing import Literal

from app.tools.parsers.base import Collector, ParseError, clip, number
from app.tools.parsers.schema import Host, Service, ToolResult
from app.tools.parsers.xmlsafe import Element, parse_xml

_PROTOCOLS: tuple[Literal["tcp"], Literal["udp"], Literal["sctp"]] = ("tcp", "udp", "sctp")


def _service(port: Element) -> Service | None:
    portid = number(port.get("portid"))
    state = port.find("state")
    if portid is None or not 0 <= portid <= 65535 or state is None:
        return None
    protocol = port.get("protocol", "tcp")
    detail = port.find("service")
    cpes = [clip(c.text) for c in detail.findall("cpe")] if detail is not None else []
    return Service(
        port=portid,
        protocol=protocol if protocol in _PROTOCOLS else "tcp",
        state=clip(state.get("state")) or "unknown",
        name=clip(detail.get("name")) if detail is not None else None,
        product=clip(detail.get("product")) if detail is not None else None,
        version=clip(detail.get("version")) if detail is not None else None,
        tunnel=clip(detail.get("tunnel")) if detail is not None else None,
        cpe=[c for c in cpes if c],
    )


def _state(value: str | None) -> Literal["up", "down", "unknown"]:
    if value == "up":
        return "up"
    return "down" if value == "down" else "unknown"


def _host(element: Element, found: Collector) -> Host | None:
    addresses = [a for a in element.findall("address") if a.get("addrtype") in ("ipv4", "ipv6")]
    if not addresses:
        return None
    status = element.find("status")
    state = status.get("state") if status is not None else None
    names = (clip(h.get("name")) for h in element.iter("hostname"))
    host = Host(
        address=clip(addresses[0].get("addr")) or "",
        hostnames=[name for name in names if name],
        state=_state(state),
    )
    for port in element.iter("port"):
        service = _service(port)
        if service is not None and not found.add(host.services, service):
            break
    return host


def parse_nmap_xml(data: bytes) -> ToolResult:
    """Every host nmap reported, with its ports. Ports that are closed or filtered are kept, with
    their state, so "nothing open" can be told from "nothing scanned"."""
    root = parse_xml(data)
    if root.tag != "nmaprun":
        raise ParseError("The output is not an nmap report")
    found = Collector()
    hosts: list[Host] = []
    for element in root.findall("host"):
        host = _host(element, found)
        if host is not None and not found.add(hosts, host):
            break
    return ToolResult(
        tool="c.nmap",
        parser="nmap_xml",
        hosts=hosts,
        truncated=found.truncated,
        warnings=found.warnings,
    )
