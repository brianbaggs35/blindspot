"""The built-in analyzers: canned pages in, findings out. No network anywhere."""

import base64
import inspect
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

import pytest

from app.tools.analyzers import HANDLERS, Fetched, FetchError
from app.tools.analyzers import entropy as entropy_tool
from app.tools.analyzers import headers as headers_tool
from app.tools.analyzers import jwt as jwt_tool
from app.tools.analyzers import spider as spider_tool
from app.tools.analyzers import wellknown as wellknown_tool
from app.tools.analyzers.csp import evaluate_csp, parse_csp
from app.tools.analyzers.entropy import analyze_tokens, estimate_bits
from app.tools.analyzers.headers import (
    PROBE_ORIGIN,
    analyze_cookies,
    analyze_cors,
    analyze_response,
)
from app.tools.analyzers.jwt import inspect_jwt
from app.tools.analyzers.spider import Form, form_issues, read_page
from app.tools.analyzers.wellknown import (
    parse_robots,
    parse_security_txt,
    robots_issues,
    security_txt_issues,
    sitemap_urls,
)
from app.tools.parsers import ParseError
from app.tools.parsers import base as parsers_base
from app.tools.parsers.schema import MAX_ITEMS, Issue, Severity

NOW = datetime(2026, 11, 25, tzinfo=UTC)
GOOD = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=()",
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; base-uri 'none'; "
    "frame-ancestors 'none'",
}


def page(
    url: str = "https://app.example.com/",
    headers: Mapping[str, str] | None = None,
    body: str | bytes = b"",
    status: int = 200,
    extra: list[tuple[str, str]] | None = None,
) -> Fetched:
    pairs = [(k, v) for k, v in (headers or {}).items()] + (extra or [])
    return Fetched(url, status, tuple(pairs), body.encode() if isinstance(body, str) else body)


class Canned:
    """A fetcher with answers by address (or by address and Origin), and a record of requests."""

    def __init__(self, pages: dict[str, Fetched | FetchError | list[Fetched]]) -> None:
        self.pages = pages
        self.requests: list[tuple[str, dict[str, str]]] = []

    async def get(self, url: str, headers: Mapping[str, str] | None = None) -> Fetched:
        self.requests.append((url, dict(headers or {})))
        answer = self.pages.get(url)
        if isinstance(answer, FetchError):
            raise answer
        if isinstance(answer, list):
            return answer.pop(0)
        return answer or page(url, status=404)


def tags(result_issues: Sequence[Issue]) -> set[str | None]:
    return {i.reference for i in result_issues}


# ---- fetch


def test_a_response_answers_for_its_headers_and_body() -> None:
    response = page(extra=[("Set-Cookie", "a=1"), ("set-cookie", "b=2")], body=b"caf\xe9")
    assert response.headers_named("SET-COOKIE") == ["a=1", "b=2"]
    assert response.header("set-cookie") == "a=1"
    assert response.header("missing") is None
    assert response.text() == "caf�"


# ---- csp


def test_a_strict_policy_has_nothing_to_report() -> None:
    assert evaluate_csp(GOOD["Content-Security-Policy"]) == []


def test_the_first_of_a_repeated_directive_wins() -> None:
    assert parse_csp("script-src a; script-src b;; ") == {"script-src": ["a"]}


def test_a_policy_that_only_reports_blocks_nothing() -> None:
    (issue,) = evaluate_csp("default-src 'none'", report_only=True)
    assert issue.reference == "csp:report-only"


def test_a_policy_without_script_limits_is_weak() -> None:
    found = tags(evaluate_csp("img-src 'self'"))
    assert found == {
        "csp:no-script-src",
        "csp:no-object-src",
        "csp:no-base-uri",
        "csp:no-frame-ancestors",
    }


def test_inline_eval_wildcards_and_shared_hosts_are_found_in_script_src() -> None:
    policy = (
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https: cdnjs.cloudflare.com;"
        " object-src 'none'; base-uri 'self'; frame-ancestors 'self'"
    )
    assert tags(evaluate_csp(policy)) == {
        "csp:unsafe-inline",
        "csp:unsafe-eval",
        "csp:wildcard-script",
        "csp:bypass-host",
    }


