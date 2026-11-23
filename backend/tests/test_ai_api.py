"""The provider routes: add, change, hide the key, models, role defaults and the catalog."""

import uuid
from decimal import Decimal

import psycopg
from fastapi.testclient import TestClient
from tests.conftest import add_account, another_browser, app_of, set_up

from app.ai.netguard import Resolver, system_resolver
from app.ai.routes import get_resolver, router
from app.db.events import connection_string
from app.routers import ROUTERS

KEY = "sk-test-0123456789abcdefghijklmnopqrstuv"
PUBLIC = "93.184.216.34"


def resolve_to(*addresses: str) -> Resolver:
    async def resolve(host: str, port: int) -> list[str]:
        assert host
        assert port
        return list(addresses)

    return resolve


def admin_api(api: TestClient, *addresses: str) -> TestClient:
    """A signed-in administrator, with host names resolving to the addresses given (public by
    default)."""
    set_up(api)
    found = resolve_to(*(addresses or (PUBLIC,)))
    app_of(api).dependency_overrides[get_resolver] = lambda: found
    return api


def add_provider(api: TestClient, **fields: object) -> dict[str, object]:
    body = {"kind": "openai", "name": "OpenAI", "api_key": KEY} | fields
    answer = api.post("/api/providers", json=body)
    assert answer.status_code == 201, answer.text
    return answer.json()


def test_a_provider_is_added_with_the_kinds_usual_address_and_its_key_is_hidden(
    api: TestClient,
) -> None:
    admin_api(api)
    made = add_provider(api, monthly_budget_usd="25.50", hard_stop=True)
    assert made["base_url"] == "https://api.openai.com/v1"
    assert made["has_key"] is True
    assert made["key_last4"] == KEY[-4:]
    assert Decimal(str(made["monthly_budget_usd"])) == Decimal("25.5")
    assert made["hard_stop"] is True
    assert made["spent_this_month_usd"] == "0"
    assert made["model_count"] == 0
    assert KEY not in api.get("/api/providers").text
    assert KEY not in api.get(f"/api/providers/{made['id']}").text
    assert "api_key" not in api.get("/api/providers").json()[0]


def test_the_key_is_sealed_in_the_database_and_never_audited_or_logged(
    api: TestClient, database_url: str, caplog: object
) -> None:
    admin_api(api)
    made = add_provider(api)
    with psycopg.connect(connection_string(database_url)) as connection:
        stored = connection.execute(
            "SELECT api_key, api_key_last4 FROM ai_provider WHERE id = %s", (made["id"],)
        ).fetchone()
        assert stored is not None
        assert stored[0].startswith("v1:")
        assert KEY not in stored[0]
        assert stored[1] == KEY[-4:]
        audit = connection.execute("SELECT detail::text FROM audit_event").fetchall()
    assert all(KEY not in (row[0] or "") for row in audit)
    assert api.get("/api/audit").text.count(KEY) == 0
    assert KEY not in str(getattr(caplog, "text", ""))


def test_each_kind_has_its_own_rules_for_keys_and_addresses(api: TestClient) -> None:
    admin_api(api)
    kinds = api.get("/api/ai/kinds").json()
    assert [one["kind"] for one in kinds] == ["anthropic", "openai", "ollama-local", "ollama-cloud"]
    assert [one["needs_key"] for one in kinds] == [True, True, False, True]
    assert kinds[2]["default_base_url"] == "http://host.docker.internal:11434"

    missing = api.post("/api/providers", json={"kind": "anthropic", "name": "A"})
    assert (missing.status_code, missing.json()["code"]) == (422, "key_required")
    blank = api.post("/api/providers", json={"kind": "ollama-cloud", "name": "C", "api_key": "  "})
    assert blank.json()["code"] == "key_required"

    local = add_provider(api, kind="ollama-local", name="Local", api_key=None)
    assert (local["has_key"], local["key_last4"]) == (False, None)
    cloud = add_provider(api, kind="ollama-cloud", name="Cloud")
    assert cloud["base_url"] == "https://ollama.com"


def test_an_unsafe_address_is_refused_and_nothing_is_saved(api: TestClient) -> None:
    admin_api(api, "10.0.0.5")
    refused = api.post(
        "/api/providers",
        json={"kind": "openai", "name": "Bad", "api_key": KEY, "base_url": "https://proxy.lan"},
    )
    assert (refused.status_code, refused.json()["code"]) == (422, "base_url_rejected")
    assert "private or local" in refused.json()["title"]
    assert api.get("/api/providers").json() == []
    # Local Ollama may be on the private network.
    assert add_provider(api, kind="ollama-local", name="L", api_key=None)["base_url"]


