"""Trying a provider and fetching its models, through the routes."""

import json
import uuid
from collections.abc import Callable

import httpx2
from fastapi.testclient import TestClient
from tests.conftest import add_account, another_browser, app_of
from tests.test_ai_api import KEY, add_provider, admin_api, resolve_to

from app.ai.adapters.factory import get_http_client_factory
from app.ai.routes import get_resolver

Handler = Callable[[httpx2.Request], httpx2.Response]


def fake_network(api: TestClient, handler: Handler) -> list[httpx2.AsyncClient]:
    """Send the provider calls to `handler`. The clients made are returned, to check they are
    closed."""
    made: list[httpx2.AsyncClient] = []

    def factory() -> httpx2.AsyncClient:
        made.append(httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))
        return made[-1]

    app_of(api).dependency_overrides[get_http_client_factory] = lambda: factory
    return made


def claude_list(request: httpx2.Request) -> httpx2.Response:
    assert request.headers["authorization"] == f"Bearer {KEY}"
    return httpx2.Response(
        200,
        json={
            "data": [
                {
                    "id": "claude-opus-5-5",
                    "type": "model",
                    "display_name": "Claude Opus 5.5",
                    "created_at": "2026-01-01T00:00:00Z",
                    "max_input_tokens": 1_000_000,
                    "max_tokens": 128_000,
                    "capabilities": {},
                },
                {
                    "id": "claude-brand-new",
                    "type": "model",
                    "display_name": "claude-brand-new",
                    "created_at": "2026-02-01T00:00:00Z",
                },
            ],
            "has_more": False,
            "first_id": "claude-opus-5-5",
            "last_id": "claude-brand-new",
        },
    )


def anthropic_provider(api: TestClient) -> dict[str, object]:
    return add_provider(api, kind="anthropic", name="Anthropic")


def test_a_working_provider_reports_its_model_count_and_latency(api: TestClient) -> None:
    admin_api(api)
    made = fake_network(api, claude_list)
    provider = anthropic_provider(api)
    report = api.post(f"/api/providers/{provider['id']}/test").json()
    assert report["ok"] is True
    assert report["model_count"] == 2
    assert report["failure"] is None
    assert report["latency_ms"] >= 0
    assert "2 models" in report["detail"]
    assert all(client.is_closed for client in made)
    audited = api.get("/api/audit", params={"action": "provider.test"}).json()["items"][0]
    assert audited["detail"] == {"ok": True, "failure": None}
    assert KEY not in api.get("/api/audit").text


def test_a_failure_is_a_result_the_page_can_show(api: TestClient) -> None:
    admin_api(api)
    provider = anthropic_provider(api)
    fake_network(api, lambda _r: httpx2.Response(401, headers={"x-should-retry": "false"}))
    report = api.post(f"/api/providers/{provider['id']}/test").json()
    assert (report["ok"], report["failure"], report["model_count"]) == (False, "key_rejected", None)
    assert "did not accept the key" in report["detail"]
    assert KEY not in json.dumps(report)


