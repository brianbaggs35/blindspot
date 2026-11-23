"""Accounts, the audit trail, the read-only role, the cross-site check and the route policies."""

import uuid

import psycopg
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from tests.conftest import GOOD_PASSWORD, SAME_SITE, add_account, another_browser, app_of, set_up

from app.auth.deps import Policy
from app.db.events import connection_string
from app.routers import ROUTERS


def routes() -> list[APIRoute]:
    return [route for router in ROUTERS for route in router.routes if isinstance(route, APIRoute)]


def test_an_administrator_adds_lists_and_changes_accounts(api: TestClient) -> None:
    set_up(api)
    ann = add_account(api, "Ann", "viewer")
    listed = api.get("/api/users").json()
    assert [one["username"] for one in listed] == ["admin", "ann"]
    assert all("password" not in key for one in listed for key in one)

    changed = api.patch(f"/api/users/{ann}", json={"display_name": "Ann A.", "role": "admin"})
    assert changed.json()["display_name"] == "Ann A."
    assert changed.json()["role"] == "admin"
    blank = api.patch(f"/api/users/{ann}", json={"display_name": ""})
    assert blank.json()["display_name"] == "ann"


def test_usernames_and_passwords_are_checked_when_adding(api: TestClient) -> None:
    set_up(api)
    add_account(api, "ann")
    taken = api.post("/api/users", json={"username": "ANN", "password": GOOD_PASSWORD})
    assert (taken.status_code, taken.json()["code"]) == (409, "username_taken")
    bad = api.post("/api/users", json={"username": "a", "password": GOOD_PASSWORD})
    assert bad.json()["code"] == "username_invalid"
    weak = api.post("/api/users", json={"username": "bob", "password": "weak"})
    assert weak.json()["code"] == "password_rejected"
    extra = api.post(
        "/api/users", json={"username": "bob", "password": GOOD_PASSWORD, "is_admin": True}
    )
    assert extra.status_code == 422
    assert len(api.get("/api/users").json()) == 2  # the failed attempts left nothing behind


def test_an_account_that_does_not_exist_is_not_found(api: TestClient) -> None:
    set_up(api)
    missing = uuid.uuid4()
    assert api.patch(f"/api/users/{missing}", json={"is_active": False}).status_code == 404
    assert api.delete(f"/api/users/{missing}").status_code == 404
    assert api.post(f"/api/users/{missing}/sign-out").status_code == 404
    reset = api.post(f"/api/users/{missing}/password", json={"password": GOOD_PASSWORD})
    assert reset.status_code == 404


def test_you_cannot_lock_yourself_out(api: TestClient) -> None:
    set_up(api)
    me = api.get("/api/auth/me").json()["id"]
    for change in ({"role": "viewer"}, {"is_active": False}):
        answer = api.patch(f"/api/users/{me}", json=change)
        assert (answer.status_code, answer.json()["code"]) == (409, "own_account")
    assert api.delete(f"/api/users/{me}").status_code == 409
    renamed = api.patch(f"/api/users/{me}", json={"display_name": "The Boss"})
    assert renamed.json()["display_name"] == "The Boss"


def test_a_password_reset_signs_the_account_out(api: TestClient) -> None:
    set_up(api)
    ann = add_account(api, "ann")
    browser = another_browser(api, "ann")
    weak = api.post(f"/api/users/{ann}/password", json={"password": "weak"})
    assert weak.json()["code"] == "password_rejected"
    assert (
        api.post(
            f"/api/users/{ann}/password", json={"password": "a different passphrase"}
        ).status_code
        == 204
    )
    assert browser.get("/api/auth/me").status_code == 401
    assert (
        another_browser(api, "ann", "a different passphrase").get("/api/auth/me").status_code == 200
    )


