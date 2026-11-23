"""Where the key comes from."""

import stat
from pathlib import Path

import pytest

from app.config import Settings
from app.vault import SecretKey, VaultError, build_vault, generate_key, get_vault, open_vault
from app.vault.keys import load_key


def settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for name in ("SECRET_KEY", "SECRET_KEY_FILE", "PREVIOUS_SECRET_KEY", "DATA_DIR"):
        monkeypatch.delenv(f"BLINDSPOT_{name}", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(f"BLINDSPOT_{name}", value)
    return Settings()


def test_a_generated_key_is_long_and_different_each_time() -> None:
    assert len(generate_key()) == 96
    first, second = generate_key(), generate_key()
    assert first != second


def test_a_short_key_is_refused() -> None:
    with pytest.raises(VaultError, match="at least 32"):
        SecretKey.from_text("too short")


def test_the_key_id_is_not_the_key() -> None:
    key = SecretKey.from_text("c" * 40)
    assert len(key.id) == 8
    assert key.id not in "c" * 40


def test_the_key_can_be_given_as_a_value(monkeypatch: pytest.MonkeyPatch) -> None:
    key = load_key(settings(monkeypatch, SECRET_KEY="d" * 40))
    assert key == SecretKey.from_text("d" * 40)


def test_the_key_can_be_given_as_a_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "key"
    path.write_text("e" * 40 + "\n")  # a trailing newline is not part of the key
    key = load_key(settings(monkeypatch, SECRET_KEY_FILE=str(path)))
    assert key == SecretKey.from_text("e" * 40)


def test_a_key_file_that_cannot_be_read_is_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = settings(monkeypatch, SECRET_KEY_FILE=str(tmp_path / "missing"))
    with pytest.raises(VaultError, match="cannot be read"):
        load_key(config)


def test_without_a_key_one_is_generated_once_and_kept_private(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = settings(monkeypatch, DATA_DIR=str(tmp_path))
    first = load_key(config)
    second = load_key(config)
    path = tmp_path / "secrets" / "secret.key"
    assert first == second == SecretKey.from_text(path.read_text())
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_a_key_that_cannot_be_saved_says_what_to_do(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blocked = tmp_path / "file"
    blocked.write_text("not a directory")
    config = settings(monkeypatch, DATA_DIR=str(blocked))
    with pytest.raises(VaultError, match="BLINDSPOT_SECRET_KEY"):
        load_key(config)


def test_the_vault_opens_what_the_previous_key_sealed(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.vault import Purpose, Vault  # noqa: PLC0415

    old = Vault(SecretKey.from_text("f" * 40)).seal(Purpose.PROVIDERS, "value")
    vault = build_vault(settings(monkeypatch, SECRET_KEY="g" * 40, PREVIOUS_SECRET_KEY="f" * 40))
    assert vault.open(Purpose.PROVIDERS, old) == "value"


def test_opening_the_vault_makes_it_the_current_one(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = open_vault(settings(monkeypatch, SECRET_KEY="h" * 40))
    assert get_vault() is vault


def test_there_is_no_vault_until_one_is_opened() -> None:
    with pytest.raises(VaultError, match="not open"):
        get_vault()
