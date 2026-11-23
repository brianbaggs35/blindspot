"""The Pydantic AI models built from stored providers: the right API, caching switched on, and
usage split the way the price catalog needs it."""

import json
from typing import Any

import httpx2
import pytest
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.usage import RunUsage

from app.ai.engine import build_model, cache_settings, usage_of
from app.ai.kinds import KINDS, ProviderKind
from app.ai.pricing import Usage
from app.db.models import AiProvider

INSTRUCTIONS = "Be brief and exact. " * 400


def provider(kind: ProviderKind, key: str | None = "the-key") -> AiProvider:
    return AiProvider(
        kind=kind.value, name=kind.value, base_url=KINDS[kind].default_base_url, api_key=key
    )


ANTHROPIC_ANSWER: dict[str, Any] = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-opus-5-5",
    "content": [{"type": "text", "text": "done"}],
    "stop_reason": "end_turn",
    "usage": {
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_read_input_tokens": 20,
        "cache_creation_input_tokens": 150,
        "cache_creation": {"ephemeral_5m_input_tokens": 100, "ephemeral_1h_input_tokens": 50},
        "output_tokens_details": {"thinking_tokens": 3},
    },
}
OPENAI_ANSWER: dict[str, Any] = {
    "id": "resp_1",
    "object": "response",
    "created_at": 1,
    "model": "gpt-6-luna",
    "status": "completed",
    "output": [
        {
            "type": "message",
            "id": "msg_1",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "done", "annotations": []}],
        }
    ],
    "parallel_tool_calls": True,
    "tool_choice": "auto",
    "tools": [],
    "usage": {
        "input_tokens": 300,
        "input_tokens_details": {"cached_tokens": 128, "cache_write_tokens": 100},
        "output_tokens": 20,
        "output_tokens_details": {"reasoning_tokens": 7},
        "total_tokens": 320,
    },
}
OLLAMA_ANSWER: dict[str, Any] = {
    "id": "chat_1",
    "object": "chat.completion",
    "created": 1,
    "model": "llama3.3",
    "choices": [
        {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "done"}}
    ],
    "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
}


async def run(
    kind: ProviderKind, answer: dict[str, Any], key: str | None = "the-key"
) -> tuple[httpx2.Request, dict[str, object], RunUsage]:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=answer)

    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    model = build_model(provider(kind, key), "some-model", http)
    agent = Agent(model, instructions=INSTRUCTIONS)
    result = await agent.run("hello", model_settings=cache_settings(kind, cache_key="run-7"))
    await http.aclose()
    return seen[0], json.loads(seen[0].content), result.usage


async def test_anthropic_uses_the_messages_api_with_the_start_of_the_prompt_cached() -> None:
    request, body, usage = await run(ProviderKind.ANTHROPIC, ANTHROPIC_ANSWER)
    assert request.url == "https://api.anthropic.com/v1/messages"
    assert request.headers["authorization"] == "Bearer the-key"
    assert body["system"][0]["cache_control"]["type"] == "ephemeral"  # type: ignore[index]
    assert body["messages"][0]["content"][0]["cache_control"]["type"] == "ephemeral"  # type: ignore[index]
    assert usage_of(usage) == Usage(
        input_tokens=10,
        output_tokens=5,
        cache_read_tokens=20,
        cache_write_tokens=100,
        cache_write_long_tokens=50,
        thinking_tokens=3,
    )


async def test_openai_uses_the_responses_api_and_groups_a_runs_calls_for_the_cache() -> None:
    request, body, usage = await run(ProviderKind.OPENAI, OPENAI_ANSWER)
    assert request.url == "https://api.openai.com/v1/responses"
    assert request.headers["authorization"] == "Bearer the-key"
    assert body["prompt_cache_key"] == "run-7"
    assert usage_of(usage) == Usage(
        input_tokens=72,  # 300 minus the 128 read and the 100 written
        output_tokens=20,
        cache_read_tokens=128,
        cache_write_tokens=100,
        thinking_tokens=7,
    )


@pytest.mark.parametrize(
    ("kind", "key", "sent"),
    [
        (ProviderKind.OLLAMA_LOCAL, None, "Bearer ollama"),
        (ProviderKind.OLLAMA_CLOUD, "cloud-key", "Bearer cloud-key"),
    ],
)
async def test_ollama_uses_its_openai_compatible_chat_api(
    kind: ProviderKind, key: str | None, sent: str
) -> None:
    request, body, usage = await run(kind, OLLAMA_ANSWER, key)
    assert str(request.url) == f"{KINDS[kind].default_base_url}/v1/chat/completions"
    assert request.headers["authorization"] == sent
    assert "prompt_cache_key" not in body
    assert usage_of(usage) == Usage(input_tokens=12, output_tokens=4)


def test_the_model_classes_match_the_kind() -> None:
    http = httpx2.AsyncClient()
    assert isinstance(build_model(provider(ProviderKind.ANTHROPIC), "m", http), AnthropicModel)
    assert isinstance(build_model(provider(ProviderKind.OPENAI), "m", http), OpenAIResponsesModel)
    assert isinstance(
        build_model(provider(ProviderKind.OLLAMA_LOCAL, None), "m", http), OpenAIChatModel
    )
    assert isinstance(build_model(provider(ProviderKind.OLLAMA_CLOUD), "m", http), OpenAIChatModel)


def test_cache_settings_per_kind() -> None:
    anthropic: dict[str, object] = dict(cache_settings(ProviderKind.ANTHROPIC, "ignored"))
    assert anthropic == {
        "anthropic_cache_instructions": True,
        "anthropic_cache_tool_definitions": True,
        "anthropic_cache_messages": True,
    }
    assert dict(cache_settings(ProviderKind.OPENAI, "run-1")) == {
        "openai_prompt_cache_key": "run-1"
    }
    assert dict(cache_settings(ProviderKind.OPENAI)) == {}
    assert dict(cache_settings(ProviderKind.OLLAMA_LOCAL)) == {}


def test_usage_never_goes_negative_when_a_provider_reports_oddly() -> None:
    odd = RunUsage(
        input_tokens=5, cache_read_tokens=9, cache_write_tokens=4, cache_write_1h_tokens=6
    )
    assert usage_of(odd) == Usage(
        cache_read_tokens=9, cache_write_tokens=0, cache_write_long_tokens=6
    )
