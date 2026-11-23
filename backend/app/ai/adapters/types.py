"""What every adapter returns, and the one error it raises."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class Failure(StrEnum):
    """Why a call to a provider failed, in terms that tell the person what to do."""

    KEY_REJECTED = "key_rejected"
    UNREACHABLE = "unreachable"
    RATE_LIMITED = "rate_limited"
    NOT_FOUND = "not_found"
    PROVIDER_ERROR = "provider_error"
    BAD_RESPONSE = "bad_response"


class UpstreamError(Exception):
    """A provider refused, was not reachable, or answered with something unusable. `detail` is
    safe to show: it never contains the key or the raw response body."""

    def __init__(self, failure: Failure, detail: str) -> None:
        super().__init__(detail)
        self.failure = failure
        self.detail = detail


@dataclass(frozen=True)
class DiscoveredModel:
    """A model the provider says this account can use."""

    model_id: str
    display_name: str
    context_tokens: int | None = None
    max_output_tokens: int | None = None
    capabilities: tuple[str, ...] = field(default_factory=tuple)


class Adapter(Protocol):
    """What the app needs from a provider apart from running prompts."""

    async def list_models(self) -> list[DiscoveredModel]:
        """The models the account can use. Also the connection test: it needs the address, the
        key and the network to be right."""
        ...
