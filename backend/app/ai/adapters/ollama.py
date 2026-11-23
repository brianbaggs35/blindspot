"""Ollama, local or cloud: `/api/tags` lists the models and `/api/show` says what each can do
(https://docs.ollama.com/api/tags and https://docs.ollama.com/api-reference/show-model-details)."""

import asyncio

import httpx2
from pydantic import BaseModel, ConfigDict, ValidationError

from app.ai.adapters.types import DiscoveredModel, Failure, UpstreamError

SHOWN_AT_ONCE = 8
OUR_NAMES = {"tools": "tools", "thinking": "thinking", "vision": "vision"}


class Tag(BaseModel):
    """One entry of `/api/tags`."""

    model_config = ConfigDict(extra="ignore")

    name: str


class Tags(BaseModel):
    """The answer of `/api/tags`."""

    model_config = ConfigDict(extra="ignore")

    models: list[Tag]


class Shown(BaseModel):
    """What `/api/show` says about one model; both parts may be missing on old servers."""

    model_config = ConfigDict(extra="ignore")

    capabilities: list[str] = []
    model_info: dict[str, object] = {}


def context_length(info: dict[str, object]) -> int | None:
    """The context window, which Ollama files under `<architecture>.context_length`."""
    for name, value in info.items():
        if name.endswith(".context_length") and isinstance(value, int) and value > 0:
            return value
    return None


def describe(name: str, shown: Shown | None) -> DiscoveredModel:
    """One model. Without `/api/show` the capabilities are not known, which is not the same as
    having none."""
    if shown is None:
        return DiscoveredModel(model_id=name, display_name=name)
    return DiscoveredModel(
        model_id=name,
        display_name=name,
        context_tokens=context_length(shown.model_info),
        capabilities=tuple(OUR_NAMES[one] for one in shown.capabilities if one in OUR_NAMES),
    )


def is_text_model(shown: Shown | None) -> bool:
    """Embedding-only models cannot run an agent."""
    return shown is None or not shown.capabilities or "completion" in shown.capabilities


class OllamaAdapter:
    """Lists the models of an Ollama server."""

    def __init__(self, base_url: str, api_key: str | None, http_client: httpx2.AsyncClient) -> None:
        self._base_url = base_url
        self._client = http_client
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def _send(self, method: str, path: str, body: dict[str, str] | None = None) -> object:
        try:
            answer = await self._client.request(
                method, f"{self._base_url}{path}", headers=self._headers, json=body
            )
        except httpx2.HTTPError:
            raise UpstreamError(Failure.UNREACHABLE, "Ollama could not be reached.") from None
        if answer.status_code in (401, 403):
            raise UpstreamError(Failure.KEY_REJECTED, "Ollama did not accept the key.")
        if answer.status_code == 404:
            raise UpstreamError(
                Failure.NOT_FOUND, "That address does not look like an Ollama server."
            )
        if answer.status_code >= 400:
            raise UpstreamError(
                Failure.PROVIDER_ERROR, f"Ollama answered with status {answer.status_code}."
            )
        try:
            return answer.json()
        except ValueError:
            raise UpstreamError(
                Failure.BAD_RESPONSE, "Ollama answered with something unexpected."
            ) from None

    async def _show(self, name: str, gate: asyncio.Semaphore) -> Shown | None:
        async with gate:
            try:
                return Shown.model_validate(await self._send("POST", "/api/show", {"model": name}))
            except UpstreamError, ValidationError:
                return None  # one model's details are not worth failing the whole list for

    async def list_models(self) -> list[DiscoveredModel]:
        """Every model, with what `/api/show` says about it."""
        try:
            tags = Tags.model_validate(await self._send("GET", "/api/tags"))
        except ValidationError:
            raise UpstreamError(
                Failure.BAD_RESPONSE, "Ollama answered with something unexpected."
            ) from None
        gate = asyncio.Semaphore(SHOWN_AT_ONCE)
        names = sorted(one.name for one in tags.models)
        shown = await asyncio.gather(*(self._show(name, gate) for name in names))
        return [
            describe(name, one)
            for name, one in zip(names, shown, strict=True)
            if is_text_model(one)
        ]
