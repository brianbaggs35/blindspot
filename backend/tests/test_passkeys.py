"""Passkeys, with a software authenticator that answers as a real one would."""

import uuid
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from tests.conftest import GOOD_PASSWORD, add_account, another_browser, app_of, set_up
from tests.software_authenticator import SoftwareAuthenticator

from app.config import Settings, passkey_origin, passkey_rp_id
from app.db.events import connection_string

ORIGIN = "https://localhost"
BASE = "/api/auth/passkeys"


def sql(url: str, statement: str, *arguments: object) -> list[tuple[Any, ...]]:
    with psycopg.connect(connection_string(url), autocommit=True) as connection:
        cursor = connection.execute(statement, arguments)  # type: ignore[arg-type]
        return cursor.fetchall() if cursor.description else []


def add_passkey(
    client: TestClient,
    authenticator: SoftwareAuthenticator,
    name: str = "Laptop",
    *,
    origin: str = ORIGIN,
) -> Any:
    """Add a passkey the way the page does: ask for options, make a credential, send it."""
    started = client.post(f"{BASE}/register/options", json={"password": GOOD_PASSWORD})
    assert started.status_code == 200, started.text
    ceremony = started.json()
    credential = authenticator.make_credential(ceremony["options"], origin)
    return client.post(
        f"{BASE}/register",
        json={"challenge_id": ceremony["challenge_id"], "name": name, "credential": credential},
    )


def sign_in_with(
    client: TestClient,
    authenticator: SoftwareAuthenticator,
    *,
    origin: str = ORIGIN,
    count: int | None = None,
) -> Any:
    """Sign in the way the page does, from a browser that is not signed in."""
    ceremony = client.post(f"{BASE}/login/options").json()
    credential = authenticator.sign_in(ceremony["options"], origin, count=count)
    return client.post(
        f"{BASE}/login", json={"challenge_id": ceremony["challenge_id"], "credential": credential}
    )


def stranger(client: TestClient) -> TestClient:
    """A browser with no session on the same app."""
    return TestClient(
        app_of(client),
        base_url="https://testserver",
        raise_server_exceptions=False,
        headers=dict(client.headers),
    )


@pytest.mark.parametrize(
    ("settings", "origin", "rp_id"),
    [
        ({}, "https://localhost", "localhost"),
        (
            {"hostnames": "pentest.example.com, other.example"},
            "https://pentest.example.com",
            "pentest.example.com",
        ),
        (
            {"hostnames": "pentest.lan", "public_https_port": 8443},
            "https://pentest.lan:8443",
            "pentest.lan",
        ),
        ({"hostnames": "::1"}, "https://[::1]", "::1"),
        (
            {"hostnames": "ignored", "public_origin": "https://bs.example/"},
            "https://bs.example",
            "bs.example",
        ),
    ],
)
def test_where_passkeys_belong(settings: dict[str, Any], origin: str, rp_id: str) -> None:
    configured = Settings.model_validate(settings)
    assert passkey_origin(configured) == origin
    assert passkey_rp_id(configured) == rp_id


def test_add_use_rename_and_remove_a_passkey(api: TestClient, database_url: str) -> None:
    set_up(api)
    phone = SoftwareAuthenticator()
    added = add_passkey(api, phone, "My phone")
    assert added.status_code == 201, added.text
    assert added.json()["name"] == "My phone"
    assert added.json()["transports"] == ["internal"]
    listed = api.get(BASE).json()
    assert [one["name"] for one in listed] == ["My phone"]

    # A different browser, not signed in, signs in with it: no username asked.
    elsewhere = stranger(api)
    answer = sign_in_with(elsewhere, phone)
    assert answer.status_code == 200, answer.text
    assert answer.json()["username"] == "admin"
    assert elsewhere.get("/api/auth/me").status_code == 200
    assert api.get(BASE).json()[0]["last_used_at"] is not None

    renamed = api.patch(f"{BASE}/{listed[0]['id']}", json={"name": "Work phone"})
    assert renamed.json()["name"] == "Work phone"
    removed = api.request("DELETE", f"{BASE}/{listed[0]['id']}", json={"password": GOOD_PASSWORD})
    assert removed.status_code == 204
    assert api.get(BASE).json() == []
    assert sign_in_with(stranger(api), phone).status_code == 401

    actions = [row[0] for row in sql(database_url, "SELECT action FROM audit_event ORDER BY id")]
    assert actions == [
        "auth.setup",
        "passkey.add",
        "passkey.login",
        "passkey.rename",
        "passkey.remove",
        "passkey.login",
    ]


