"""Build the adapter and the SDK clients for a stored provider."""

from collections.abc import Callable
from typing import Annotated

import httpx2
from fastapi import Depends

from app.ai.adapters.anthropic import AnthropicAdapter
from app.ai.adapters.anthropic import client_for as anthropic_client
from app.ai.adapters.ollama import OllamaAdapter
from app.ai.adapters.openai import OpenAIAdapter
from app.ai.adapters.openai import client_for as openai_client
from app.ai.adapters.types import Adapter
from app.ai.kinds import ProviderKind
from app.db.models import AiProvider

TIMEOUT = httpx2.Timeout(30.0, connect=10.0)
LIMITS = httpx2.Limits(max_connections=20, max_keepalive_connections=10)

HttpClientFactory = Callable[[], httpx2.AsyncClient]


def new_http_client() -> httpx2.AsyncClient:
    """The HTTP client every provider call uses. It never follows redirects: a provider that
    answers with one could otherwise send the key to an address the guard never checked."""
    return httpx2.AsyncClient(timeout=TIMEOUT, limits=LIMITS, follow_redirects=False)


def get_http_client_factory() -> HttpClientFactory:
    """The way to make an HTTP client (the tests replace this one)."""
    return new_http_client


HttpClientFactoryDep = Annotated[HttpClientFactory, Depends(get_http_client_factory)]


def base_url_of(provider: AiProvider) -> str:
    """The address as stored, without a trailing slash."""
    return provider.base_url.rstrip("/")


def adapter_for(provider: AiProvider, http_client: httpx2.AsyncClient) -> Adapter:
    """The adapter for the provider's kind. The key is opened here and goes no further than the
    SDK client."""
    kind = ProviderKind(provider.kind)
    key = provider.api_key
    base = base_url_of(provider)
    if kind is ProviderKind.ANTHROPIC:
        return AnthropicAdapter(anthropic_client(base, key or "", http_client))
    if kind is ProviderKind.OPENAI:
        return OpenAIAdapter(openai_client(base, key or "", http_client))
    return OllamaAdapter(base, key, http_client)
