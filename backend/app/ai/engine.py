"""The Pydantic AI model for a stored provider, with prompt caching switched on, and the usage
of a run in the app's own terms."""

import httpx2
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.models.openai import (
    OpenAIChatModel,
    OpenAIResponsesModel,
    OpenAIResponsesModelSettings,
)
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage

from app.ai.adapters.anthropic import client_for as anthropic_client
from app.ai.adapters.factory import base_url_of
from app.ai.adapters.openai import client_for as openai_client
from app.ai.kinds import ProviderKind
from app.ai.pricing import Usage
from app.db.models import AiProvider


def build_model(provider: AiProvider, model_id: str, http_client: httpx2.AsyncClient) -> Model:
    """The model to hand to an agent. Anthropic and OpenAI use their own APIs (Messages and
    Responses); Ollama, local or cloud, uses its OpenAI-compatible chat endpoint."""
    kind = ProviderKind(provider.kind)
    base = base_url_of(provider)
    key = provider.api_key or ""
    if kind is ProviderKind.ANTHROPIC:
        client = anthropic_client(base, key, http_client)
        return AnthropicModel(model_id, provider=AnthropicProvider(anthropic_client=client))
    if kind is ProviderKind.OPENAI:
        client = openai_client(base, key, http_client)
        return OpenAIResponsesModel(model_id, provider=OpenAIProvider(openai_client=client))
    # Ollama needs no key, but the SDK insists on a non-empty one.
    client = openai_client(f"{base}/v1", key or "ollama", http_client)
    return OpenAIChatModel(model_id, provider=OpenAIProvider(openai_client=client))


def cache_settings(kind: ProviderKind, cache_key: str | None = None) -> ModelSettings:
    """Settings that make the provider cache the static start of every prompt: the instructions
    and the tool definitions, then the conversation so far. `cache_key` groups the calls of one
    run on OpenAI, so they land on the same cache."""
    if kind is ProviderKind.ANTHROPIC:
        return AnthropicModelSettings(
            anthropic_cache_instructions=True,
            anthropic_cache_tool_definitions=True,
            anthropic_cache_messages=True,
        )
    if kind is ProviderKind.OPENAI:
        settings = OpenAIResponsesModelSettings()
        if cache_key is not None:
            settings["openai_prompt_cache_key"] = cache_key
        return settings
    return ModelSettings()


def usage_of(run: RunUsage) -> Usage:
    """A run's usage, split the way the price catalog needs it: Pydantic AI counts cached tokens
    inside `input_tokens`, so they are taken out to leave the uncached prompt."""
    long_writes = run.cache_write_1h_tokens
    short_writes = max(run.cache_write_tokens - long_writes, 0)
    uncached = max(run.input_tokens - run.cache_read_tokens - run.cache_write_tokens, 0)
    return Usage(
        input_tokens=uncached,
        output_tokens=run.output_tokens,
        cache_read_tokens=run.cache_read_tokens,
        cache_write_tokens=short_writes,
        cache_write_long_tokens=long_writes,
        thinking_tokens=run.output_reasoning_tokens,
    )