def test_adding_or_removing_a_passkey_asks_for_the_password_again(api: TestClient) -> None:
    set_up(api)
    wrong = api.post(f"{BASE}/register/options", json={"password": "not the one 1"})
    assert (wrong.status_code, wrong.json()["code"]) == (403, "current_password_wrong")
    phone = SoftwareAuthenticator()
    passkey_id = add_passkey(api, phone).json()["id"]
    refused = api.request("DELETE", f"{BASE}/{passkey_id}", json={"password": "not the one 1"})
    assert refused.status_code == 403
    assert len(api.get(BASE).json()) == 1


def test_guessing_the_password_to_add_a_passkey_is_throttled(api: TestClient) -> None:
    set_up(api)
    codes = [
        api.post(f"{BASE}/register/options", json={"password": "not the one 1"}).status_code
        for _ in range(11)
    ]
    assert codes[10] == 429


def test_a_passkey_made_for_another_site_is_refused(api: TestClient) -> None:
    set_up(api)
    phishing = add_passkey(api, SoftwareAuthenticator(), origin="https://evil.example")
    assert (phishing.status_code, phishing.json()["code"]) == (400, "passkey_refused")
    assert api.get(BASE).json() == []


def test_a_sign_in_from_another_site_is_refused(api: TestClient) -> None:
    set_up(api)
    phone = SoftwareAuthenticator()
    add_passkey(api, phone)
    answer = sign_in_with(stranger(api), phone, origin="https://evil.example")
    assert (answer.status_code, answer.json()["code"]) == (401, "invalid_credentials")


def test_a_passkey_without_user_verification_is_refused(api: TestClient) -> None:
    set_up(api)
    ceremony = api.post(f"{BASE}/register/options", json={"password": GOOD_PASSWORD}).json()
    credential = SoftwareAuthenticator().make_credential(
        ceremony["options"], ORIGIN, verified=False
    )
    answer = api.post(
        f"{BASE}/register",
        json={"challenge_id": ceremony["challenge_id"], "name": "x", "credential": credential},
    )
    assert answer.status_code == 400


def test_a_challenge_works_once(api: TestClient) -> None:
    set_up(api)
    phone = SoftwareAuthenticator()
    add_passkey(api, phone)
    browser = stranger(api)
    ceremony = browser.post(f"{BASE}/login/options").json()
    credential = phone.sign_in(ceremony["options"], ORIGIN)
    body = {"challenge_id": ceremony["challenge_id"], "credential": credential}
    assert browser.post(f"{BASE}/login", json=body).status_code == 200
    assert stranger(api).post(f"{BASE}/login", json=body).status_code == 401  # replayed


def test_an_expired_challenge_is_refused(api: TestClient, database_url: str) -> None:
    set_up(api)
    phone = SoftwareAuthenticator()
    add_passkey(api, phone)
    browser = stranger(api)
    ceremony = browser.post(f"{BASE}/login/options").json()
    sql(database_url, "UPDATE webauthn_challenge SET expires_at = now() - interval '1 second'")
    credential = phone.sign_in(ceremony["options"], ORIGIN)
    answer = browser.post(
        f"{BASE}/login", json={"challenge_id": ceremony["challenge_id"], "credential": credential}
    )
    assert answer.status_code == 401