def test_default_src_is_read_when_there_is_no_script_src() -> None:
    assert "csp:wildcard-script" in tags(evaluate_csp("default-src *"))


def test_a_nonce_or_strict_dynamic_makes_inline_and_hosts_fine() -> None:
    policy = "script-src 'nonce-abc' 'unsafe-inline' https: cdn.jsdelivr.net 'strict-dynamic'"
    assert tags(evaluate_csp(policy)) == {
        "csp:no-object-src",
        "csp:no-base-uri",
        "csp:no-frame-ancestors",
    }
    assert "csp:unsafe-inline" not in tags(evaluate_csp("script-src 'sha256-abc' 'unsafe-inline'"))


# ---- headers


def test_a_page_with_every_header_is_clean() -> None:
    result = analyze_response(page(headers=GOOD), None)
    assert result.issues == []
    assert result.http[0].status == 200


def test_a_bare_page_misses_every_header() -> None:
    result = analyze_response(page(), None)
    assert tags(result.issues) == {
        "headers:no-hsts",
        "headers:no-nosniff",
        "headers:framing",
        "headers:referrer",
        "headers:no-permissions-policy",
        "headers:no-csp",
    }


def test_hsts_is_only_expected_over_https_and_must_last() -> None:
    plain = analyze_response(page(url="http://app.example.com/"), None)
    assert "headers:no-hsts" not in tags(plain.issues)
    short = analyze_response(
        page(headers={**GOOD, "Strict-Transport-Security": "max-age=60"}), None
    )
    assert tags(short.issues) == {"headers:short-hsts"}
    broken = analyze_response(
        page(headers={**GOOD, "Strict-Transport-Security": "includeSubDomains"}), None
    )
    assert tags(broken.issues) == {"headers:short-hsts"}


def test_framing_is_stopped_by_either_header() -> None:
    only_csp = {k: v for k, v in GOOD.items() if k != "X-Frame-Options"}
    assert analyze_response(page(headers=only_csp), None).issues == []
    weak = {
        **GOOD,
        "X-Frame-Options": "ALLOW-FROM x",
        "Content-Security-Policy": "default-src 'none'",
    }
    found = analyze_response(page(headers=weak), None).issues
    assert {i.reference for i in found} >= {"headers:framing"}


def test_a_csp_that_only_reports_is_found_and_leaks_are_named() -> None:
    headers = {
        **{k: v for k, v in GOOD.items() if k != "Content-Security-Policy"},
        "Content-Security-Policy-Report-Only": "default-src 'none'",
        "Server": "Apache/2.4.41 (Ubuntu)",
        "X-Powered-By": "PHP/7.4.3",
        "X-AspNet-Version": "4.0",
        "Referrer-Policy": "unsafe-url",
    }
    result = analyze_response(page(headers=headers), None)
    assert {"csp:report-only", "headers:leak-server", "headers:leak-x-powered-by"} <= tags(
        result.issues
    )
    assert "headers:leak-x-aspnet-version" in tags(result.issues)
    assert {(t.name, t.version) for t in result.technologies} == {
        ("Apache", "2.4.41"),
        ("PHP", "7.4.3"),
        ("4.0", None),
    }
    assert "headers:referrer" in tags(result.issues)


def test_a_server_name_without_a_version_is_not_a_leak() -> None:
    result = analyze_response(page(headers={**GOOD, "Server": "nginx"}), None)
    assert result.issues == []