def test_an_administrator_can_sign_an_account_out(api: TestClient) -> None:
    set_up(api)
    ann = add_account(api, "ann")
    browser = another_browser(api, "ann")
    assert api.post(f"/api/users/{ann}/sign-out").status_code == 204
    assert browser.get("/api/auth/me").status_code == 401


def test_removing_an_account_keeps_what_it_did_in_the_audit_trail(api: TestClient) -> None:
    set_up(api)
    ann = add_account(api, "ann")
    another_browser(api, "ann")
    assert api.delete(f"/api/users/{ann}").status_code == 204
    assert [one["username"] for one in api.get("/api/users").json()] == ["admin"]
    events = api.get("/api/audit", params={"actor": "ann"}).json()["items"]
    assert [one["action"] for one in events] == ["auth.login"]


def test_a_viewer_can_look_but_not_change(api: TestClient) -> None:
    set_up(api)
    add_account(api, "vera", "viewer")
    vera = another_browser(api, "vera")
    assert vera.get("/api/auth/me").json()["role"] == "viewer"
    for answer in (
        vera.get("/api/users"),
        vera.post("/api/users", json={"username": "x" * 5, "password": GOOD_PASSWORD}),
        vera.get("/api/audit"),
    ):
        assert (answer.status_code, answer.json()["code"]) == (403, "read_only")
    # What a person does to their own account is allowed to everyone.
    assert vera.get("/api/auth/sessions").status_code == 200
    assert vera.post("/api/auth/logout").status_code == 204


def test_the_audit_trail_filters_and_pages(api: TestClient) -> None:
    set_up(api)
    for name in ("ann", "bob", "cat"):
        add_account(api, name)
    everything = api.get("/api/audit", params={"limit": 200}).json()["items"]
    assert [one["action"] for one in everything][-1] == "auth.setup"  # newest first
    first = api.get("/api/audit", params={"limit": 2}).json()
    assert len(first["items"]) == 2
    second = api.get("/api/audit", params={"limit": 2, "before": first["next_before"]}).json()
    assert [one["id"] for one in first["items"] + second["items"]] == [
        one["id"] for one in everything[:4]
    ]
    last = api.get("/api/audit", params={"limit": 200, "before": everything[-1]["id"]}).json()
    assert last == {"items": [], "next_before": None}
    created = api.get("/api/audit", params={"action": "user.create"}).json()["items"]
    assert len(created) == 3
    assert created[0]["detail"] == {"username": "cat", "role": "viewer"}
    assert api.get("/api/audit", params={"outcome": "failure"}).json()["items"] == []
    assert len(api.get("/api/audit", params={"since": "2999-01-01T00:00:00Z"}).json()["items"]) == 0
    assert len(api.get("/api/audit", params={"since": "2000-01-01T00:00:00Z"}).json()["items"]) == 4
    assert api.get("/api/audit", params={"outcome": "maybe"}).status_code == 422


def test_the_audit_trail_records_the_address_and_browser(api: TestClient) -> None:
    set_up(api)
    event = api.get("/api/audit").json()["items"][0]
    assert event["ip_address"] == "testclient"
    assert event["user_agent"] == "testclient"
    assert event["actor_name"] == "admin"


def test_a_request_from_another_site_is_refused(api: TestClient) -> None:
    set_up(api)
    cookie = api.cookies
    hostile = TestClient(app_of(api), base_url="https://testserver", raise_server_exceptions=False)
    hostile.cookies = cookie
    for headers in (
        {},  # the cookie but nothing to show where the request is from
        {"Origin": "https://evil.test"},
        {"Sec-Fetch-Site": "cross-site", "Origin": "https://testserver"},
    ):
        answer = hostile.post("/api/auth/logout", headers=headers)
        assert (answer.status_code, answer.json()["code"]) == (403, "cross_site_request")
    assert api.get("/api/auth/me").status_code == 200  # nothing was done
    assert answer.headers["x-request-id"]


