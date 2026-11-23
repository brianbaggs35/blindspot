"""The provider adapters, with the network replaced by a fake transport."""

import json
from collections.abc import Callable

import anthropic
import httpx2
import openai
import pytest

from app.ai.adapters import anthropic as anthropic_module
from app.ai.adapters import openai as openai_module
from app.ai.adapters.anthropic import AnthropicAdapter
from app.ai.adapters.ollama import OllamaAdapter, Shown, context_length
from app.ai.adapters.openai import OpenAIAdapter, is_chat_model
from app.ai.adapters.types import DiscoveredModel, Failure, UpstreamError

Handler = Callable[[httpx2.Request], httpx2.Response]
REQUEST = httpx2.Request("GET", "https://example.com")
SECRET = "sk-secret-0123456789abcdefghijklmnop"


@pytest.fixture(autouse=True)
def quick_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """The SDKs wait between retries; the tests should not."""
    for module in ("anthropic._base_client", "openai._base_client"):
        base = __import__(module, fromlist=["x"])
        monkeypatch.setattr(base, "INITIAL_RETRY_DELAY", 0.0)
        monkeypatch.setattr(base, "MAX_RETRY_DELAY", 0.0)


def client(handler: Handler) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


def anthropic_adapter(handler: Handler) -> AnthropicAdapter:
    return AnthropicAdapter(
        anthropic_module.client_for("https://api.anthropic.com", SECRET, client(handler))
    )


def openai_adapter(handler: Handler) -> OpenAIAdapter:
    return OpenAIAdapter(
        openai_module.client_for("https://api.openai.com/v1", SECRET, client(handler))
    )


def ollama_adapter(handler: Handler, key: str | None = None) -> OllamaAdapter:
    return OllamaAdapter("http://ollama.test:11434", key, client(handler))


def capability(supported: bool) -> dict[str, bool]:
    return {"supported": supported}


def claude(model_id: str, name: str, **extra: object) -> dict[str, object]:
    return {
        "id": model_id,
        "type": "model",
        "display_name": name,
        "created_at": "2026-01-01T00:00:00Z",
        "max_input_tokens": 1_000_000,
        "max_tokens": 128_000,
        "capabilities": {
            "thinking": {"supported": True, "types": {}},
            "image_input": capability(True),
        }
        | extra,
    }


def page(models: list[dict[str, object]], *, more: bool) -> httpx2.Response:
    ids = [str(one["id"]) for one in models]
    return httpx2.Response(
        200,
        json={
            "data": models,
            "has_more": more,
            "first_id": ids[0] if ids else None,
            "last_id": ids[-1] if ids else None,
        },
    )


async def test_anthropic_lists_every_page_with_what_each_model_can_do() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if request.url.params.get("after_id") is None:
            return page([claude("claude-opus-5-5", "Claude Opus 5.5")], more=True)
        return page(
            [
                {**claude("claude-haiku-5-5", "Claude Haiku 5.5"), "capabilities": {}},
                {**claude("claude-old", ""), "capabilities": None},
            ],
            more=False,
        )

    found = await anthropic_adapter(handler).list_models()
    assert found == [
        DiscoveredModel(
            "claude-opus-5-5",
            "Claude Opus 5.5",
            1_000_000,
            128_000,
            ("tools", "thinking", "vision"),
        ),
        DiscoveredModel("claude-haiku-5-5", "Claude Haiku 5.5", 1_000_000, 128_000, ("tools",)),
        DiscoveredModel("claude-old", "claude-old", 1_000_000, 128_000, ("tools",)),
    ]
    assert [request.url.path for request in seen] == ["/v1/models", "/v1/models"]
    assert seen[0].headers["authorization"] == f"Bearer {SECRET}"
    assert seen[1].url.params["after_id"] == "claude-opus-5-5"