def test_names_are_unique_and_a_provider_is_found_by_id(api: TestClient) -> None:
    admin_api(api)
    first = add_provider(api, name="Main")
    again = api.post("/api/providers", json={"kind": "openai", "name": "Main", "api_key": KEY})
    assert (again.status_code, again.json()["code"]) == (409, "name_taken")
    other = add_provider(api, name="Other")
    taken = api.patch(f"/api/providers/{other['id']}", json={"name": "Main"})
    assert (taken.status_code, taken.json()["code"]) == (409, "name_taken")
    assert api.get(f"/api/providers/{first['id']}").json()["name"] == "Main"
    missing = api.get(f"/api/providers/{uuid.uuid4()}")
    assert (missing.status_code, missing.json()["code"]) == (404, "not_found")


def test_changing_a_provider(api: TestClient, database_url: str) -> None:
    admin_api(api)
    made = add_provider(api, monthly_budget_usd="10", hard_stop=True)
    url = f"/api/providers/{made['id']}"
    changed = api.patch(
        url,
        json={
            "name": "Renamed",
            "base_url": "https://gateway.example.com/v1/",
            "enabled": False,
            "hard_stop": False,
            "api_key": "sk-new-0123456789abcdefghijklmnopqrst",
            "monthly_budget_usd": None,
        },
    ).json()
    assert changed["name"] == "Renamed"
    assert changed["base_url"] == "https://gateway.example.com/v1"
    assert changed["enabled"] is False
    assert changed["hard_stop"] is False
    assert changed["key_last4"] == "qrst"
    assert changed["monthly_budget_usd"] is None  # null removes the budget
    # Leaving a field out keeps it.
    kept = api.patch(url, json={"enabled": True}).json()
    assert (kept["name"], kept["key_last4"]) == ("Renamed", "qrst")
    updates = api.get("/api/audit", params={"action": "provider.update"}).json()["items"]
    assert "api_key" in updates[-1]["detail"]["changed"]  # the oldest is the big change
    assert "sk-new" not in api.get("/api/audit").text
    bad = api.patch(url, json={"base_url": "http://plain.example.com"})
    assert bad.json()["code"] == "base_url_rejected"
    assert api.patch(f"/api/providers/{uuid.uuid4()}", json={"enabled": True}).status_code == 404
    with psycopg.connect(connection_string(database_url)) as connection:
        assert connection.execute("SELECT count(*) FROM ai_provider").fetchone() == (1,)


def test_a_key_can_be_removed_only_where_none_is_needed(api: TestClient) -> None:
    admin_api(api)
    hosted = add_provider(api)
    refused = api.patch(f"/api/providers/{hosted['id']}", json={"remove_key": True})
    assert (refused.status_code, refused.json()["code"]) == (422, "key_required")
    local = add_provider(api, kind="ollama-local", name="L", api_key="local-secret-1234")
    assert local["key_last4"] == "1234"
    removed = api.patch(f"/api/providers/{local['id']}", json={"remove_key": True}).json()
    assert (removed["has_key"], removed["key_last4"]) == (False, None)


def test_deleting_a_provider_removes_its_models_and_defaults(api: TestClient) -> None:
    admin_api(api)
    made = add_provider(api)
    model = api.post(f"/api/providers/{made['id']}/models", json={"model_id": "gpt-6-luna"}).json()
    assert api.put("/api/ai/role-defaults/chat", json={"model_ref": model["id"]}).status_code == 204
    assert api.delete(f"/api/providers/{made['id']}").status_code == 204
    assert api.get("/api/providers").json() == []
    assert all(one["model_ref"] is None for one in api.get("/api/ai/role-defaults").json())
    assert api.delete(f"/api/providers/{made['id']}").status_code == 404
    deleted = api.get("/api/audit", params={"action": "provider.delete"}).json()["items"][0]
    assert deleted["detail"] == {"name": "OpenAI"}


