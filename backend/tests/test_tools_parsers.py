"""Parsers: real tool output in, the one result shape out, and hostile or broken output refused."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from app.tools.parsers import PARSERS, ParseError, ToolResult, parse_output
from app.tools.parsers import base as parsers_base
from app.tools.parsers.base import (
    Collector,
    as_list,
    as_object,
    clip,
    json_lines,
    load_json,
    number,
    text_of,
)
from app.tools.parsers.schema import MAX_ITEMS, MAX_WARNINGS, Artifact, Credential, Severity
from app.tools.parsers.xmlsafe import parse_xml

FIXTURES = Path(__file__).parent / "fixtures" / "tools"
GOLDEN = FIXTURES / "golden"

CASES = [
    ("nmap_xml", "nmap.xml"),
    ("nmap_xml", "nmap-closed.xml"),
    ("ffuf_json", "ffuf.json"),
    ("whatweb_json", "whatweb.json"),
    ("wafw00f_json", "wafw00f.json"),
    ("testssl_json", "testssl.json"),
    ("nikto_csv", "nikto.csv"),
    ("nuclei_jsonl", "nuclei.jsonl"),
    ("httpx_jsonl", "httpx.jsonl"),
]


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def parsed(parser: str, name: str) -> ToolResult:
    return parse_output(parser, "t.test", fixture(name))


@pytest.mark.parametrize(("parser", "name"), CASES)
def test_each_parser_makes_what_the_golden_file_says(parser: str, name: str) -> None:
    result = parsed(parser, name).model_dump(mode="json")
    golden = GOLDEN / f"{name}.json"
    if os.environ.get("BLINDSPOT_UPDATE_GOLDEN"):
        golden.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    assert result == json.loads(golden.read_text())


def test_every_parser_has_a_fixture_and_a_name_a_manifest_can_use() -> None:
    assert {parser for parser, _ in CASES} == set(PARSERS)


def test_the_result_is_recorded_as_the_tools_own() -> None:
    assert parsed("nmap_xml", "nmap.xml").tool == "t.test"


def test_nmap_finds_the_open_and_closed_ports() -> None:
    (host,) = parsed("nmap_xml", "nmap.xml").hosts
    assert (host.address, host.state, host.hostnames) == ("127.0.0.1", "up", ["localhost"])
    by_port = {s.port: s for s in host.services}
    assert by_port[22].state == "closed"
    assert (by_port[8081].product, by_port[8081].version) == ("Apache httpd", "2.4.41")
    assert by_port[8443].tunnel == "ssl"
    assert by_port[8081].cpe == ["cpe:/a:apache:http_server:2.4.41"]


def test_a_scan_that_found_nothing_open_is_still_a_scan() -> None:
    (host,) = parsed("nmap_xml", "nmap-closed.xml").hosts
    assert [(s.port, s.state) for s in host.services] == [(22, "closed")]


def test_ffuf_keeps_what_it_found_and_what_was_tried() -> None:
    http = parsed("ffuf_json", "ffuf.json").http
    assert {(r.input, r.status) for r in http} >= {("login", 200), ("robots.txt", 200)}
    assert all(r.url.startswith("http://127.0.0.1:8081/") for r in http)


def test_whatweb_names_the_technologies_and_leaves_out_request_facts() -> None:
    found = {(t.name, t.version) for t in parsed("whatweb_json", "whatweb.json").technologies}
    assert ("Apache", "2.4.41") in found
    assert ("PHP", "7.4.3") in found
    assert not {name for name, _ in found} & {"IP", "Country", "Title", "Cookies"}


def test_wafw00f_without_a_firewall_is_an_informational_issue() -> None:
    result = parsed("wafw00f_json", "wafw00f.json")
    assert [(i.title, i.severity) for i in result.issues] == [
        ("No web application firewall detected", Severity.INFO)
    ]


def test_wafw00f_with_a_firewall_names_it() -> None:
    report = json.dumps([{"url": "https://x.example", "detected": True, "firewall": "Cloudflare"}])
    result = parse_output("wafw00f_json", "p.waf", report.encode())
    assert [(t.name, t.category) for t in result.technologies] == [
        ("Cloudflare", "web application firewall")
    ]
    assert not result.issues


def test_testssl_turns_weaknesses_into_issues_and_keeps_every_finding() -> None:
    result = parsed("testssl_json", "testssl.json")
    assert result.tls
    severities = {i.severity for i in result.issues}
    assert Severity.CRITICAL in severities
    assert Severity.INFO not in severities
    assert any(i.target == "127.0.0.1:8443" for i in result.issues)
    heartbleed = next(t for t in result.tls if t.id == "heartbleed")
    assert heartbleed.cve == ["CVE-2014-0160"]
    assert heartbleed.severity is Severity.INFO


def test_testssl_ignores_debug_lines_and_reads_the_wrapped_form() -> None:
    lines = [
        {"id": "x", "severity": "DEBUG", "finding": "noise"},
        {"id": "SSLv3", "ip": "a/1.2.3.4", "port": "443", "severity": "HIGH", "finding": "offered"},
        {"id": "y", "ip": "1.2.3.4", "port": "70000", "severity": "LOW", "finding": "bad port"},
    ]
    flat = parse_output("testssl_json", "p.testssl", json.dumps(lines).encode())
    assert [t.id for t in flat.tls] == ["SSLv3", "y"]
    assert (flat.tls[0].host, flat.tls[0].port, flat.tls[1].port) == ("1.2.3.4", 443, None)
    wrapped = json.dumps({"scanResult": [{"scanResult": lines}]}).encode()
    assert [t.id for t in parse_output("testssl_json", "p.testssl", wrapped).tls] == ["SSLv3", "y"]
    several = json.dumps([{"scanResult": lines}, {"scanResult": lines}]).encode()
    assert len(parse_output("testssl_json", "p.testssl", several).tls) == 4


def test_nikto_reads_findings_by_column_and_ignores_the_stray_text() -> None:
    result = parsed("nikto_csv", "nikto.csv")
    assert [(t.name, t.version) for t in result.technologies] == [("Apache", "2.4.41")]
    assert len(result.issues) == 4
    assert all("SCALAR" not in (i.target or "") for i in result.issues)
    assert "robots.txt" in (result.issues[-1].target or "")
    assert result.issues[0].reference is None


def test_nikto_keeps_a_reference_when_there_is_one() -> None:
    text = (
        '"Nikto - v2.1.5"\n'
        '"h","1.1.1.1","80","","","","Apache"\n'
        '"h","1.1.1.1","80","OSVDB-3092","GET","/admin/","Found"\n'
        '"h","1.1.1.1","80","OSVDB-1","","/x","no method"\n'
    )
    result = parse_output("nikto_csv", "o.nikto", text.encode())
    assert [(i.reference, i.target) for i in result.issues] == [("OSVDB-3092", "h:80/admin/")]


def test_nuclei_makes_an_issue_for_each_match_and_counts_the_noise() -> None:
    result = parsed("nuclei_jsonl", "nuclei.jsonl")
    assert [(i.severity, i.reference) for i in result.issues] == [
        (Severity.INFO, "http-missing-security-headers"),
        (Severity.CRITICAL, "cve-2021-41773"),
        (Severity.INFO, "tech-detect"),
    ]
    assert result.issues[0].evidence == "Strict-Transport-Security, Content-Security-Policy"
    assert result.issues[1].target.endswith("passwd")  # pyright: ignore[reportOptionalMemberAccess]
    assert result.warnings == ["2 lines were not matches and were left out"]


def test_httpx_makes_a_response_and_technologies_for_each_live_address() -> None:
    result = parsed("httpx_jsonl", "httpx.jsonl")
    assert [(r.url, r.status, r.title) for r in result.http] == [
        ("http://127.0.0.1:8081", 200, "Demo Shop"),
        ("https://127.0.0.1:8443", 302, "Demo Shop"),
    ]
    assert result.http[1].redirect == "https://127.0.0.1:8443/login"
    assert [t.name for t in result.technologies] == ["Apache HTTP Server:2.4.41", "PHP:7.4.3"]
    assert result.warnings == ["2 lines were not results and were left out"]


EMPTY = [
    ("nmap_xml", b'<?xml version="1.0"?><nmaprun scanner="nmap"></nmaprun>'),
    ("ffuf_json", b'{"results": []}'),
    ("whatweb_json", b'[{"target": "x", "plugins": {}}]'),
    ("wafw00f_json", b"[]"),
    ("testssl_json", b"[]"),
    ("nikto_csv", b'"Nikto - v2.1.5"\n'),
    ("nuclei_jsonl", b""),
    ("httpx_jsonl", b"\n\n"),
]


@pytest.mark.parametrize(("parser", "output"), EMPTY)
def test_output_with_nothing_in_it_is_an_empty_result(parser: str, output: bytes) -> None:
    result = parse_output(parser, "t.test", output)
    assert result.is_empty()
    assert not result.truncated


MALFORMED = [
    ("nmap_xml", b"<nmaprun><host>"),
    ("nmap_xml", b"<other/>"),
    ("nmap_xml", b""),
    ("ffuf_json", b"{not json"),
    ("ffuf_json", b'{"results": 4}'),
    ("ffuf_json", b"[]"),
    ("whatweb_json", b'"text"'),
    ("whatweb_json", b"[]"),
    ("wafw00f_json", b'{"a": 1}'),
    ("wafw00f_json", b"[1, 2]"),
    ("testssl_json", b'{"a": 1}'),
    ("testssl_json", b""),
    ("nikto_csv", b"this is not a nikto report"),
    ("nuclei_jsonl", b"plain text\nmore text\n"),
    ("httpx_jsonl", b"[INF] started\n"),
]


@pytest.mark.parametrize(("parser", "output"), MALFORMED)
def test_malformed_output_is_a_parse_error_with_a_message_to_show(
    parser: str, output: bytes
) -> None:
    with pytest.raises(ParseError) as error:
        parse_output(parser, "t.test", output)
    assert str(error.value)
    assert "Traceback" not in str(error.value)


def test_unreadable_entries_are_left_out_and_said_so() -> None:
    mixed = json.dumps({"results": [{"url": "http://x/a", "status": 200}, {"nope": 1}, 7]})
    result = parse_output("ffuf_json", "p.ffuf", mixed.encode())
    assert [r.url for r in result.http] == ["http://x/a"]
    assert result.warnings == ["2 results could not be read and were left out"]


def results(count: int) -> bytes:
    return json.dumps(
        {"results": [{"url": f"http://x/{n}", "status": 200} for n in range(count)]}
    ).encode()


def test_huge_output_is_cut_at_the_cap_and_says_so() -> None:
    result = parse_output("ffuf_json", "p.ffuf", results(MAX_ITEMS + 50))
    assert len(result.http) == MAX_ITEMS
    assert result.truncated
    assert not parse_output("ffuf_json", "p.ffuf", results(MAX_ITEMS)).truncated


def test_a_huge_nmap_report_is_cut_too() -> None:
    ports = "".join(
        f'<port protocol="tcp" portid="{n}"><state state="open"/></port>' for n in range(1, 301)
    )
    hosts = "".join(
        f'<host><status state="up"/><address addr="10.0.{n // 250}.{n % 250}" addrtype="ipv4"/>'
        f"<ports>{ports if n == 0 else ''}</ports></host>"
        for n in range(MAX_ITEMS + 10)
    )
    result = parse_output("nmap_xml", "c.nmap", f"<nmaprun>{hosts}</nmaprun>".encode())
    assert len(result.hosts) == MAX_ITEMS
    assert result.truncated
    assert len(result.hosts[0].services) == 300


def test_too_many_services_on_one_host_are_cut() -> None:
    ports = "".join(
        f'<port protocol="udp" portid="{n % 65536}"><state state="open"/></port>'
        for n in range(MAX_ITEMS + 5)
    )
    report = (
        '<nmaprun><host><address addr="::1" addrtype="ipv6"/>'
        f"<ports>{ports}</ports></host></nmaprun>"
    )
    result = parse_output("nmap_xml", "c.nmap", report.encode())
    assert len(result.hosts[0].services) == MAX_ITEMS
    assert result.truncated


def test_output_beyond_the_size_limit_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parsers_base, "MAX_INPUT_BYTES", 100)
    for parser in PARSERS:
        with pytest.raises(ParseError, match="too large"):
            parse_output(parser, "t.test", b" " * 101)


def test_xml_that_declares_or_expands_entities_is_refused() -> None:
    bomb = (
        b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY a "aaaa">'
        b'<!ENTITY b "&a;&a;&a;">]><nmaprun>&b;</nmaprun>'
    )
    with pytest.raises(ParseError, match="entity"):
        parse_xml(bomb)
    external = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><nmaprun>&e;</nmaprun>'
    with pytest.raises(ParseError):
        parse_xml(external)


def test_xml_with_only_a_doctype_name_is_fine() -> None:
    assert parse_xml(b"<!DOCTYPE nmaprun>\n<nmaprun/>").tag == "nmaprun"


def test_deeply_nested_json_is_refused() -> None:
    deep = b'{"results": ' + b"[" * 60 + b"]" * 60 + b"}"
    with pytest.raises(ParseError, match="nested"):
        parse_output("ffuf_json", "p.ffuf", deep)
    lines, bad = json_lines(b'{"a": ' + b"[" * 60 + b"]" * 60 + b"}\n")
    assert (lines, bad) == ([], 1)
    lines, bad = json_lines(b"[1,2]\n{}\n \n")
    assert (lines, bad) == ([{}], 1)


def test_bytes_that_are_not_utf8_are_replaced_not_fatal() -> None:
    assert "�" in text_of(b"caf\xe9")
    report = b'{"results": [{"url": "http://x/caf\xe9", "status": 200}]}'
    assert parse_output("ffuf_json", "p.ffuf", report).http[0].url == "http://x/caf�"


def test_an_unknown_parser_is_an_error() -> None:
    with pytest.raises(ParseError, match="no parser called nope"):
        parse_output("nope", "t.test", b"")


def test_the_helpers() -> None:
    assert clip(None) is None
    assert clip("  ") is None
    assert clip(" abc ", 2) == "ab"
    assert clip(7) == "7"
    assert [number(v) for v in (True, 5, " 12 ", "x", None, 1.5)] == [None, 5, 12, None, None, None]
    assert as_object({"a": 1}) == {"a": 1}
    assert as_object([1]) is None
    assert as_list([1]) == [1]
    assert as_list({}) is None
    assert load_json(b" [1] ") == [1]
    with pytest.raises(ParseError, match="empty"):
        load_json(b"  ")
    with pytest.raises(ParseError, match="not valid JSON"):
        load_json(b"{")


def test_the_collector_stops_at_the_cap_and_limits_its_warnings() -> None:
    items: list[int] = []
    collector = Collector()
    assert all(collector.add(items, n) for n in range(MAX_ITEMS))
    assert not collector.truncated
    assert not collector.add(items, 0)
    assert collector.truncated
    for n in range(MAX_WARNINGS + 5):
        collector.warn(f"w{n}" * 200)
    assert len(collector.warnings) == MAX_WARNINGS
    assert all(len(w) <= 300 for w in collector.warnings)


def test_a_secret_in_a_result_is_never_printed() -> None:
    result: dict[str, Any] = Credential.model_validate(
        {"target": "h", "username": "root", "secret": "hunter2"}
    ).model_dump(mode="json")
    assert result["secret"] == "**********"
    assert "hunter2" not in repr(Credential(target="h", secret="hunter2"))  # pyright: ignore[reportArgumentType]


def test_a_result_with_only_an_artifact_is_not_empty() -> None:
    assert ToolResult(tool="t.x", parser="p").is_empty()
    assert not ToolResult(tool="t.x", parser="p", artifacts=[Artifact(name="shot.png")]).is_empty()


def test_ffuf_input_with_only_the_hash_has_no_input() -> None:
    report = {"results": [{"url": "http://x/a", "status": 200, "input": {"FFUFHASH": "ab"}}]}
    assert parse_output("ffuf_json", "p.ffuf", json.dumps(report).encode()).http[0].input is None


def test_httpx_skips_lines_without_an_address_and_empty_technology_names() -> None:
    lines = [{"nope": 1}, {"url": "http://x", "status_code": 200, "tech": ["", "Nginx"]}]
    text = "\n".join(json.dumps(line) for line in lines)
    result = parse_output("httpx_jsonl", "p.pd", text.encode())
    assert [t.name for t in result.technologies] == ["Nginx"]
    assert result.warnings == ["1 lines were not results and were left out"]


def test_nikto_without_a_banner_and_beyond_the_cap() -> None:
    rows = ['"Nikto - v2.1.5"', '"h","1.1.1.1","80","","","",""']
    rows += [f'"h","1.1.1.1","80","","GET","/{n}","finding {n}"' for n in range(MAX_ITEMS + 5)]
    result = parse_output("nikto_csv", "o.nikto", "\n".join(rows).encode())
    assert not result.technologies
    assert len(result.issues) == MAX_ITEMS
    assert result.truncated


def test_nmap_leaves_out_ports_and_hosts_it_cannot_place() -> None:
    report = (
        b'<nmaprun><host><address addr="10.0.0.1" addrtype="ipv4"/><ports>'
        b'<port protocol="tcp" portid="70000"><state state="open"/></port>'
        b'<port protocol="tcp"><state state="open"/></port>'
        b'<port protocol="tcp" portid="80"><state state="open"/></port>'
        b'</ports></host><host><address addr="aa:bb" addrtype="mac"/></host></nmaprun>'
    )
    (host,) = parse_output("nmap_xml", "c.nmap", report).hosts
    assert [s.port for s in host.services] == [80]


def test_nuclei_stops_at_the_cap() -> None:
    line = {
        "template-id": "t",
        "info": {"name": "n", "severity": "info"},
        "matched-at": "http://x/",
    }
    text = "\n".join(json.dumps(line) for _ in range(MAX_ITEMS + 3))
    result = parse_output("nuclei_jsonl", "c.nuclei", text.encode())
    assert len(result.issues) == MAX_ITEMS
    assert result.truncated


def test_testssl_stops_at_the_cap() -> None:
    lines = [{"id": f"x{n}", "severity": "LOW", "finding": "f"} for n in range(MAX_ITEMS + 3)]
    result = parse_output("testssl_json", "p.testssl", json.dumps(lines).encode())
    assert len(result.tls) == MAX_ITEMS
    assert result.truncated


def test_httpx_stops_at_the_cap() -> None:
    text = "\n".join(json.dumps({"url": f"http://x/{n}"}) for n in range(MAX_ITEMS + 3))
    result = parse_output("httpx_jsonl", "p.pd", text.encode())
    assert len(result.http) == MAX_ITEMS
    assert result.truncated


def test_whatweb_stops_at_the_cap() -> None:
    plugins = {f"P{n}": {"version": ["1"]} for n in range(MAX_ITEMS + 3)}
    report = [{"target": "http://x", "plugins": plugins}]
    result = parse_output("whatweb_json", "o.whatweb", json.dumps(report).encode())
    assert len(result.technologies) == MAX_ITEMS
    assert result.truncated