def test_a_challenge_cannot_be_used_for_something_else(api: TestClient) -> None:
    set_up(api)
    sign_in_options = stranger(api).post(f"{BASE}/login/options").json()
    credential = SoftwareAuthenticator().make_credential(
        api.post(f"{BASE}/register/options", json={"password": GOOD_PASSWORD}).json()["options"],
        ORIGIN,
    )
    # A sign-in challenge offered to the registration route.
    answer = api.post(
        f"{BASE}/register",
        json={
            "challenge_id": sign_in_options["challenge_id"],
            "name": "x",
            "credential": credential,
        },
    )
    assert answer.status_code == 400
    # Or one that does not exist.
    unknown = api.post(
        f"{BASE}/register",
        json={"challenge_id": str(uuid.uuid4()), "name": "x", "credential": credential},
    )
    assert unknown.status_code == 400


def test_someone_elses_challenge_does_not_work_for_you(api: TestClient) -> None:
    set_up(api)
    add_account(api, "ann")
    ann = another_browser(api, "ann")
    mine = api.post(f"{BASE}/register/options", json={"password": GOOD_PASSWORD}).json()
    credential = SoftwareAuthenticator().make_credential(mine["options"], ORIGIN)
    answer = ann.post(
        f"{BASE}/register",
        json={"challenge_id": mine["challenge_id"], "name": "x", "credential": credential},
    )
    assert answer.status_code == 400


def test_a_copied_passkey_is_noticed_by_its_counter(api: TestClient, database_url: str) -> None:
    set_up(api)
    phone = SoftwareAuthenticator()
    add_passkey(api, phone)
    assert sign_in_with(stranger(api), phone, count=7).status_code == 200
    copy = sign_in_with(stranger(api), phone, count=3)  # the counter went backwards
    assert copy.status_code == 401
    rows = sql(database_url, "SELECT action, outcome FROM audit_event ORDER BY id DESC LIMIT 1")
    assert rows == [("passkey.clone_suspected", "failure")]


def test_a_synced_passkey_that_always_reports_zero_is_fine(api: TestClient) -> None:
    set_up(api)
    synced = SoftwareAuthenticator(synced=True)
    added = add_passkey(api, synced).json()
    assert added["backup_eligible"] is True
    assert added["backed_up"] is True
    for _ in range(3):
        assert sign_in_with(stranger(api), synced, count=0).status_code == 200


def test_an_unknown_passkey_is_refused(api: TestClient) -> None:
    set_up(api)
    answer = sign_in_with(stranger(api), SoftwareAuthenticator())
    assert (answer.status_code, answer.json()["code"]) == (401, "invalid_credentials")


@pytest.mark.parametrize("raw_id", [None, 42, "***not base64***"])
def test_a_credential_with_a_missing_or_broken_id_is_refused(
    api: TestClient, raw_id: object
) -> None:
    set_up(api)
    browser = stranger(api)
    ceremony = browser.post(f"{BASE}/login/options").json()
    answer = browser.post(
        f"{BASE}/login",
        json={"challenge_id": ceremony["challenge_id"], "credential": {"rawId": raw_id}},
    )
    assert answer.status_code == 401


def test_a_switched_off_account_cannot_use_its_passkey(api: TestClient) -> None:
    set_up(api)
    ann_id = add_account(api, "ann")
    ann = another_browser(api, "ann")
    phone = SoftwareAuthenticator()
    add_passkey(ann, phone)
    api.patch(f"/api/users/{ann_id}", json={"is_active": False})
    assert sign_in_with(stranger(api), phone).status_code == 401