def test_cookies_missing_flags_are_named_and_values_are_never_printed() -> None:
    response = page(
        extra=[
            ("Set-Cookie", "sid=SECRETVALUE; Path=/"),
            ("Set-Cookie", "ok=1; Secure; HttpOnly; SameSite=Lax"),
            ("Set-Cookie", "x=1; Secure; HttpOnly; SameSite=None"),
            ("Set-Cookie", "y=1; HttpOnly; SameSite=None"),
            ("Set-Cookie", "__Host-z=1; Secure; HttpOnly; SameSite=Strict; Path=/; Domain=a.com"),
            ("Set-Cookie", "__Host-w=1; Secure; HttpOnly; SameSite=Strict; Path=/"),
        ]
    )
    found = analyze_cookies(response)
    assert [i.title for i in found] == [
        "Cookie sid is missing secure, httponly, samesite",
        "Cookie y is missing secure",
        "Cookie __Host-z is missing the __Host- rules",
    ]
    assert all("SECRETVALUE" not in (i.evidence or "") for i in found)
    insecure = analyze_cookies(
        page(url="http://a.example/", extra=[("Set-Cookie", "y=1; HttpOnly; SameSite=None")])
    )
    assert [i.title for i in insecure] == ["Cookie y is missing secure (needed with SameSite=None)"]
    over_http = analyze_cookies(
        page(url="http://a.example/", extra=[("Set-Cookie", "a=1; HttpOnly; SameSite=Lax")])
    )
    assert over_http == []


def test_cors_wildcard_reflection_and_null_are_found() -> None:
    star = page(headers={"Access-Control-Allow-Origin": "*"})
    assert tags(analyze_cors(star, None)) == {"headers:cors-wildcard"}
    creds = page(
        headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Credentials": "true"}
    )
    assert analyze_cors(creds, None)[0].severity is Severity.MEDIUM
    reflected = page(
        headers={
            "Access-Control-Allow-Origin": PROBE_ORIGIN,
            "Access-Control-Allow-Credentials": "true",
        }
    )
    (issue,) = analyze_cors(page(), reflected)
    assert (issue.reference, issue.severity) == ("headers:cors-reflected", Severity.HIGH)
    plain = page(headers={"Access-Control-Allow-Origin": PROBE_ORIGIN})
    assert [i.severity for i in analyze_cors(plain, plain)] == [Severity.MEDIUM]
    null = page(
        headers={"Access-Control-Allow-Origin": "null", "Access-Control-Allow-Credentials": "true"}
    )
    assert analyze_cors(null, None)[0].severity is Severity.MEDIUM
    assert (
        analyze_cors(page(headers={"Access-Control-Allow-Origin": "null"}), None)[0].severity
        is Severity.LOW
    )
    assert (
        analyze_cors(page(headers={"Access-Control-Allow-Origin": "https://ok.example"}), None)
        == []
    )


async def test_the_headers_tool_asks_twice_the_second_time_with_a_made_up_origin() -> None:
    url = "https://app.example.com/"
    fetcher = Canned(
        {url: [page(url, GOOD), page(url, {**GOOD, "Access-Control-Allow-Origin": PROBE_ORIGIN})]}
    )
    result = await headers_tool.run({"url": url}, fetcher)
    assert fetcher.requests == [(url, {}), (url, {"Origin": PROBE_ORIGIN})]
    assert tags(result.issues) == {"headers:cors-reflected"}
    assert result.tool == "b.headers"


def test_too_many_findings_are_cut() -> None:
    cookies = [("Set-Cookie", f"c{n}=1") for n in range(MAX_ITEMS + 3)]
    result = analyze_response(page(extra=cookies), None)
    assert len(result.issues) == MAX_ITEMS
    assert result.truncated


# ---- jwt


def token(header: object, claims: object, signature: str = "sig") -> str:
    def part(value: object) -> str:
        raw = json.dumps(value).encode() if not isinstance(value, bytes) else value
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{part(header)}.{part(claims)}.{signature}"


def test_an_unsigned_token_is_critical_and_its_value_is_never_echoed() -> None:
    value = token({"alg": "none"}, {"sub": "a", "password": "hunter2"}, "")
    result = inspect_jwt(value, NOW)
    assert {"jwt:alg-none", "jwt:no-exp", "jwt:sensitive-claims"} <= tags(result.issues)
    assert "hunter2" not in result.model_dump_json()
    assert value not in result.model_dump_json()