@pytest.mark.parametrize(
    ("status", "failure"),
    [
        (401, Failure.KEY_REJECTED),
        (403, Failure.KEY_REJECTED),
        (404, Failure.NOT_FOUND),
        (429, Failure.RATE_LIMITED),
        (500, Failure.PROVIDER_ERROR),
        (418, Failure.PROVIDER_ERROR),
    ],
)
async def test_anthropic_failures_are_named_and_never_quote_the_response(
    status: int, failure: Failure
) -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status,
            json={"error": {"message": f"leaked {SECRET}"}},
            headers={"x-should-retry": "false"},
        )

    adapter = anthropic_adapter(handler)
    with pytest.raises(UpstreamError) as raised:
        await adapter.list_models()
    assert raised.value.failure is failure
    assert SECRET not in raised.value.detail
    assert "leaked" not in raised.value.detail


async def test_anthropic_that_cannot_be_reached_or_answers_nonsense() -> None:
    def down(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route", request=request)

    adapter = anthropic_adapter(down)
    with pytest.raises(UpstreamError) as unreachable:
        await adapter.list_models()
    assert unreachable.value.failure is Failure.UNREACHABLE

    def slow(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("too slow", request=request)

    adapter = anthropic_adapter(slow)
    with pytest.raises(UpstreamError) as timed_out:
        await adapter.list_models()
    assert timed_out.value.failure is Failure.UNREACHABLE

    def nonsense(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"<html>not json</html>")

    adapter = anthropic_adapter(nonsense)
    with pytest.raises(UpstreamError) as bad:
        await adapter.list_models()
    assert bad.value.failure is Failure.BAD_RESPONSE


def test_a_generic_sdk_error_is_a_bad_response() -> None:
    assert anthropic_module.translate(anthropic.APIError("x", REQUEST, body=None)).failure is (
        Failure.BAD_RESPONSE
    )
    assert openai_module.translate(openai.APIError("x", REQUEST, body=None)).failure is (
        Failure.BAD_RESPONSE
    )


async def test_openai_lists_text_models_only_and_sorted() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        assert request.url.path == "/v1/models"
        ids = [
            "text-embedding-3-large",
            "gpt-6.2-sol",
            "gpt-realtime-2",
            "whisper-1",
            "gpt-6-luna",
            "gpt-image-2",
            "gpt-5.4-mini-transcribe",
        ]
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": one, "object": "model", "created": 1, "owned_by": "openai"}
                    for one in ids
                ],
            },
        )

    found = await openai_adapter(handler).list_models()
    assert [one.model_id for one in found] == ["gpt-6-luna", "gpt-6.2-sol"]
    assert all(one.capabilities == ("tools",) for one in found)
    assert is_chat_model("gpt-5.4-nano")
    assert not is_chat_model("dall-e-3")
    assert not is_chat_model("gpt-4o-mini-tts")


@pytest.mark.parametrize(
    ("status", "failure"),
    [
        (401, Failure.KEY_REJECTED),
        (403, Failure.KEY_REJECTED),
        (404, Failure.NOT_FOUND),
        (429, Failure.RATE_LIMITED),
        (503, Failure.PROVIDER_ERROR),
    ],
)
async def test_openai_failures_are_named(status: int, failure: Failure) -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status, json={"error": {"message": SECRET}}, headers={"x-should-retry": "false"}
        )

    adapter = openai_adapter(handler)
    with pytest.raises(UpstreamError) as raised:
        await adapter.list_models()
    assert raised.value.failure is failure
    assert SECRET not in raised.value.detail


