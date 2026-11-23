"""First-run setup, sign-in, sessions and the cookie, through the real routes and a real
database."""

import uuid
from datetime import timedelta

import psycopg
import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from tests.conftest import GOOD_PASSWORD, SAME_SITE, another_browser, app_of, set_up, setup_code

from app.auth.deps import COOKIE_NAME
from app.auth.passwords import mix
from app.config import get_settings
from app.db.base import Base
from app.db.events import connection_string
from app.db.models import AuthSecret
from app.vault import SecretKey, Vault, get_vault, set_vault
from app.vault.rotate import rotate


def sql(url: str, statement: str, *arguments: object) -> list[tuple[object, ...]]:
    with psycopg.connect(connection_string(url), autocommit=True) as connection:
        cursor = connection.execute(statement, arguments)  # type: ignore[arg-type]
        return cursor.fetchall() if cursor.description else []


def audit_actions(url: str) -> list[tuple[object, ...]]:
    return sql(url, "SELECT action, outcome, actor_name FROM audit_event ORDER BY id")


def test_before_setup_the_app_says_so_and_prints_a_code(api: TestClient) -> None:
    status = api.get("/api/auth/status").json()
    assert status == {"setup_required": True, "user": None}
    assert setup_code(api).startswith("BLND-")


def test_setup_makes_the_first_administrator_and_signs_them_in(
    api: TestClient, database_url: str
) -> None:
    set_up(api, "Admin")
    assert api.get("/api/auth/status").json()["user"]["username"] == "admin"
    assert api.get("/api/auth/status").json()["setup_required"] is False
    me = api.get("/api/auth/me").json()
    assert me["role"] == "admin"
    assert "password_hash" not in me
    assert audit_actions(database_url) == [("auth.setup", "success", "admin")]


def test_the_cookie_is_locked_down(api: TestClient) -> None:
    code = setup_code(api)
    answer = api.post(
        "/api/auth/setup",
        json={"setup_code": code, "username": "admin", "password": GOOD_PASSWORD},
    )
    cookie = answer.headers["set-cookie"].lower()
    assert f"{COOKIE_NAME}=" in cookie
    for flag in ("httponly", "secure", "samesite=strict", "path=/", "max-age=43200"):
        assert flag in cookie
    assert answer.headers["cache-control"] == "no-store"


def test_setup_works_once(api: TestClient) -> None:
    set_up(api)
    again = api.post(
        "/api/auth/setup",
        json={"setup_code": "BLND-AAAA-AAAA-AAAA", "username": "second", "password": GOOD_PASSWORD},
    )
    assert again.status_code == 409
    assert again.json()["code"] == "setup_complete"


def test_setup_needs_the_code_from_the_log(api: TestClient, database_url: str) -> None:
    wrong = api.post(
        "/api/auth/setup",
        json={"setup_code": "BLND-AAAA-AAAA-AAAA", "username": "admin", "password": GOOD_PASSWORD},
    )
    assert wrong.status_code == 403
    assert wrong.json()["code"] == "setup_code_invalid"
    assert api.get("/api/auth/status").json()["setup_required"] is True
    assert audit_actions(database_url) == [("auth.setup", "failure", "admin")]


def test_setup_refuses_a_weak_password_and_a_bad_username(api: TestClient) -> None:
    code = setup_code(api)
    weak = api.post(
        "/api/auth/setup", json={"setup_code": code, "username": "admin", "password": "short"}
    )
    assert weak.status_code == 422
    assert weak.json()["code"] == "password_rejected"
    bad_name = api.post(
        "/api/auth/setup",
        json={"setup_code": code, "username": "no spaces", "password": GOOD_PASSWORD},
    )
    assert bad_name.json()["code"] == "username_invalid"
    assert api.get("/api/auth/status").json()["setup_required"] is True


def test_guessing_the_setup_code_is_throttled(api: TestClient) -> None:
    body = {"setup_code": "BLND-AAAA-AAAA-AAAA", "username": "admin", "password": GOOD_PASSWORD}
    codes = [api.post("/api/auth/setup", json=body).status_code for _ in range(11)]
    assert codes[:10] == [403] * 10
    assert codes[10] == 429


def test_signing_in_and_out(api: TestClient, database_url: str) -> None:
    set_up(api)
    browser = another_browser(api, "admin")
    assert browser.get("/api/auth/me").json()["username"] == "admin"
    assert browser.post("/api/auth/logout").status_code == 204
    assert browser.get("/api/auth/me").status_code == 401
    assert [row[0] for row in audit_actions(database_url)] == [
        "auth.setup",
        "auth.login",
        "auth.logout",
    ]