def test_a_missing_signature_and_a_shared_secret_are_found() -> None:
    assert tags(
        inspect_jwt(
            token({"alg": "RS256"}, {"exp": 4_000_000_000, "iat": 4_000_000_000}, ""), NOW
        ).issues
    ) == {"jwt:no-signature"}
    found = inspect_jwt(token({"alg": "hs256"}, {"exp": 1, "iat": 0}), NOW)
    assert tags(found.issues) == {"jwt:hmac"}


def test_long_lived_tokens_and_self_named_keys_are_found() -> None:
    claims = {"iat": 1_000_000, "exp": 1_000_000 + 400 * 24 * 3600}
    header = {"alg": "RS256", "jku": "http://x", "x5u": "http://y", "kid": "../../etc/passwd"}
    assert tags(inspect_jwt(token(header, claims), NOW).issues) == {
        "jwt:long-lived",
        "jwt:header-jku",
        "jwt:header-x5u",
        "jwt:kid",
    }
    assert "jwt:long-lived" in tags(
        inspect_jwt(token({"alg": "ES256"}, {"exp": 2_000_000_000 + 10**9}), NOW).issues
    )
    assert (
        inspect_jwt(token({"alg": "ES256", "kid": "key-1"}, {"exp": 1_800_000_000}), NOW).issues
        == []
    )


@pytest.mark.parametrize(
    "value",
    ["", "a.b", "a.b.c.d", "a b.c.d", "x" * 9000, "!!!.e30.sig"],
)
def test_a_value_that_is_not_a_token_is_a_warning_not_a_crash(value: str) -> None:
    result = inspect_jwt(value, NOW)
    assert result.issues == []
    assert result.warnings


def test_a_token_whose_parts_are_not_json_objects_is_a_warning() -> None:
    for header, claims in (({"alg": "x"}, [1]), (b"not json", {"a": 1}), (b"\xff\xfe", {})):
        assert inspect_jwt(token(header, claims), NOW).warnings == [
            "The token's header or claims are not JSON"
        ]


async def test_the_jwt_tool_reads_the_token_it_is_given_and_fetches_nothing() -> None:
    fetcher = Canned({})
    result = await jwt_tool.run({"token": token({"alg": "none"}, {})}, fetcher)
    assert "jwt:alg-none" in tags(result.issues)
    assert fetcher.requests == []


def test_the_clock_is_read_when_none_is_given() -> None:
    assert inspect_jwt(token({"alg": "RS256"}, {"exp": 1}))


# ---- entropy


def test_strength_estimates() -> None:
    assert estimate_bits("") == 0
    assert estimate_bits("0000000000000000") == 0
    assert estimate_bits("1234") < 14
    assert estimate_bits("aB3$" * 10) <= 80
    assert estimate_bits("kT9fQ2vLxP7mZ4wRb8NcYd5HsJ3gUe6A") > 112


def test_tokens_that_repeat_count_or_are_short_are_found() -> None:
    assert tags(analyze_tokens("sid", ["abc123", "abc123"])) >= {"entropy:repeat", "entropy:weak"}
    assert "entropy:counter" in tags(analyze_tokens("sid", ["100", "101", "102"]))
    assert "entropy:counter" not in tags(analyze_tokens("sid", ["5", "5", "5"]))
    assert "entropy:counter" not in tags(analyze_tokens("sid", ["1", "2"]))
    assert "entropy:counter" not in tags(analyze_tokens("sid", ["1", "2", "x"]))
    assert analyze_tokens("sid", []) == []


def test_a_middling_token_is_informational_and_a_long_random_one_is_fine() -> None:
    random_a = "kT9fQ2vLxP7mZ4wRb8NcYd5HsJ3gUe6A"
    random_b = "Zq1Xw8Er5Ty2Ui9Op4As7Df3Gh6Jk0Lm"
    assert analyze_tokens("sid", [random_a, random_b]) == []
    medium = "kT9fQ2vLxP7mZ4wR"
    (issue,) = analyze_tokens("sid", [medium])
    assert (issue.reference, issue.severity) == ("entropy:short", Severity.INFO)
    assert medium not in issue.model_dump_json()


