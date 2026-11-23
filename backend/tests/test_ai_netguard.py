"""The address check for providers: what a base URL may point to."""

import pytest

from app.ai.kinds import ProviderKind
from app.ai.netguard import BaseUrlRejected, check_base_url, system_resolver

PUBLIC = "93.184.216.34"


def resolving(*addresses: str):
    async def resolve(host: str, port: int) -> list[str]:
        assert host
        assert port
        return list(addresses)

    return resolve


async def test_a_hosted_provider_at_a_public_address_is_fine() -> None:
    url = await check_base_url(
        "https://api.example.com/v1/", ProviderKind.OPENAI, resolving(PUBLIC, "2606:2800:220:1::1")
    )
    assert url == "https://api.example.com/v1"


@pytest.mark.parametrize(
    ("address", "why"),
    [
        ("127.0.0.1", "private or local"),
        ("10.0.0.5", "private or local"),
        ("192.168.1.9", "private or local"),
        ("172.16.0.1", "private or local"),
        ("100.64.0.1", "private or local"),  # shared address space
        ("::1", "private or local"),
        ("fc00::1", "private or local"),
        ("::ffff:10.0.0.1", "private or local"),  # IPv4 written as IPv6
        ("169.254.169.254", "metadata"),
        ("fe80::1", "metadata"),
        ("100.100.100.200", "metadata"),
        ("0.0.0.0", "not for connections"),  # noqa: S104  # the address being refused
        ("224.0.0.1", "not for connections"),
        ("240.0.0.1", "not for connections"),
    ],
)
async def test_a_hosted_provider_cannot_point_at_private_or_metadata_addresses(
    address: str, why: str
) -> None:
    resolver = resolving(address)
    with pytest.raises(BaseUrlRejected, match=why):
        await check_base_url("https://api.example.com", ProviderKind.ANTHROPIC, resolver)


async def test_one_bad_answer_among_good_ones_refuses_the_name() -> None:
    # A name that resolves to a public and a private address could be pointed at either.
    resolver = resolving(PUBLIC, "10.1.1.1")
    with pytest.raises(BaseUrlRejected, match="private"):
        await check_base_url("https://api.example.com", ProviderKind.OPENAI, resolver)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "192.168.1.9", "::1", "172.17.0.1"])
async def test_local_ollama_may_use_private_addresses(address: str) -> None:
    url = await check_base_url(
        "http://host.docker.internal:11434", ProviderKind.OLLAMA_LOCAL, resolving(address)
    )
    assert url == "http://host.docker.internal:11434"


@pytest.mark.parametrize("address", ["169.254.169.254", "fe80::1", "0.0.0.0", "224.0.0.1"])  # noqa: S104
async def test_local_ollama_still_cannot_reach_metadata_or_unusable_addresses(
    address: str,
) -> None:
    resolver = resolving(address)
    with pytest.raises(BaseUrlRejected, match="not allowed"):
        await check_base_url("http://ollama.lan:11434", ProviderKind.OLLAMA_LOCAL, resolver)


async def test_an_address_typed_as_an_ip_is_checked_without_a_lookup() -> None:
    async def never(host: str, port: int) -> list[str]:
        raise AssertionError(f"looked up {host}:{port}")

    assert await check_base_url("http://127.0.0.1:11434", ProviderKind.OLLAMA_LOCAL, never)
    assert await check_base_url("https://[2606:2800:220:1::1]", ProviderKind.OPENAI, never)
    with pytest.raises(BaseUrlRejected, match="private"):
        await check_base_url("https://10.0.0.1", ProviderKind.OPENAI, never)


@pytest.mark.parametrize(
    ("url", "kind", "message"),
    [
        ("http://api.example.com", ProviderKind.ANTHROPIC, "must start with https://"),
        ("ftp://ollama.lan", ProviderKind.OLLAMA_LOCAL, "http:// or https://"),
        ("api.example.com", ProviderKind.OPENAI, "must start with"),
        ("https://", ProviderKind.OPENAI, "no host name"),
        ("https://user:pw@api.example.com", ProviderKind.OPENAI, "user name or password"),
        ("https://user@api.example.com", ProviderKind.OPENAI, "user name or password"),
        ("https://api.example.com/?x=1", ProviderKind.OPENAI, "query or a fragment"),
        ("https://api.example.com/#x", ProviderKind.OPENAI, "query or a fragment"),
        ("https://api.example.com:0", ProviderKind.OPENAI, "port is not valid"),
        ("https://api.example.com:99999", ProviderKind.OPENAI, "not a valid web address"),
        ("https://[::1", ProviderKind.OPENAI, "not a valid web address"),
    ],
)
async def test_malformed_or_unsafe_addresses_are_refused(
    url: str, kind: ProviderKind, message: str
) -> None:
    resolver = resolving(PUBLIC)
    with pytest.raises(BaseUrlRejected, match=message):
        await check_base_url(url, kind, resolver)


async def test_a_name_that_cannot_be_found_is_refused() -> None:
    async def missing(host: str, port: int) -> list[str]:
        raise OSError(f"no such host {host}:{port}")

    with pytest.raises(BaseUrlRejected, match="cannot be found"):
        await check_base_url("https://nowhere.example", ProviderKind.OPENAI, missing)
    nothing = resolving()
    with pytest.raises(BaseUrlRejected, match="cannot be found"):
        await check_base_url("https://nowhere.example", ProviderKind.OPENAI, nothing)


async def test_the_system_resolver_finds_localhost() -> None:
    found = await system_resolver("localhost", 11434)
    assert set(found) & {"127.0.0.1", "::1"}
    # Used for real by the default, which is allowed here because local Ollama may be anywhere
    # on the machine.
    assert await check_base_url("http://localhost:11434", ProviderKind.OLLAMA_LOCAL)