def test_a_foreign_origin_is_refused_even_without_a_cookie(api: TestClient) -> None:
    bare = TestClient(app_of(api), base_url="https://testserver", raise_server_exceptions=False)
    answer = bare.post(
        "/api/auth/login",
        json={"username": "admin", "password": GOOD_PASSWORD},
        headers={"Origin": "https://evil.test"},
    )
    assert answer.status_code == 403


def test_reading_needs_no_proof_of_origin(api: TestClient) -> None:
    set_up(api)
    plain = TestClient(app_of(api), base_url="https://testserver")
    plain.cookies = api.cookies
    assert plain.get("/api/auth/me").status_code == 200


def test_every_route_says_who_may_use_it(api: TestClient) -> None:
    """A route with no policy would be open to everyone by accident."""
    found: dict[tuple[str, str], str] = {}
    for route in routes():
        policies = {
            dependency.call.name
            for dependency in route.dependant.dependencies
            if isinstance(dependency.call, Policy)
        }
        assert len(policies) == 1, f"{route.path} needs exactly one policy, has {policies}"
        for method in route.methods or set():
            found[method, route.path] = policies.pop()
    assert found == {
        ("GET", "/api/health"): "public",
        ("GET", "/api/ready"): "public",
        ("GET", "/api/auth/status"): "public",
        ("POST", "/api/auth/setup"): "public",
        ("POST", "/api/auth/login"): "public",
        ("POST", "/api/auth/logout"): "user",
        ("GET", "/api/auth/me"): "user",
        ("POST", "/api/auth/password"): "user",
        ("GET", "/api/auth/sessions"): "user",
        ("DELETE", "/api/auth/sessions/{session_id}"): "user",
        ("GET", "/api/users"): "admin",
        ("POST", "/api/users"): "admin",
        ("PATCH", "/api/users/{user_id}"): "admin",
        ("POST", "/api/users/{user_id}/password"): "admin",
        ("POST", "/api/users/{user_id}/sign-out"): "admin",
        ("DELETE", "/api/users/{user_id}"): "admin",
        ("GET", "/api/audit"): "admin",
    }


def test_every_route_that_changes_something_needs_an_administrator_or_is_about_yourself(
    api: TestClient,
) -> None:
    """Viewers are read-only: a write that a viewer can make must be on this short list."""
    about_yourself = {
        "/api/auth/logout",
        "/api/auth/password",
        "/api/auth/sessions/{session_id}",
        "/api/auth/login",
        "/api/auth/setup",
    }
    for route in routes():
        if (route.methods or set()) & {"POST", "PUT", "PATCH", "DELETE"}:
            names = {
                dependency.call.name
                for dependency in route.dependant.dependencies
                if isinstance(dependency.call, Policy)
            }
            assert names == {"admin"} or route.path in about_yourself, route.path


def test_api_responses_are_not_cached(api: TestClient) -> None:
    assert api.get("/api/health").headers["cache-control"] == "no-store"
    assert SAME_SITE  # the client sends the headers a browser would


def test_a_visitor_after_setup_is_just_told_nobody_is_signed_in(api: TestClient) -> None:
    set_up(api)
    visitor = TestClient(app_of(api), base_url="https://testserver", headers=SAME_SITE)
    assert visitor.get("/api/auth/status").json() == {"setup_required": False, "user": None}


def test_an_account_can_be_switched_off_and_on_again(api: TestClient, database_url: str) -> None:
    set_up(api)
    ann = add_account(api, "ann")
    browser = another_browser(api, "ann")
    # Switched off in the database, as if the session had not been revoked.
    with psycopg.connect(connection_string(database_url), autocommit=True) as connection:
        connection.execute("UPDATE app_user SET is_active = false WHERE username = 'ann'")
    assert browser.get("/api/auth/me").status_code == 401
    assert api.patch(f"/api/users/{ann}", json={"is_active": True}).json()["is_active"] is True
    assert another_browser(api, "ann").get("/api/auth/me").status_code == 200