def test_a_long_shared_start_is_found() -> None:
    first = "PREFIXPREFIX" + "kT9fQ2vLxP7mZ4wRb8NcYd5HsJ3gUe6A"
    second = "PREFIXPREFIX" + "Zq1Xw8Er5Ty2Ui9Op4As7Df3Gh6Jk0Lm"
    assert tags(analyze_tokens("sid", [first, second])) == {"entropy:prefix"}


async def test_the_entropy_tool_collects_the_session_cookie_across_requests() -> None:
    url = "https://app.example.com/"
    cookies = [
        page(url, extra=[("Set-Cookie", f"PHPSESSID={n}; Path=/"), ("Set-Cookie", "theme=dark")])
        for n in range(100, 103)
    ]
    fetcher = Canned({url: cookies})
    result = await entropy_tool.run({"url": url, "samples": 3}, fetcher)
    assert len(fetcher.requests) == 3
    assert "entropy:counter" in tags(result.issues)
    assert all("theme" not in (i.evidence or "") for i in result.issues)


async def test_the_entropy_tool_can_be_pointed_at_one_cookie_and_stops_at_the_cap() -> None:
    url = "https://app.example.com/"
    answer = page(url, extra=[("Set-Cookie", "a=1"), ("Set-Cookie", "SESSION=2")])
    fetcher = Canned({url: [answer] * 30})
    result = await entropy_tool.run({"url": url, "cookie": "a", "samples": 99}, fetcher)
    assert len(fetcher.requests) == 30
    assert {i.evidence for i in result.issues} == {"cookie a"}


async def test_the_entropy_tool_says_when_there_is_no_session_cookie() -> None:
    url = "https://app.example.com/"
    result = await entropy_tool.run({"url": url}, Canned({url: [page(url)] * 10}))
    assert result.issues == []
    assert result.warnings == ["No session cookie was set, so there was nothing to measure"]


# ---- well-known files


def test_robots_gives_away_paths_and_sitemaps() -> None:
    text = (
        "User-agent: *\nDisallow: /admin/ # staff\nDisallow: /admin/\nDisallow:\nAllow: /\n"
        "Sitemap: https://x/s.xml\nnonsense\n"
    )
    assert parse_robots(text) == (["/admin/"], ["https://x/s.xml"])
    found = robots_issues("https://x/robots.txt", text)
    assert [i.reference for i in found] == ["wellknown:robots", "wellknown:robots-interesting"]
    assert robots_issues("u", "User-agent: *\nDisallow: /shop\n")[0].reference == "wellknown:robots"
    assert len(robots_issues("u", "Disallow: /shop\n")) == 1
    assert robots_issues("u", "User-agent: *\nAllow: /\n") == []


def test_a_sitemap_lists_pages_or_more_sitemaps() -> None:
    urlset = (
        b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        b"<url><loc> https://x/a </loc></url><url><loc></loc></url></urlset>"
    )
    assert sitemap_urls(urlset) == (["https://x/a"], [])
    index = b"<sitemapindex><sitemap><loc>https://x/s2.xml</loc></sitemap></sitemapindex>"
    assert sitemap_urls(index) == ([], ["https://x/s2.xml"])
    with pytest.raises(ParseError, match="not a sitemap"):
        sitemap_urls(b"<html/>")
    with pytest.raises(ParseError):
        sitemap_urls(b"<!DOCTYPE x [<!ENTITY e 'a'>]><urlset>&e;</urlset>")


def test_security_txt_must_have_a_contact_and_an_expiry_that_has_not_passed() -> None:
    text = "# hello\nContact: mailto:s@x\nExpires: 2027-01-01T00:00:00Z\nbad line\n"
    assert parse_security_txt(text) == {
        "contact": ["mailto:s@x"],
        "expires": ["2027-01-01T00:00:00Z"],
    }
    assert security_txt_issues("u", text, NOW) == []
    assert tags(security_txt_issues("u", "Preferred-Languages: en", NOW)) == {
        "wellknown:txt-no-contact",
        "wellknown:txt-no-expires",
    }
    assert tags(security_txt_issues("u", "Contact: a\nExpires: 2020-01-01T00:00:00Z", NOW)) == {
        "wellknown:txt-expired"
    }
    assert (
        security_txt_issues("u", "Contact: a\nExpires: 2020-01-01", NOW)[0].detail
        == "The file has expired"
    )
    assert (
        security_txt_issues("u", "Contact: a\nExpires: soon", NOW)[0].detail
        == "Expires is not a date"
    )


