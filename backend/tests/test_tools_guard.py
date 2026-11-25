"""The scope guard: every target is looked up and checked, and anything unclear is refused."""

import ipaddress

import pytest

from app.ai.netguard import never_reachable_in
from app.pentests.scope import CompiledScope
from app.tools.guard import check_target, check_targets, check_url

SHOP = "93.184.216.34"
OTHER = "93.184.216.99"
PRIVATE = "10.0.0.5"


def scope(*in_scope: str, out: tuple[str, ...] = (), paths: tuple[str, ...] = ()) -> CompiledScope:
    return CompiledScope.compile(in_scope, out, paths)


def resolving(**names: list[str]):
    async def resolve(host: str, port: int) -> list[str]:
        assert port
        return names[host]

    return resolve


async def unreachable(host: str, port: int) -> list[str]:
    raise OSError(f"{host}:{port} not found")


async def nothing(host: str, port: int) -> list[str]:
    assert host
    assert port
    return []


WHOLE_SHOP = scope("shop.example.com")
LOOKUP = resolving(**{"shop.example.com": [SHOP], "other.example.com": [OTHER]})


@pytest.mark.parametrize(
    "target",
    [
        "https://shop.example.com/cart",
        "http://shop.example.com:8080/",
        "shop.example.com",
        "shop.example.com:8443",
    ],
)
async def test_what_is_in_scope_is_allowed(target: str) -> None:
    decision = await check_target(WHOLE_SHOP, target, LOOKUP)
    assert decision.allowed, decision.reason


@pytest.mark.parametrize(
    "target", ["https://other.example.com/", "other.example.com", "other.example.com:443"]
)
async def test_what_is_not_in_scope_is_refused(target: str) -> None:
    decision = await check_target(WHOLE_SHOP, target, LOOKUP)
    assert not decision.allowed


async def test_a_host_that_is_in_scope_only_as_a_web_address_cannot_be_scanned() -> None:
    narrow = scope("https://shop.example.com/app")
    assert (await check_target(narrow, "https://shop.example.com/app/x", LOOKUP)).allowed
    scanned = await check_target(narrow, "shop.example.com", LOOKUP)
    assert not scanned.allowed
    assert "whole host" in scanned.reason


async def test_a_host_in_scope_on_one_port_cannot_be_scanned_on_all() -> None:
    narrow = scope("shop.example.com:8443")
    assert not (await check_target(narrow, "shop.example.com", LOOKUP)).allowed
    assert (await check_target(narrow, "shop.example.com:8443", LOOKUP)).allowed
    assert not (await check_target(narrow, "shop.example.com:22", LOOKUP)).allowed


async def test_a_name_with_one_address_outside_is_refused() -> None:
    mixed = resolving(**{"shop.example.com": [SHOP, OTHER]})
    decision = await check_target(scope(f"{SHOP}"), "https://shop.example.com/", mixed)
    assert not decision.allowed


async def test_a_name_that_points_at_loopback_or_metadata_is_refused() -> None:
    for address in ("127.0.0.1", "::1", "169.254.169.254", "fe80::1"):
        lookup = resolving(**{"shop.example.com": [address]})
        decision = await check_target(WHOLE_SHOP, "https://shop.example.com/", lookup)
        assert not decision.allowed, address
        assert "never reachable" in decision.reason


@pytest.mark.parametrize(
    "target", ["127.0.0.1", "http://127.0.0.1:8000/", "[::1]:80", "::1", "169.254.169.254"]
)
async def test_literal_addresses_that_are_never_reachable_are_refused(target: str) -> None:
    everything = scope("10.0.0.0/16")
    assert not (await check_target(everything, target, LOOKUP)).allowed


async def test_a_name_that_cannot_be_looked_up_is_refused() -> None:
    decision = await check_target(WHOLE_SHOP, "https://shop.example.com/", unreachable)
    assert not decision.allowed
    assert "could not be looked up" in decision.reason
    assert not (await check_target(WHOLE_SHOP, "shop.example.com", unreachable)).allowed


async def test_a_name_with_no_address_is_refused() -> None:
    decision = await check_target(WHOLE_SHOP, "shop.example.com", nothing)
    assert not decision.allowed
    assert "no address" in decision.reason


async def test_a_literal_address_is_not_looked_up() -> None:
    inside = scope(f"{PRIVATE}")
    assert (await check_target(inside, PRIVATE, unreachable)).allowed
    assert (await check_target(inside, f"http://{PRIVATE}:81/", unreachable)).allowed
    assert (await check_target(scope("2001:db8::7"), "2001:db8::7", unreachable)).allowed
    assert (await check_target(scope("2001:db8::7"), "[2001:db8::7]:80", unreachable)).allowed


async def test_out_of_scope_wins_and_excluded_paths_are_kept_out() -> None:
    hard = scope("shop.example.com", out=("admin.shop.example.com",), paths=("/billing",))
    lookup = resolving(**{"admin.shop.example.com": [SHOP], "shop.example.com": [SHOP]})
    assert not (await check_target(hard, "https://admin.shop.example.com/", lookup)).allowed
    assert not (await check_target(hard, "https://shop.example.com/Billing/pay", lookup)).allowed
    assert (await check_target(hard, "https://shop.example.com/shop", lookup)).allowed


@pytest.mark.parametrize(
    "target",
    ["http://", "ftp://shop.example.com/", "http://shop.example.com:99999/", "http://[::1/"],
)
async def test_web_addresses_that_make_no_sense_are_refused(target: str) -> None:
    assert not (await check_target(WHOLE_SHOP, target, LOOKUP)).allowed


