"""Secrets are hidden from logs."""

import json
import logging

import pytest
import structlog

from app.log import configure_logging
from app.redact import REDACTED, RedactingFilter, mask, redact, redact_value
from app.vault import Purpose, SecretKey, Vault

SECRETS = [
    "sk-ant-api03-abcdefghijklmnop1234",
    "sk-proj-abcdefghijklmnop1234567",
    "ghp_abcdefghijklmnopqrstuvwxyz0123",
    "AKIAABCDEFGHIJKLMNOP",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.c2lnbmF0dXJl",
    "-----BEGIN PRIVATE KEY-----\nMIIBVgIBADANBg\n-----END PRIVATE KEY-----",
    Vault(SecretKey.from_text("k" * 40)).seal(Purpose.PROVIDERS, "value"),
]


@pytest.mark.parametrize("secret", SECRETS)
def test_secret_shaped_text_is_hidden(secret: str) -> None:
    assert (
        redact(f"calling the provider with {secret} now")
        == f"calling the provider with {REDACTED} now"
    )


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        ("Authorization: Bearer abcdef0123456789", "Authorization"),
        ("api_key=abcd1234 next", "api_key="),
        ('{"password": "hunter2", "user": "bob"}', '"user": "bob"'),
        ("postgres://app:s3cret@db/blindspot", "@db/blindspot"),
        ("token=abc123&page=2", "page=2"),
    ],
)
def test_assignments_hide_the_value_and_keep_the_rest(text: str, kept: str) -> None:
    hidden = redact(text)
    assert kept in hidden
    assert REDACTED in hidden
    for leaked in ("abcdef0123456789", "abcd1234", "hunter2", "s3cret", "abc123&"):
        assert leaked not in hidden


def test_ordinary_text_and_counts_are_left_alone() -> None:
    text = "scan finished in 12s, input_tokens=1200 output_tokens=300 on https://example.com/a"
    assert redact(text) == text


def test_values_are_hidden_inside_containers_and_by_key_name() -> None:
    value = {
        "password": "p",
        "note": f"key {SECRETS[0]}",
        "items": [SECRETS[3], 7, {"api_key": "k"}],
        "bytes": b"raw",
        "deep": {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": "x"}}}}}}}},
    }
    result = redact_value(value)
    assert result["password"] == REDACTED
    assert SECRETS[0] not in result["note"]
    assert result["items"] == [REDACTED, 7, {"api_key": REDACTED}]
    assert result["bytes"] == b"raw"
    assert result["deep"]["a"]["b"]["c"]["d"]["e"]["f"]["g"] == REDACTED


def test_structured_logs_never_hold_a_secret(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    structlog.get_logger().info(
        "provider call", api_key=SECRETS[0], detail=f"failed with {SECRETS[1]}"
    )
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["api_key"] == REDACTED
    assert SECRETS[1] not in line["detail"]


def test_standard_library_logs_never_hold_a_secret(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    logging.getLogger("uvicorn.error").warning("bad key %s", SECRETS[0])
    output = capsys.readouterr().out
    assert "bad key" in output
    assert SECRETS[0] not in output


def test_the_filter_lets_every_record_through() -> None:
    record = logging.LogRecord("x", logging.INFO, "", 0, "a %s", (SECRETS[3],), None)
    assert RedactingFilter().filter(record)
    assert record.getMessage() == f"a {REDACTED}"


@pytest.mark.parametrize(
    ("secret", "shown"),
    [("short", "••••"), ("sk-ant-api03-abcdefghijWXYZ", "••••WXYZ")],
)
def test_a_stored_secret_is_shown_as_its_last_four_characters_at_most(
    secret: str, shown: str
) -> None:
    assert mask(secret) == shown