async def test_the_wellknown_tool_reads_all_three_files() -> None:
    o = "https://app.example.com"
    fetcher = Canned(
        {
            f"{o}/robots.txt": page(
                f"{o}/robots.txt",
                body=f"Disallow: /admin\nSitemap: {o}/map.xml\nSitemap: https://evil.example/s.xml\n",
            ),
            f"{o}/map.xml": page(
                f"{o}/map.xml", body=f"<urlset><url><loc>{o}/a</loc></url></urlset>"
            ),
            f"{o}/.well-known/security.txt": page(
                f"{o}/.well-known/security.txt", body="Contact: a\nExpires: 2027-01-01T00:00:00Z"
            ),
        }
    )
    result = await wellknown_tool.run({"url": f"{o}/some/page?x=1"}, fetcher, NOW)
    assert [h.url for h in result.http] == [f"{o}/a"]
    assert tags(result.issues) == {"wellknown:robots", "wellknown:robots-interesting"}
    assert [u for u, _ in fetcher.requests] == [
        f"{o}/robots.txt",
        f"{o}/map.xml",
        f"{o}/.well-known/security.txt",
    ]


async def test_the_wellknown_tool_copes_with_nothing_there() -> None:
    o = "https://app.example.com"
    fetcher = Canned(
        {
            f"{o}/robots.txt": FetchError("Out of scope"),
            f"{o}/sitemap.xml": page(f"{o}/sitemap.xml", body="<html/>"),
            f"{o}/security.txt": page(
                f"{o}/security.txt", body="Contact: a\nExpires: 2999-01-01T00:00:00Z"
            ),
        }
    )
    result = await wellknown_tool.run({"url": o}, fetcher)
    assert result.issues == []
    assert result.warnings == [
        f"{o}/robots.txt: Out of scope",
        f"{o}/sitemap.xml: The output is not a sitemap",
    ]
    empty = await wellknown_tool.run({"url": o}, Canned({}), NOW)
    assert tags(empty.issues) == {"wellknown:txt-missing"}


async def test_a_huge_sitemap_is_cut() -> None:
    o = "https://app.example.com"
    urls = "".join(f"<url><loc>{o}/{n}</loc></url>" for n in range(MAX_ITEMS + 5))
    fetcher = Canned(
        {f"{o}/sitemap.xml": page(f"{o}/sitemap.xml", body=f"<urlset>{urls}</urlset>")}
    )
    result = await wellknown_tool.run({"url": o}, fetcher, NOW)
    assert len(result.http) == MAX_ITEMS
    assert result.truncated


# ---- spider

LOGIN = (
    '<html><a href="/shop?id=1&sort=asc#top">shop</a><a href="https://other.example/x">out</a>'
    '<a href="mailto:a@b">mail</a><a>none</a><area href="/map">'
    '<form action="http://app.example.com/login" method="POST">'
    '<input name="user"><input type="password" name="pw"><input type="submit">'
    '<textarea name="note"></textarea><select name="s"></select>'
    '<input type="file" name="doc"></form><form><input name="q"></form>'
    '<input name="stray"></form></html>'
)


def test_a_page_gives_its_links_and_forms() -> None:
    links, forms = read_page("https://app.example.com/", LOGIN)
    assert "https://app.example.com/shop?id=1&sort=asc#top" in links
    assert [(f.method, f.action) for f in forms] == [
        ("post", "http://app.example.com/login"),
        ("get", "https://app.example.com/"),
    ]
    assert forms[0].names == ["user", "pw", "note", "s", "doc"]
    assert not forms[0].has_token