def test_failed_passkey_attempts_are_throttled_apart_from_passwords(api: TestClient) -> None:
    set_up(api)
    nobody = SoftwareAuthenticator()
    codes = [sign_in_with(stranger(api), nobody).status_code for _ in range(10)]
    assert codes == [401] * 10
    browser = stranger(api)
    assert browser.post(f"{BASE}/login/options").status_code == 429
    body: dict[str, Any] = {"challenge_id": str(uuid.uuid4()), "credential": {}}
    assert browser.post(f"{BASE}/login", json=body).status_code == 429
    # The password's own limits are untouched.
    fresh = stranger(api)
    password = {"username": "admin", "password": GOOD_PASSWORD}
    assert fresh.post("/api/auth/login", json=password).status_code == 200


def test_failed_attempts_to_add_a_passkey_are_throttled(api: TestClient) -> None:
    set_up(api)
    codes = [
        add_passkey(api, SoftwareAuthenticator(), origin="https://evil.example").status_code
        for _ in range(11)
    ]
    assert codes[:10] == [400] * 10
    assert codes[10] == 429


def test_an_account_can_have_twenty_passkeys_and_no_more(
    api: TestClient, database_url: str
) -> None:
    set_up(api)
    ceremony = api.post(f"{BASE}/register/options", json={"password": GOOD_PASSWORD}).json()
    for number in range(20):
        sql(
            database_url,
            "INSERT INTO passkey (id, user_id, credential_id, public_key, sign_count, transports,"
            " name, backup_eligible, backed_up) SELECT gen_random_uuid(), id, %s, %s, 0, '[]',"
            " %s, false, false FROM app_user",
            f"credential-{number}".encode(),
            b"key",
            f"key {number}",
        )
    refused = api.post(f"{BASE}/register/options", json={"password": GOOD_PASSWORD})
    assert (refused.status_code, refused.json()["code"]) == (409, "too_many_passkeys")
    credential = SoftwareAuthenticator().make_credential(ceremony["options"], ORIGIN)
    late = api.post(
        f"{BASE}/register",
        json={"challenge_id": ceremony["challenge_id"], "name": "x", "credential": credential},
    )
    assert late.status_code == 409


def test_you_cannot_touch_someone_elses_passkey(api: TestClient) -> None:
    set_up(api)
    add_account(api, "ann")
    ann = another_browser(api, "ann")
    passkey_id = add_passkey(ann, SoftwareAuthenticator()).json()["id"]
    assert api.get(BASE).json() == []
    assert api.patch(f"{BASE}/{passkey_id}", json={"name": "mine now"}).status_code == 404
    removed = api.request("DELETE", f"{BASE}/{passkey_id}", json={"password": GOOD_PASSWORD})
    assert removed.status_code == 404
    assert len(ann.get(BASE).json()) == 1


def test_removing_an_account_removes_its_passkeys(api: TestClient, database_url: str) -> None:
    set_up(api)
    ann_id = add_account(api, "ann")
    add_passkey(another_browser(api, "ann"), SoftwareAuthenticator())
    assert sql(database_url, "SELECT count(*) FROM passkey") == [(1,)]
    api.delete(f"/api/users/{ann_id}")
    assert sql(database_url, "SELECT count(*) FROM passkey") == [(0,)]


def test_old_challenges_are_cleared_when_new_ones_are_made(
    api: TestClient, database_url: str
) -> None:
    set_up(api)
    stranger(api).post(f"{BASE}/login/options")
    sql(database_url, "UPDATE webauthn_challenge SET expires_at = now() - interval '1 hour'")
    stranger(api).post(f"{BASE}/login/options")
    assert sql(database_url, "SELECT count(*) FROM webauthn_challenge") == [(1,)]


def test_a_viewer_can_have_passkeys_too(api: TestClient) -> None:
    set_up(api)
    add_account(api, "vera", "viewer")
    vera = another_browser(api, "vera")
    phone = SoftwareAuthenticator()
    assert add_passkey(vera, phone).status_code == 201
    assert sign_in_with(stranger(api), phone).json()["role"] == "viewer"