@pytest.mark.parametrize("target", ["a:b:c", "shop.example.com:0", ":80", "1.2.3.4/33", "x/y"])
async def test_targets_that_are_not_understood_are_refused(target: str) -> None:
    decision = await check_target(WHOLE_SHOP, target, LOOKUP)
    assert not decision.allowed


async def test_a_range_must_be_in_scope_as_a_whole() -> None:
    lab = scope("10.0.0.0/24", "192.168.1.7")
    assert (await check_target(lab, "10.0.0.0/24", LOOKUP)).allowed
    assert (await check_target(lab, "10.0.0.64/26", LOOKUP)).allowed
    assert (await check_target(lab, "192.168.1.7/32", LOOKUP)).allowed
    assert not (await check_target(lab, "10.0.1.0/24", LOOKUP)).allowed
    assert not (await check_target(lab, "10.0.0.0/23", LOOKUP)).allowed
    assert not (await check_target(lab, "192.168.1.0/30", LOOKUP)).allowed
    assert not (await check_target(lab, "2001:db8::/64", LOOKUP)).allowed


async def test_a_range_cannot_be_wider_than_a_scope_may_be() -> None:
    wide = await check_target(scope("10.0.0.0/16"), "10.0.0.0/8", LOOKUP)
    assert not wide.allowed
    assert "wider" in wide.reason
    assert not (await check_target(scope("2001:db8::/48"), "2001:db8::/32", LOOKUP)).allowed
    assert (await check_target(scope("2001:db8::/48"), "2001:db8::/64", LOOKUP)).allowed


async def test_a_range_that_holds_an_address_never_reachable_is_refused() -> None:
    for network in ("127.0.0.0/24", "169.254.0.0/24", "100.100.100.0/24", "0.0.0.0/16"):
        everything = scope("10.0.0.0/16")
        decision = await check_target(everything, network, LOOKUP)
        assert not decision.allowed, network
        assert "never reachable" in decision.reason


async def test_a_range_that_overlaps_out_of_scope_is_refused() -> None:
    lab = scope("10.0.0.0/16", out=("10.0.5.0/24", "10.0.9.9"))
    assert not (await check_target(lab, "10.0.5.0/25", LOOKUP)).allowed
    assert not (await check_target(lab, "10.0.8.0/22", LOOKUP)).allowed
    assert (await check_target(lab, "10.0.6.0/24", LOOKUP)).allowed
    # An out-of-scope range of the other kind of address cannot overlap.
    mixed = scope("10.0.0.0/16", "2001:db8::/48", out=("2001:db8::/64", "2001:db8::5"))
    assert (await check_target(mixed, "10.0.1.0/24", LOOKUP)).allowed
    assert not (await check_target(mixed, "2001:db8::/80", LOOKUP)).allowed


async def test_a_range_needs_a_scope_line_with_no_port_scheme_or_path_limit() -> None:
    limited = scope("http://10.0.0.0/24", "10.1.0.5:8080")
    assert not (await check_target(limited, "10.0.0.0/24", LOOKUP)).allowed
    assert not (await check_target(limited, "10.1.0.5/32", LOOKUP)).allowed


async def test_every_target_of_a_call_must_pass_and_the_first_failure_is_named() -> None:
    assert (await check_targets(WHOLE_SHOP, ["shop.example.com"], LOOKUP)).allowed
    assert (await check_targets(WHOLE_SHOP, [], LOOKUP)).allowed
    decision = await check_targets(
        WHOLE_SHOP, ["shop.example.com", "other.example.com", "x.invalid"], LOOKUP
    )
    assert not decision.allowed
    assert decision.reason.startswith("other.example.com: ")


async def test_a_redirect_is_checked_like_a_first_request() -> None:
    assert (await check_url(WHOLE_SHOP, "https://shop.example.com/login", LOOKUP)).allowed
    assert not (await check_url(WHOLE_SHOP, "https://other.example.com/", LOOKUP)).allowed
    assert not (await check_url(WHOLE_SHOP, "http://127.0.0.1/admin", LOOKUP)).allowed
    assert not (await check_url(WHOLE_SHOP, "http://169.254.169.254/latest", LOOKUP)).allowed
    assert not (await check_url(WHOLE_SHOP, "ftp://shop.example.com/", LOOKUP)).allowed
    assert not (await check_url(WHOLE_SHOP, "https://shop.example.com:xx/", LOOKUP)).allowed


async def test_the_lookup_is_made_for_the_port_the_request_uses() -> None:
    seen: list[tuple[str, int]] = []

    async def spy(host: str, port: int) -> list[str]:
        seen.append((host, port))
        return [SHOP]

    await check_url(WHOLE_SHOP, "https://shop.example.com/", spy)
    await check_url(WHOLE_SHOP, "http://shop.example.com/", spy)
    await check_url(WHOLE_SHOP, "http://shop.example.com:8080/", spy)
    assert seen == [("shop.example.com", 443), ("shop.example.com", 80), ("shop.example.com", 8080)]


def test_the_ends_and_the_metadata_addresses_of_a_range_are_looked_at() -> None:
    assert never_reachable_in(ipaddress.ip_network("10.0.0.0/24")) is None
    assert never_reachable_in(ipaddress.ip_network("100.100.100.0/24")) == ipaddress.ip_address(
        "100.100.100.200"
    )
    assert never_reachable_in(ipaddress.ip_network("127.0.0.0/30")) is not None
    assert never_reachable_in(ipaddress.ip_network("fe80::/64")) is not None