def test_a_provider_that_cannot_be_reached(api: TestClient) -> None:
    admin_api(api)
    provider = add_provider(api, kind="ollama-local", name="L", api_key=None)

    def down(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    made = fake_network(api, down)
    report = api.post(f"/api/providers/{provider['id']}/test").json()
    assert (report["ok"], report["failure"]) == (False, "unreachable")
    assert all(client.is_closed for client in made)


def test_the_address_is_checked_again_at_call_time(api: TestClient) -> None:
    admin_api(api)
    provider = anthropic_provider(api)
    made = fake_network(api, claude_list)
    # The name now resolves to a private address, as in a DNS rebinding attack.
    app_of(api).dependency_overrides[get_resolver] = lambda: resolve_to("10.0.0.5")
    report = api.post(f"/api/providers/{provider['id']}/test").json()
    assert (report["ok"], report["failure"]) == (False, "base_url_rejected")
    assert "private or local" in report["detail"]
    assert made == []  # no request was made
    fetched = api.post(f"/api/providers/{provider['id']}/models/fetch")
    assert (fetched.status_code, fetched.json()["code"]) == (422, "base_url_rejected")


def test_fetching_lists_the_models_with_what_would_be_added(api: TestClient) -> None:
    admin_api(api)
    provider = anthropic_provider(api)
    fake_network(api, claude_list)
    base = f"/api/providers/{provider['id']}"
    api.post(f"{base}/models", json={"model_id": "claude-opus-5-5"})
    found = api.post(f"{base}/models/fetch").json()
    assert found == [
        {
            "model_id": "claude-opus-5-5",
            "display_name": "Claude Opus 5.5",
            "context_tokens": 1_000_000,
            "max_output_tokens": 128_000,
            "capabilities": ["tools"],
            "added": True,
            "price_source": "catalog",
        },
        {
            "model_id": "claude-brand-new",
            "display_name": "claude-brand-new",
            "context_tokens": None,
            "max_output_tokens": None,
            "capabilities": ["tools"],
            "added": False,
            "price_source": "unknown",
        },
    ]
    # Fetching adds nothing.
    assert len(api.get(f"{base}/models").json()) == 1


def test_fetching_fills_gaps_from_the_catalog_and_marks_local_models_free(api: TestClient) -> None:
    admin_api(api)
    provider = add_provider(api, kind="openai", name="OpenAI")
    fake_network(
        api,
        lambda _r: httpx2.Response(
            200,
            json={
                "object": "list",
                "data": [{"id": "gpt-6-luna", "object": "model", "created": 1}],
            },
        ),
    )
    luna = api.post(f"/api/providers/{provider['id']}/models/fetch").json()[0]
    assert luna["context_tokens"] is not None
    assert luna["display_name"] != "gpt-6-luna"
    assert luna["price_source"] == "catalog"

    local = add_provider(api, kind="ollama-local", name="L", api_key=None)

    def ollama(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/api/tags":
            return httpx2.Response(200, json={"models": [{"name": "llama3.3:70b"}]})
        return httpx2.Response(
            200,
            json={
                "capabilities": ["completion", "tools"],
                "model_info": {"llama.context_length": 131072},
            },
        )

    fake_network(api, ollama)
    found = api.post(f"/api/providers/{local['id']}/models/fetch").json()
    assert found[0]["price_source"] == "free"
    assert (found[0]["context_tokens"], found[0]["capabilities"]) == (131072, ["tools"])


def test_a_failed_fetch_is_a_gateway_error_with_a_code(api: TestClient) -> None:
    admin_api(api)
    provider = anthropic_provider(api)
    fake_network(api, lambda _r: httpx2.Response(401, headers={"x-should-retry": "false"}))
    answer = api.post(f"/api/providers/{provider['id']}/models/fetch")
    assert (answer.status_code, answer.json()["code"]) == (502, "provider_key_rejected")
    assert KEY not in answer.text


def test_unknown_providers_are_not_found(api: TestClient) -> None:
    admin_api(api)
    missing = uuid.uuid4()
    assert api.post(f"/api/providers/{missing}/test").status_code == 404
    assert api.post(f"/api/providers/{missing}/models/fetch").status_code == 404


def test_a_viewer_cannot_make_the_server_call_out(api: TestClient) -> None:
    admin_api(api)
    provider = anthropic_provider(api)
    made = fake_network(api, claude_list)
    add_account(api, "vera", "viewer")
    vera = another_browser(api, "vera")
    for path in ("test", "models/fetch"):
        answer = vera.post(f"/api/providers/{provider['id']}/{path}")
        assert (answer.status_code, answer.json()["code"]) == (403, "read_only")
    assert made == []


def test_the_default_http_client_factory_makes_a_real_client() -> None:
    from app.ai.adapters.factory import new_http_client  # noqa: PLC0415

    assert get_http_client_factory() is new_http_client