def test_forms_that_send_a_password_in_clear_or_change_data_without_a_token_are_found() -> None:
    _, forms = read_page("https://app.example.com/", LOGIN)
    found = tags(form_issues("https://app.example.com/", forms[0]))
    assert found == {
        "spider:password-http",
        "spider:no-csrf-token",
        "spider:password-autocomplete",
        "spider:upload",
    }
    assert form_issues("https://app.example.com/", forms[1]) == []


def test_a_post_to_http_from_https_and_a_form_with_a_token() -> None:
    plain = Form("http://a/x", "post", [("csrf_token", "hidden"), ("a", "text")])
    assert tags(form_issues("https://a/", plain)) == {"spider:mixed-form"}
    assert form_issues("http://a/", plain) == []
    safe = Form(
        "https://a/x", "post", [("_csrf", "hidden"), ("pw", "password")], autocomplete_off=True
    )
    assert form_issues("https://a/", safe) == []


async def test_the_spider_stays_on_the_site_and_collects_parameters() -> None:
    o = "https://app.example.com"
    html = {"Content-Type": "text/html; charset=utf-8"}
    fetcher = Canned(
        {
            f"{o}/": page(f"{o}/", html, LOGIN),
            f"{o}/shop?id=1&sort=asc": page(
                f"{o}/shop?id=1&sort=asc", html, "<a href='/'>home</a>"
            ),
            f"{o}/map": page(f"{o}/map", {"Content-Type": "image/png"}, "<a href='/never'>x</a>"),
        }
    )
    result = await spider_tool.run({"url": f"{o}/", "max_pages": 50}, fetcher)
    asked = [u for u, _ in fetcher.requests]
    assert (
        asked
        == [f"{o}/", f"{o}/shop?id=1&sort=asc", f"{o}/map", f"{o}/login", f"{o}/login"][
            : len(asked)
        ]
    )
    assert not any("other.example" in u for u in asked)
    inputs = {h.url: h.input for h in result.http if h.input}
    assert inputs[f"{o}/shop"] == "id, sort"
    assert inputs["http://app.example.com/login"] == "doc, note, pw, s, user"
    assert "spider:password-http" in tags(result.issues)


async def test_the_spider_stops_at_the_page_limit_and_reports_refusals() -> None:
    o = "https://app.example.com"
    fetcher = Canned(
        {
            f"{o}/": page(f"{o}/", {}, "<a href='/a'>a</a><a href='/b'>b</a>"),
            f"{o}/a": FetchError("Out of scope"),
        }
    )
    result = await spider_tool.run({"url": f"{o}/", "max_pages": 1}, fetcher)
    assert [h.url for h in result.http] == [f"{o}/"]
    assert [u for u, _ in fetcher.requests] == [f"{o}/"]
    again = await spider_tool.run(
        {"url": f"{o}/"},
        Canned(
            {f"{o}/": page(f"{o}/", {}, "<a href='/a'>a</a>"), f"{o}/a": FetchError("Out of scope")}
        ),
    )
    assert again.warnings == [f"{o}/a: Out of scope"]


async def test_a_status_outside_the_range_is_not_recorded() -> None:
    o = "https://app.example.com"
    odd = Fetched(f"{o}/", 99, (), b"")
    result = await spider_tool.run({"url": f"{o}/"}, Canned({f"{o}/": odd}))
    assert result.http[0].status is None


async def test_too_many_parameter_sets_are_cut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parsers_base, "MAX_ITEMS", 3)
    o = "https://app.example.com"
    links = "".join(f"<a href='/p{n}?a=1'>x</a>" for n in range(6))
    body = f"<html>{links}<form action='/empty'></form></html>"
    result = await spider_tool.run(
        {"url": f"{o}/", "max_pages": 1}, Canned({f"{o}/": page(f"{o}/", {}, body)})
    )
    assert result.truncated
    assert len(result.http) == 3


# ---- the handlers


def test_every_handler_is_a_coroutine_function() -> None:
    assert set(HANDLERS) == {"headers", "jwt", "wellknown", "spider", "entropy"}
    assert all(inspect.iscoroutinefunction(h) for h in HANDLERS.values())
