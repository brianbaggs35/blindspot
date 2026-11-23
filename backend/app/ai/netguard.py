"""Keep a provider's address from reaching what it should not (server-side request forgery).

A provider's base URL is typed by a person, and the server then calls it with a secret key. So
the address is checked when it is saved and again before it is used (a name can change what it
points to). Hosted providers must resolve to public addresses only. Only a provider on this
machine or network (local Ollama) may use a private address, and even that never reaches a
link-local address, where cloud metadata services live, nor an unspecified, multicast or
reserved one.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from typing import Final
from urllib.parse import SplitResult, urlsplit

from app.ai.kinds import KINDS, ProviderKind

Address = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int], Awaitable[list[str]]]

# Metadata services outside the link-local range.
_METADATA: Final[frozenset[Address]] = frozenset(
    {
        ipaddress.IPv4Address(bytes([100, 100, 100, 200])),  # Alibaba Cloud
        ipaddress.IPv6Address((0xFD00_0EC2 << 96) | 0x254),  # AWS, over IPv6
    }
)


class BaseUrlRejected(ValueError):  # noqa: N818  # reads as a sentence at the call sites
    """The address is not allowed. The message is safe to show to the person who typed it."""


async def system_resolver(host: str, port: int) -> list[str]:
    """Every address the name has, from the system's resolver."""
    found = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({str(item[4][0]) for item in found})


def _plain(address: Address) -> Address:
    """An IPv4 address written as IPv6 (::ffff:10.0.0.1) is judged as the IPv4 address."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _refuse_always(address: Address) -> str | None:
    if address in _METADATA or address.is_link_local:
        return "a link-local or cloud metadata address"
    # ::1 is in IPv6's reserved block but is only a loopback address, judged with the private ones.
    if (
        address.is_unspecified
        or address.is_multicast
        or (address.is_reserved and not address.is_loopback)
    ):
        return "an address that is not for connections"
    return None


def _why_not(address: Address, *, allow_private: bool) -> str | None:
    address = _plain(address)
    if (reason := _refuse_always(address)) is not None:
        return reason
    if allow_private:
        return None
    return None if address.is_global else "a private or local address"


def _parse(url: str, kind: ProviderKind) -> SplitResult:
    info = KINDS[kind]
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        raise BaseUrlRejected("That is not a valid web address") from None
    allowed = ("http", "https") if info.allows_http else ("https",)
    if parts.scheme not in allowed:
        raise BaseUrlRejected(
            f"The address must start with {' or '.join(a + '://' for a in allowed)}"
        )
    if not parts.hostname:
        raise BaseUrlRejected("The address has no host name")
    if parts.username is not None or parts.password is not None:
        raise BaseUrlRejected("The address must not contain a user name or password")
    if parts.query or parts.fragment:
        raise BaseUrlRejected("The address must not have a query or a fragment")
    if port == 0:
        raise BaseUrlRejected("The port is not valid")
    return parts


async def check_base_url(url: str, kind: ProviderKind, resolver: Resolver | None = None) -> str:
    """The address, tidied (no trailing slash), once every address it resolves to is allowed.
    Raises BaseUrlRejected with a reason otherwise."""
    parts = _parse(url, kind)
    host = parts.hostname or ""
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        literal: Address | None = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [str(literal)]
    else:
        try:
            addresses = await (resolver or system_resolver)(host, port)
        except OSError:
            raise BaseUrlRejected("That host name cannot be found") from None
    if not addresses:
        raise BaseUrlRejected("That host name cannot be found")
    allow_private = KINDS[kind].allows_private_addresses
    for text in addresses:
        reason = _why_not(ipaddress.ip_address(text), allow_private=allow_private)
        if reason is not None:
            raise BaseUrlRejected(f"That address points to {reason}, which is not allowed here")
    return url.strip().rstrip("/")
