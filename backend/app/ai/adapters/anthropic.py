"""Anthropic: the Models API, through the official SDK."""

import anthropic
import httpx2
from anthropic.types import ModelInfo

from app.ai.adapters.types import DiscoveredModel, Failure, UpstreamError

PAGE = 100
BAD = "Anthropic answered with something unexpected."


def client_for(
    base_url: str, api_key: str, http_client: httpx2.AsyncClient
) -> anthropic.AsyncAnthropic:
    """An SDK client that uses our HTTP client (so redirects, timeouts and the transport are
    ours) and does its own bounded retries on rate limits and server errors."""
    return anthropic.AsyncAnthropic(
        api_key=api_key, base_url=base_url, http_client=http_client, max_retries=2
    )


def supported(capabilities: object, name: str) -> bool:
    """Whether the API says a capability is supported. A missing part counts as not supported:
    the list is allowed to say less than the SDK's types promise."""
    return bool(getattr(getattr(capabilities, name, None), "supported", False))


def capabilities_of(info: ModelInfo) -> tuple[str, ...]:
    """The capabilities the API reports, in the names the app uses. Every Claude model that can
    be listed accepts tools."""
    found = ["tools"]
    if supported(info.capabilities, "thinking"):
        found.append("thinking")
    if supported(info.capabilities, "image_input"):
        found.append("vision")
    return tuple(found)


def describe(info: ModelInfo) -> DiscoveredModel:
    """One listed model."""
    return DiscoveredModel(
        model_id=info.id,
        display_name=info.display_name or info.id,
        context_tokens=info.max_input_tokens,
        max_output_tokens=info.max_tokens,
        capabilities=capabilities_of(info),
    )


class AnthropicAdapter:
    """Lists the models of an Anthropic account."""

    def __init__(self, client: anthropic.AsyncAnthropic) -> None:
        self._client = client

    async def list_models(self) -> list[DiscoveredModel]:
        """Every model, following the pages."""
        try:
            return [describe(info) async for info in self._client.models.list(limit=PAGE)]
        except anthropic.APIError as error:
            raise translate(error) from None
        except AttributeError, TypeError, ValueError:
            # An address that answers 200 with something that is not JSON makes the SDK's page
            # parser fail with one of these instead of its own error.
            raise UpstreamError(Failure.BAD_RESPONSE, BAD) from None


def translate(error: anthropic.APIError) -> UpstreamError:
    """The SDK's errors, as ours. The SDK's message can quote the response, so only the status
    is passed on."""
    if isinstance(error, anthropic.APITimeoutError | anthropic.APIConnectionError):
        return UpstreamError(Failure.UNREACHABLE, "Anthropic could not be reached.")
    if isinstance(error, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return UpstreamError(Failure.KEY_REJECTED, "Anthropic did not accept the key.")
    if isinstance(error, anthropic.RateLimitError):
        return UpstreamError(
            Failure.RATE_LIMITED, "Anthropic is limiting requests; try again soon."
        )
    if isinstance(error, anthropic.NotFoundError):
        return UpstreamError(
            Failure.NOT_FOUND, "That address does not look like the Anthropic API."
        )
    if isinstance(error, anthropic.APIStatusError):
        return UpstreamError(
            Failure.PROVIDER_ERROR, f"Anthropic answered with status {error.status_code}."
        )
    return UpstreamError(Failure.BAD_RESPONSE, BAD)
