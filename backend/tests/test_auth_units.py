"""The pieces of sign-in that need no database: passwords, the limiter, tokens, the setup code
and the cross-site check."""

import asyncio
import re

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from starlette.requests import Request
from tests.conftest import app_of, set_up

from app.auth import passwords
from app.auth.csrf import came_from_this_site
from app.auth.ratelimit import FailureLimiter
from app.auth.setup_code import SetupGate, new_code
from app.auth.tokens import hash_token, new_token

PEPPER = b"pepper-pepper-pepper-pepper-1234"


@pytest.mark.parametrize(
    ("password", "username", "problem"),
    [
        ("short", "ann", "at least 12"),
        ("x" * 300, "ann", "at most 256"),
        ("aaaaaabbbbbb", "ann", "different characters"),
        ("Password1234", "ann", "too common"),
        ("my-ANN-secret-phrase", "ann", "must not contain the username"),
        ("correct horse battery", "an", None),  # a very short name is not worth matching
        ("correct horse battery", "ann", None),
    ],
)
def test_what_a_password_must_be(password: str, username: str, problem: str | None) -> None:
    reason = passwords.password_problem(password, username)
    assert (reason is None) if problem is None else (problem in (reason or ""))


def test_a_hash_is_argon2id_and_checks_the_right_password() -> None:
    stored = asyncio.run(passwords.hash_password("correct horse battery", PEPPER))
    assert stored.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert asyncio.run(passwords.verify_password(stored, "correct horse battery", PEPPER)) == (
        True,
        False,
    )
    assert asyncio.run(passwords.verify_password(stored, "wrong horse battery", PEPPER)) == (
        False,
        False,
    )


def test_the_pepper_is_part_of_the_hash() -> None:
    stored = asyncio.run(passwords.hash_password("correct horse battery", PEPPER))
    other = b"another-pepper-another-pepper-12"
    assert asyncio.run(passwords.verify_password(stored, "correct horse battery", other)) == (
        False,
        False,
    )


def test_a_hash_made_with_weaker_settings_is_flagged_for_rehashing() -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    stored = weak.hash(passwords.mix("correct horse battery", PEPPER))
    assert asyncio.run(passwords.verify_password(stored, "correct horse battery", PEPPER)) == (
        True,
        True,
    )


def test_a_value_that_is_not_a_hash_is_just_wrong() -> None:
    assert asyncio.run(passwords.verify_password("not a hash", "whatever12345", PEPPER)) == (
        False,
        False,
    )


def test_the_decoy_check_runs() -> None:
    asyncio.run(passwords.spend_the_same_time("whatever12345", PEPPER))


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_the_limiter_blocks_after_enough_failures_and_lets_go_after_the_window() -> None:
    clock = Clock()
    limiter = FailureLimiter(3, 60, clock)
    assert limiter.blocked_for("a") == 0
    for _ in range(3):
        limiter.record_failure("a")
        clock.now += 1
    assert limiter.blocked_for("a") == pytest.approx(57, abs=1)
    assert limiter.blocked_for("b") == 0  # another address is not affected
    clock.now += 100
    assert limiter.blocked_for("a") == 0


def test_the_limiter_forgets_quiet_addresses_when_it_holds_too_many(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.auth.ratelimit._MAX_KEYS", 3)
    clock = Clock()
    limiter = FailureLimiter(3, 60, clock)
    for name in ("a", "b"):
        limiter.record_failure(name)
    clock.now += 100
    limiter.record_failure("c")  # recent
    limiter.record_failure("d")  # the limit is reached: a and b are forgotten, c is kept
    assert limiter.tracked() == {"c", "d"}


def test_tokens_are_random_and_stored_hashed() -> None:
    first, second = new_token(), new_token()
    assert first != second
    assert len(first) >= 43
    assert re.fullmatch(r"[0-9a-f]{64}", hash_token(first))
    assert hash_token(first) != first


def test_a_setup_code_looks_like_one_and_is_checked_without_regard_to_case() -> None:
    assert re.fullmatch(r"BLND-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", new_code())
    gate = SetupGate()
    assert gate.accepts("anything") is False  # no code yet
    code = gate.open()
    assert gate.open() == code  # the same code until setup is done
    assert gate.accepts(f" {code.lower()} ") is True
    assert gate.accepts("BLND-AAAA-AAAA-AAAA") is False
    gate.close()
    assert gate.accepts(code) is False


def request_with(headers: dict[str, str]) -> Request:
    raw = [(key.lower().encode(), value.encode()) for key, value in headers.items()]
    return Request({"type": "http", "method": "POST", "headers": raw, "path": "/"})


@pytest.mark.parametrize(
    ("headers", "allowed"),
    [
        ({}, False),
        ({"Sec-Fetch-Site": "same-origin"}, True),
        ({"Sec-Fetch-Site": "none"}, True),
        ({"Sec-Fetch-Site": "same-site"}, False),
        ({"Sec-Fetch-Site": "cross-site"}, False),
        ({"Origin": "https://app.test", "Host": "app.test"}, True),
        ({"Origin": "https://APP.test:8443", "Host": "app.test:8443"}, True),
        ({"Origin": "https://evil.test", "Host": "app.test"}, False),
        ({"Origin": "null", "Host": "app.test"}, False),
        ({"Origin": "https://app.test"}, False),  # no Host to compare with
        (
            {"Origin": "https://evil.test", "Host": "app.test", "Sec-Fetch-Site": "same-origin"},
            False,
        ),
    ],
)
def test_a_request_must_show_it_came_from_this_site(headers: dict[str, str], allowed: bool) -> None:
    assert came_from_this_site(request_with(headers)) is allowed


def test_the_setup_code_is_not_made_when_someone_can_already_sign_in(
    api: TestClient,
) -> None:
    set_up(api)
    gate = SetupGate()
    asyncio.run(gate.prepare(app_of(api).state.database))
    assert gate.code is None