def test_models_start_from_the_catalog_and_can_be_overridden(api: TestClient) -> None:
    admin_api(api)
    made = add_provider(api, kind="anthropic", name="Anthropic")
    base = f"/api/providers/{made['id']}/models"
    opus = api.post(base, json={"model_id": "claude-opus-5-5"}).json()
    assert opus["display_name"] == "Claude Opus 5.5"
    assert opus["context_tokens"] == 1_000_000
    assert opus["capabilities"] == ["tools", "thinking", "vision"]
    assert opus["supports_tools"] is True
    assert opus["price_source"] == "catalog"
    assert Decimal(opus["price"]["input"]) == 4
    assert Decimal(opus["price"]["cache_read"]) == Decimal("0.2")
    assert opus["overrides"]["input"] is None

    unknown = api.post(base, json={"model_id": "claude-future-9", "capabilities": []}).json()
    assert (unknown["price_source"], unknown["price"]["input"]) == ("unknown", None)
    assert unknown["supports_tools"] is False
    assert unknown["display_name"] == "claude-future-9"

    own = api.post(
        base,
        json={
            "model_id": "gateway-model",
            "display_name": "Gateway",
            "context_tokens": 200_000,
            "max_output_tokens": 8_000,
            "capabilities": ["tools"],
            "price_input": "1.5",
            "enabled": False,
        },
    ).json()
    assert (own["price_source"], own["enabled"]) == ("override", False)
    assert Decimal(own["price"]["input"]) == Decimal("1.5")

    dup = api.post(base, json={"model_id": "claude-opus-5-5"})
    assert (dup.status_code, dup.json()["code"]) == (409, "model_exists")

    url = f"{base}/{opus['id']}"
    changed = api.patch(
        url,
        json={
            "price_input": "3",
            "display_name": "Opus",
            "enabled": False,
            "capabilities": ["tools"],
        },
    ).json()
    assert Decimal(changed["price"]["input"]) == 3
    assert Decimal(changed["price"]["output"]) == 20  # still the catalog's
    assert (changed["price_source"], changed["display_name"], changed["enabled"]) == (
        "override",
        "Opus",
        False,
    )
    assert changed["capabilities"] == ["tools"]
    cleared = api.patch(url, json={"price_input": None}).json()
    assert cleared["price_source"] == "catalog"
    assert Decimal(cleared["price"]["input"]) == 4
    kept = api.patch(url, json={"enabled": True}).json()
    assert kept["display_name"] == "Opus"

    listed = api.get(base).json()
    assert [one["model_id"] for one in listed] == [
        "claude-future-9",
        "claude-opus-5-5",
        "gateway-model",
    ]
    assert api.get(f"/api/providers/{made['id']}").json()["model_count"] == 3

    assert api.delete(url).status_code == 204
    assert api.delete(url).status_code == 404
    assert api.patch(url, json={"enabled": True}).status_code == 404
    assert api.get(f"/api/providers/{uuid.uuid4()}/models").status_code == 404
    assert (
        api.post(f"/api/providers/{uuid.uuid4()}/models", json={"model_id": "x"}).status_code == 404
    )


def test_a_model_of_another_provider_is_not_found_under_this_one(api: TestClient) -> None:
    admin_api(api)
    first = add_provider(api, name="First")
    second = add_provider(api, name="Second")
    model = api.post(f"/api/providers/{first['id']}/models", json={"model_id": "gpt-6-luna"}).json()
    wrong = f"/api/providers/{second['id']}/models/{model['id']}"
    assert api.patch(wrong, json={"enabled": False}).status_code == 404
    assert api.delete(wrong).status_code == 404


def test_models_on_this_machine_are_free(api: TestClient) -> None:
    admin_api(api)
    local = add_provider(api, kind="ollama-local", name="L", api_key=None)
    model = api.post(
        f"/api/providers/{local['id']}/models",
        json={"model_id": "llama3.3:70b", "capabilities": ["tools"]},
    ).json()
    assert model["price_source"] == "free"
    assert model["price"]["output"] == "0"


def test_the_catalog_is_listed_with_its_date(api: TestClient) -> None:
    admin_api(api)
    catalog = api.get("/api/ai/catalog").json()
    assert catalog["verified_on"] == "2026-11-23"
    haiku = next(one for one in catalog["models"] if one["id"] == "claude-haiku-5-5")
    assert haiku["long_prompt_above"] == 100_000
    assert Decimal(haiku["long_prompt_price"]["input"]) == Decimal("0.5")
    opus = next(one for one in catalog["models"] if one["id"] == "claude-opus-5-5")
    assert (opus["long_prompt_above"], opus["long_prompt_price"]) == (None, None)