def test_every_failure_to_sign_in_looks_the_same(api: TestClient) -> None:
    set_up(api)
    unknown = api.post("/api/auth/login", json={"username": "nobody", "password": GOOD_PASSWORD})
    wrong = api.post("/api/auth/login", json={"username": "admin", "password": "not the one 1"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["code"] == wrong.json()["code"] == "invalid_credentials"
    assert unknown.json()["title"] == wrong.json()["title"]


def test_usernames_are_not_case_sensitive(api: TestClient) -> None:
    set_up(api)
    assert another_browser(api, "  ADMIN ").get("/api/auth/me").status_code == 200


def test_too_many_wrong_passwords_lock_the_account(api: TestClient, database_url: str) -> None:
    set_up(api)
    for _ in range(5):
        api.post("/api/auth/login", json={"username": "admin", "password": "not the one 1"})
    # Even the right password is refused now, and says no more than a wrong one.
    locked = api.post("/api/auth/login", json={"username": "admin", "password": GOOD_PASSWORD})
    assert locked.status_code == 401
    assert locked.json()["code"] == "invalid_credentials"
    assert "auth.lockout" in [row[0] for row in audit_actions(database_url)]
    sql(database_url, "UPDATE app_user SET locked_until = now() - interval '1 minute'")
    assert another_browser(api, "admin").get("/api/auth/me").status_code == 200


def test_a_good_sign_in_resets_the_count(api: TestClient, database_url: str) -> None:
    set_up(api)
    for _ in range(4):
        api.post("/api/auth/login", json={"username": "admin", "password": "not the one 1"})
    another_browser(api, "admin")
    assert sql(database_url, "SELECT failed_attempts FROM app_user") == [(0,)]


def test_an_address_that_keeps_failing_is_slowed_down(api: TestClient) -> None:
    set_up(api)
    answers = [
        api.post("/api/auth/login", json={"username": f"user{n}", "password": "whatever12345"})
        for n in range(11)
    ]
    assert [one.status_code for one in answers[:10]] == [401] * 10
    assert answers[10].status_code == 429
    assert int(answers[10].headers["retry-after"]) > 0


def test_a_disabled_account_cannot_sign_in_and_is_signed_out(api: TestClient) -> None:
    set_up(api)
    other = api.post(
        "/api/users", json={"username": "ann", "role": "viewer", "password": GOOD_PASSWORD}
    ).json()["id"]
    ann = another_browser(api, "ann")
    api.patch(f"/api/users/{other}", json={"is_active": False})
    assert ann.get("/api/auth/me").status_code == 401
    refused = api.post("/api/auth/login", json={"username": "ann", "password": GOOD_PASSWORD})
    assert refused.status_code == 401


def test_a_hash_with_old_settings_is_replaced_at_sign_in(
    api: TestClient, database_url: str
) -> None:
    set_up(api)
    # The pepper is stored sealed; read it through the app's own column type.
    engine = create_engine(database_url)
    with engine.connect() as connection:
        plain = connection.execute(select(AuthSecret.value)).scalar_one()
    engine.dispose()
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(
        mix(GOOD_PASSWORD, plain.encode())
    )
    sql(database_url, "UPDATE app_user SET password_hash = %s", weak)
    another_browser(api, "admin")
    (stored,) = sql(database_url, "SELECT password_hash FROM app_user")[0]
    assert str(stored).startswith("$argon2id$v=19$m=65536,t=3,p=4$")


def test_the_session_is_stored_as_a_hash_only(api: TestClient, database_url: str) -> None:
    set_up(api)
    token = api.cookies[COOKIE_NAME]
    (stored,) = sql(database_url, "SELECT token_hash FROM auth_session")[0]
    assert stored != token
    assert token not in str(sql(database_url, "SELECT * FROM auth_session"))


def test_a_session_ends_when_idle_too_long_or_too_old(api: TestClient, database_url: str) -> None:
    set_up(api)
    settings = get_settings()
    idle = timedelta(minutes=settings.session_idle_minutes + 1)
    sql(database_url, "UPDATE auth_session SET last_seen_at = now() - %s", idle)
    assert api.get("/api/auth/me").status_code == 401

    other = another_browser(api, "admin")
    assert other.get("/api/auth/me").status_code == 200
    sql(database_url, "UPDATE auth_session SET expires_at = now() - interval '1 second'")
    assert other.get("/api/auth/me").status_code == 401


def test_using_the_app_keeps_a_session_alive(api: TestClient, database_url: str) -> None:
    set_up(api)
    sql(database_url, "UPDATE auth_session SET last_seen_at = now() - interval '5 minutes'")
    assert api.get("/api/auth/me").status_code == 200
    (seen,) = sql(
        database_url, "SELECT now() - last_seen_at < interval '1 minute' FROM auth_session"
    )[0]
    assert seen is True


def test_you_can_see_and_end_your_own_sessions(api: TestClient) -> None:
    set_up(api)
    laptop = another_browser(api, "admin")
    listed = api.get("/api/auth/sessions").json()
    assert len(listed) == 2
    assert [one["current"] for one in listed].count(True) == 1
    other = next(one for one in listed if not one["current"])
    assert api.delete(f"/api/auth/sessions/{other['id']}").status_code == 204
    assert laptop.get("/api/auth/me").status_code == 401
    assert api.delete(f"/api/auth/sessions/{other['id']}").status_code == 404
    assert api.delete(f"/api/auth/sessions/{uuid.uuid4()}").status_code == 404


def test_you_cannot_end_someone_elses_session(api: TestClient) -> None:
    set_up(api)
    api.post("/api/users", json={"username": "ann", "role": "viewer", "password": GOOD_PASSWORD})
    ann = another_browser(api, "ann")
    ann_session = ann.get("/api/auth/sessions").json()[0]["id"]
    assert api.delete(f"/api/auth/sessions/{ann_session}").status_code == 404
    assert ann.get("/api/auth/me").status_code == 200


def test_changing_your_password_signs_out_your_other_browsers(api: TestClient) -> None:
    set_up(api)
    laptop = another_browser(api, "admin")
    answer = api.post(
        "/api/auth/password",
        json={"current_password": GOOD_PASSWORD, "new_password": "a brand new passphrase"},
    )
    assert answer.status_code == 204
    assert api.get("/api/auth/me").status_code == 200  # this browser stays
    assert laptop.get("/api/auth/me").status_code == 401
    assert (
        another_browser(api, "admin", "a brand new passphrase").get("/api/auth/me").status_code
        == 200
    )
    old = api.post("/api/auth/login", json={"username": "admin", "password": GOOD_PASSWORD})
    assert old.status_code == 401


def test_changing_your_password_needs_the_current_one_and_a_good_new_one(
    api: TestClient,
) -> None:
    set_up(api)
    wrong = api.post(
        "/api/auth/password",
        json={"current_password": "not the one 1", "new_password": "a brand new passphrase"},
    )
    assert (wrong.status_code, wrong.json()["code"]) == (403, "current_password_wrong")
    weak = api.post(
        "/api/auth/password", json={"current_password": GOOD_PASSWORD, "new_password": "short"}
    )
    assert (weak.status_code, weak.json()["code"]) == (422, "password_rejected")


def test_guessing_the_current_password_is_throttled(api: TestClient) -> None:
    set_up(api)
    body = {"current_password": "not the one 1", "new_password": "a brand new passphrase"}
    codes = [api.post("/api/auth/password", json=body).status_code for _ in range(11)]
    assert codes[10] == 429


def test_requests_without_a_session_are_refused(api: TestClient) -> None:
    fresh = TestClient(app_of(api), base_url="https://testserver", headers=SAME_SITE)
    assert fresh.get("/api/auth/me").status_code == 401
    assert fresh.get("/api/users").status_code == 401
    assert fresh.get("/api/audit").status_code == 401
    assert fresh.get("/api/auth/status").status_code == 200


@pytest.mark.parametrize("flag", ["not-a-token", ""])
def test_a_made_up_cookie_is_no_session(api: TestClient, flag: str) -> None:
    fresh = TestClient(app_of(api), base_url="https://testserver", headers=SAME_SITE)
    fresh.cookies.set(COOKIE_NAME, flag)
    assert fresh.get("/api/auth/me").status_code == 401


def test_passwords_still_work_after_the_secret_key_is_rotated(
    api: TestClient, database_url: str
) -> None:
    """The pepper is sealed with the app key, so rotating the key must carry it over."""
    set_up(api)
    old = get_vault()
    new = Vault(SecretKey.from_text("a-brand-new-key-0123456789abcdef0123456789"), [old.current])
    engine = create_engine(database_url)
    with engine.begin() as connection:
        assert rotate(connection, Base.metadata, new) >= 1
    engine.dispose()
    set_vault(new)
    assert another_browser(api, "admin").get("/api/auth/me").status_code == 200