async def test_openai_that_cannot_be_reached() -> None:
    def down(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route", request=request)

    adapter = openai_adapter(down)
    with pytest.raises(UpstreamError) as raised:
        await adapter.list_models()
    assert raised.value.failure is Failure.UNREACHABLE


def ollama_server(
    shown: dict[str, object], tags: list[str], seen: list[httpx2.Request] | None = None
) -> Handler:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if seen is not None:
            seen.append(request)
        if request.url.path == "/api/tags":
            return httpx2.Response(200, json={"models": [{"name": name} for name in tags]})
        name = json.loads(request.content)["model"]
        answer = shown[name]
        if isinstance(answer, int):
            return httpx2.Response(answer)
        return httpx2.Response(200, json=answer)

    return handler


async def test_ollama_lists_models_with_what_show_says_and_skips_embedding_models() -> None:
    seen: list[httpx2.Request] = []
    shown: dict[str, object] = {
        "qwen3:32b": {
            "capabilities": ["completion", "tools", "thinking", "insert"],
            "model_info": {"general.architecture": "qwen3", "qwen3.context_length": 40960},
        },
        "llava:13b": {"capabilities": ["completion", "vision"], "model_info": {}},
        "nomic-embed-text": {"capabilities": ["embedding"], "model_info": {}},
        "broken": 500,
        "old": {"model_info": {"llama.context_length": 8192}},
        "garbled": {"capabilities": "oops"},
    }
    handler = ollama_server(
        shown, ["qwen3:32b", "llava:13b", "nomic-embed-text", "broken", "old", "garbled"], seen
    )
    found = await ollama_adapter(handler, "k").list_models()
    assert found == [
        DiscoveredModel("broken", "broken"),
        DiscoveredModel("garbled", "garbled"),
        DiscoveredModel("llava:13b", "llava:13b", None, None, ("vision",)),
        DiscoveredModel("old", "old", 8192, None, ()),
        DiscoveredModel("qwen3:32b", "qwen3:32b", 40960, None, ("tools", "thinking")),
    ]
    assert {request.headers["authorization"] for request in seen} == {"Bearer k"}


async def test_local_ollama_sends_no_authorization() -> None:
    seen: list[httpx2.Request] = []
    await ollama_adapter(ollama_server({}, [], seen)).list_models()
    assert "authorization" not in seen[0].headers


@pytest.mark.parametrize(
    ("status", "failure"),
    [
        (401, Failure.KEY_REJECTED),
        (403, Failure.KEY_REJECTED),
        (404, Failure.NOT_FOUND),
        (500, Failure.PROVIDER_ERROR),
    ],
)
async def test_ollama_failures_are_named(status: int, failure: Failure) -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, text=SECRET)

    adapter = ollama_adapter(handler)
    with pytest.raises(UpstreamError) as raised:
        await adapter.list_models()
    assert raised.value.failure is failure
    assert SECRET not in raised.value.detail


@pytest.mark.parametrize(
    "answer",
    [
        httpx2.Response(200, content=b"not json"),
        httpx2.Response(200, json={"models": "none"}),
        httpx2.Response(200, json=["a"]),
    ],
)
async def test_ollama_answering_nonsense_is_a_bad_response(answer: httpx2.Response) -> None:
    adapter = ollama_adapter(lambda _request: answer)
    with pytest.raises(UpstreamError) as raised:
        await adapter.list_models()
    assert raised.value.failure is Failure.BAD_RESPONSE


async def test_ollama_that_cannot_be_reached() -> None:
    def down(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    adapter = ollama_adapter(down)
    with pytest.raises(UpstreamError) as raised:
        await adapter.list_models()
    assert raised.value.failure is Failure.UNREACHABLE


async def test_the_http_client_never_follows_redirects() -> None:
    from app.ai.adapters.factory import TIMEOUT, new_http_client  # noqa: PLC0415

    http = new_http_client()
    assert http.follow_redirects is False
    assert http.timeout == TIMEOUT
    await http.aclose()


def test_the_context_window_is_found_under_any_architecture() -> None:
    assert context_length({"x.context_length": 4096}) == 4096
    assert context_length({"x.context_length": 0}) is None
    assert context_length({"x.context_length": "big"}) is None
    assert context_length({}) is None
    assert Shown.model_validate({}).capabilities == []


async def test_openai_answering_with_something_that_is_not_json() -> None:
    def nonsense(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"<html>not json</html>")

    adapter = openai_adapter(nonsense)
    with pytest.raises(UpstreamError) as raised:
        await adapter.list_models()
    assert raised.value.failure is Failure.BAD_RESPONSE