def test_default_models_per_role(api: TestClient) -> None:
    admin_api(api)
    roles = api.get("/api/ai/role-defaults").json()
    assert [one["role"] for one in roles] == [
        "commander",
        "category-agent",
        "test-agent",
        "reporter",
        "chat",
    ]
    assert all(one["model_ref"] is None and one["label"] for one in roles)
    made = add_provider(api, name="Main")
    model = api.post(f"/api/providers/{made['id']}/models", json={"model_id": "gpt-6.2-sol"}).json()
    off = api.post(
        f"/api/providers/{made['id']}/models", json={"model_id": "gpt-6-luna", "enabled": False}
    ).json()
    assert (
        api.put("/api/ai/role-defaults/commander", json={"model_ref": model["id"]}).status_code
        == 204
    )
    assert (
        api.put("/api/ai/role-defaults/commander", json={"model_ref": model["id"]}).status_code
        == 204
    )
    chosen = next(
        one for one in api.get("/api/ai/role-defaults").json() if one["role"] == "commander"
    )
    assert (chosen["model_ref"], chosen["provider_name"], chosen["model_id"]) == (
        model["id"],
        "Main",
        "gpt-6.2-sol",
    )
    refused = api.put("/api/ai/role-defaults/chat", json={"model_ref": off["id"]})
    assert (refused.status_code, refused.json()["code"]) == (409, "model_disabled")
    nothing = api.put("/api/ai/role-defaults/chat", json={"model_ref": str(uuid.uuid4())})
    assert nothing.status_code == 404
    assert (
        api.put("/api/ai/role-defaults/nonsense", json={"model_ref": model["id"]}).status_code
        == 422
    )
    assert api.delete("/api/ai/role-defaults/commander").status_code == 204
    assert api.delete("/api/ai/role-defaults/commander").status_code == 204
    cleared = api.get("/api/ai/role-defaults").json()
    assert all(one["model_ref"] is None for one in cleared)
    # Removing a model clears the default that used it.
    api.put("/api/ai/role-defaults/reporter", json={"model_ref": model["id"]})
    api.delete(f"/api/providers/{made['id']}/models/{model['id']}")
    assert all(one["model_ref"] is None for one in api.get("/api/ai/role-defaults").json())


def test_changes_are_audited(api: TestClient) -> None:
    admin_api(api)
    made = add_provider(api)
    model = api.post(f"/api/providers/{made['id']}/models", json={"model_id": "gpt-6-luna"}).json()
    api.patch(f"/api/providers/{made['id']}/models/{model['id']}", json={"enabled": False})
    api.delete(f"/api/providers/{made['id']}/models/{model['id']}")
    actions = {
        one["action"] for one in api.get("/api/audit", params={"limit": 200}).json()["items"]
    }
    assert {
        "provider.create",
        "provider.model_add",
        "provider.model_update",
        "provider.model_remove",
    } <= actions


def test_a_viewer_can_read_providers_but_never_change_them_or_see_keys(api: TestClient) -> None:
    admin_api(api)
    made = add_provider(api)
    model = api.post(f"/api/providers/{made['id']}/models", json={"model_id": "gpt-6-luna"}).json()
    add_account(api, "vera", "viewer")
    vera = another_browser(api, "vera")
    for path in (
        "/api/providers",
        f"/api/providers/{made['id']}",
        f"/api/providers/{made['id']}/models",
        "/api/ai/catalog",
        "/api/ai/kinds",
        "/api/ai/role-defaults",
    ):
        answer = vera.get(path)
        assert answer.status_code == 200, path
        assert KEY not in answer.text
    base = f"/api/providers/{made['id']}"
    for answer in (
        vera.post("/api/providers", json={"kind": "openai", "name": "x", "api_key": KEY}),
        vera.patch(base, json={"enabled": False}),
        vera.delete(base),
        vera.post(f"{base}/models", json={"model_id": "m"}),
        vera.patch(f"{base}/models/{model['id']}", json={"enabled": False}),
        vera.delete(f"{base}/models/{model['id']}"),
        vera.put("/api/ai/role-defaults/chat", json={"model_ref": model["id"]}),
        vera.delete("/api/ai/role-defaults/chat"),
    ):
        assert (answer.status_code, answer.json()["code"]) == (403, "read_only")


def test_signed_out_visitors_get_nothing(api: TestClient) -> None:
    set_up(api)
    api.cookies.clear()
    assert api.get("/api/providers").status_code == 401
    assert api.get("/api/ai/catalog").status_code == 401
    assert api.post("/api/providers", json={}).status_code == 401


def test_the_provider_routes_are_part_of_the_app() -> None:
    assert router in ROUTERS


async def test_host_names_are_looked_up_by_the_system_unless_a_test_says_otherwise() -> None:
    assert await get_resolver() is system_resolver
