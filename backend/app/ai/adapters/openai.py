"""OpenAI: the Models API, through the official SDK."""

import httpx2
import openai

from app.ai.adapters.types import DiscoveredModel, Failure, UpstreamError

BAD = "OpenAI answered with something unexpected."

# OpenAI's list says nothing about what a model can do or how big it is. The catalog and the
# administrator fill that in, so only tools are assumed for the families the app supports.
CHAT_FAMILIES = ("gpt-",)
NOT_FOR_CHAT = ("-audio", "-realtime", "-transcribe", "-tts", "-image", "-search", "-embedding")


def client_for(base_url: str, api_key: str, http_client: httpx2.AsyncClient) -> openai.AsyncOpenAI:
    """An SDK client that uses our HTTP client and does its own bounded retries."""
    return openai.AsyncOpenAI(
        api_key=api_key, base_url=base_url, http_client=http_client, max_retries=2
    )


def is_chat_model(model_id: str) -> bool:
    """Whether the id looks like a text model an agent can use (the list also has audio, image
    and embedding models)."""
    return model_id.startswith(CHAT_FAMILIES) and not any(word in model_id for word in NOT_FOR_CHAT)


class OpenAIAdapter:
    """Lists the models of an OpenAI account."""

    def __init__(self, client: openai.AsyncOpenAI) -> None:
        self._client = client

    async def list_models(self) -> list[DiscoveredModel]:
        """The text models, sorted by id."""
        try:
            listed = [one.id async for one in self._client.models.list()]
        except openai.APIError as error:
            raise translate(error) from None
        except AttributeError, TypeError, ValueError:
            # See the Anthropic adapter: a 200 that is not JSON breaks the SDK's page parser.
            raise UpstreamError(Failure.BAD_RESPONSE, BAD) from None
        return [
            DiscoveredModel(model_id=one, display_name=one, capabilities=("tools",))
            for one in sorted(listed)
            if is_chat_model(one)
        ]


def translate(error: openai.APIError) -> UpstreamError:
    """The SDK's errors, as ours; only the status is passed on."""
    if isinstance(error, openai.APITimeoutError | openai.APIConnectionError):
        return UpstreamError(Failure.UNREACHABLE, "OpenAI could not be reached.")
    if isinstance(error, openai.AuthenticationError | openai.PermissionDeniedError):
        return UpstreamError(Failure.KEY_REJECTED, "OpenAI did not accept the key.")
    if isinstance(error, openai.RateLimitError):
        return UpstreamError(Failure.RATE_LIMITED, "OpenAI is limiting requests; try again soon.")
    if isinstance(error, openai.NotFoundError):
        return UpstreamError(Failure.NOT_FOUND, "That address does not look like the OpenAI API.")
    if isinstance(error, openai.APIStatusError):
        return UpstreamError(
            Failure.PROVIDER_ERROR, f"OpenAI answered with status {error.status_code}."
        )
    return UpstreamError(Failure.BAD_RESPONSE, BAD)
