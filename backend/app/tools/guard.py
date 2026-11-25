"""The scope guard: whether the targets of a tool call are inside what the pentest allows.

Plain code decides this, never a model. Every `target` value of a call is read as a web address, a
host (with or without a port), an address or an address range. A name is looked up, and every
address it has must be allowed (see `CompiledScope.allows`). Loopback (the app's own container),
the cloud metadata addresses and the other addresses that are never reachable are refused whatever
the scope says. Whatever cannot be read, looked up or matched is refused: the guard fails closed.

A tool that scans a host or a range does more than a web request to one address does, so it needs
the whole host or range in scope, for every port and both web schemes. A scope line limited to one
web address (`https://app.example.com/shop`) allows requests to that address, not a port scan of
the host. The refusal says so.

`check_url` is for the runner to ask again about every redirect a response sends.
"""

import ipaddress
from collections.abc import Sequence
from urllib.parse import urlsplit

from app.ai.netguard import Resolver, never_reachable_in, system_resolver
from app.pentests.scope import (
    MIN_V4_PREFIX,
    MIN_V6_PREFIX,
    NOT_IN_SCOPE,
    CompiledScope,
    Decision,
    Entry,
    Network,
)

# Any port will do for a host that must be in scope as a whole: it is checked on this one.
_ANY_PORT = 65535
_WHOLE_HOST = (
    "The whole host must be in scope, on every port, to run a tool that scans a host. "
    "Add it to the scope without a web address or port."
)


def _brackets(host: str) -> str:
    return f"[{host}]" if ":" in host else host


def _web(scheme: str, host: str, port: int) -> str:
    return f"{scheme}://{_brackets(host)}:{port}/"


async def _addresses(host: str, port: int, resolver: Resolver) -> list[str] | Decision:
    """Every address a name has. A literal address needs no lookup. A name that cannot be looked
    up, or has no address, is refused."""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return []
    try:
        found = await resolver(host, port)
    except OSError, UnicodeError:
        return Decision(False, f"{host} could not be looked up, so it cannot be checked")
    if not found:
        return Decision(False, f"{host} has no address, so it cannot be checked")
    return found


async def _allowed_on(
    scope: CompiledScope, host: str, port: int, schemes: Sequence[str], resolver: Resolver
) -> Decision:
    found = await _addresses(host, port, resolver)
    if isinstance(found, Decision):
        return found
    for scheme in schemes:
        decision = scope.allows(_web(scheme, host, port), found)
        if not decision.allowed:
            return decision
    return Decision(True, "In scope")


async def check_url(
    scope: CompiledScope, url: str, resolver: Resolver = system_resolver
) -> Decision:
    """Whether a request to a web address may be sent. Ask for the first request and again for
    every redirect it is sent to."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return Decision(False, "The address is not valid")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return Decision(False, "Only http and https addresses can be tested")
    found = await _addresses(
        parts.hostname, port or (443 if parts.scheme == "https" else 80), resolver
    )
    if isinstance(found, Decision):
        return found
    return scope.allows(url, found)


def _covers_network(entry: Entry, network: Network) -> bool:
    """Whether a scope line allows a whole range on every port: an address or a range with no
    scheme, port or path limit."""
    if entry.port is not None or entry.scheme is not None or entry.prefix != "/":
        return False
    if entry.network is not None and entry.network.version == network.version:
        return network.subnet_of(entry.network)  # pyright: ignore[reportArgumentType]
    return entry.address is not None and network == ipaddress.ip_network(entry.address)


def _overlaps(entry: Entry, network: Network) -> bool:
    if entry.network is not None and entry.network.version == network.version:
        return network.overlaps(entry.network)  # pyright: ignore[reportArgumentType]
    return (
        entry.address is not None
        and entry.address.version == network.version
        and entry.address in network
    )


def _check_network(scope: CompiledScope, network: Network) -> Decision:
    minimum = MIN_V4_PREFIX if network.version == 4 else MIN_V6_PREFIX
    if network.prefixlen < minimum:
        return Decision(False, f"{network} is a wider range than a scope may hold")
    if (bad := never_reachable_in(network)) is not None:
        return Decision(False, f"{bad} is never reachable from here")
    for entry in scope.out_of_scope:
        if _overlaps(entry, network):
            return Decision(False, f"{network} includes {entry.text}, which is out of scope")
    if any(_covers_network(entry, network) for entry in scope.in_scope):
        return Decision(True, "In scope")
    return Decision(False, f"{network} is not in scope as a whole. {_WHOLE_HOST}")


async def check_target(
    scope: CompiledScope, target: str, resolver: Resolver = system_resolver
) -> Decision:
    """Whether one target value may be touched."""
    if "://" in target:
        return await check_url(scope, target, resolver)
    if "/" in target:
        try:
            network = ipaddress.ip_network(target, strict=False)
        except ValueError:
            return Decision(False, f"{target} is not an address range")
        return _check_network(scope, network)
    try:
        host, port = _host_and_port(target)
    except ValueError:
        return Decision(False, f"{target} is not a host, an address or a web address")
    decision = await _allowed_on(scope, host, port or _ANY_PORT, ("http", "https"), resolver)
    if not decision.allowed and port is None and decision.reason == NOT_IN_SCOPE:
        return Decision(False, f"{host} is not in scope. {_WHOLE_HOST}")
    return decision


def _host_and_port(target: str) -> tuple[str, int | None]:
    """The host and port of `host`, `host:port`, `[v6]:port` or a bare IPv6 address."""
    try:
        return str(ipaddress.ip_address(target)), None
    except ValueError:
        pass
    parts = urlsplit(f"//{target}")
    host, port = parts.hostname, parts.port
    if not host or (port is not None and port == 0):
        raise ValueError(target)
    return host, port


async def check_targets(
    scope: CompiledScope, targets: Sequence[str], resolver: Resolver = system_resolver
) -> Decision:
    """Whether every target of a call may be touched. The first one that may not is the answer, so
    the reason names it."""
    for target in targets:
        decision = await check_target(scope, target, resolver)
        if not decision.allowed:
            return Decision(False, f"{target}: {decision.reason}")
    return Decision(True, "Every target is in scope")
