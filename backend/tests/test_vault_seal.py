"""Sealing and opening values."""

import pytest

from app.vault import Purpose, SecretKey, Vault, VaultError

KEY = SecretKey.from_text("a" * 40)
OTHER = SecretKey.from_text("b" * 40)


def test_a_value_comes_back_as_it_went_in() -> None:
    vault = Vault(KEY)
    envelope = vault.seal(Purpose.PROVIDERS, "sk-ant-secret-value")
    assert vault.open(Purpose.PROVIDERS, envelope) == "sk-ant-secret-value"


def test_the_envelope_shows_neither_the_value_nor_its_length_class() -> None:
    envelope = Vault(KEY).seal(Purpose.PROVIDERS, "sk-ant-secret-value")
    assert "secret" not in envelope
    version, key_id, nonce, _ciphertext = envelope.split(":")
    assert (version, key_id) == ("v1", KEY.id)
    assert len(nonce) == 16  # 12 bytes, base64 without padding


def test_the_same_value_is_sealed_differently_each_time() -> None:
    vault = Vault(KEY)
    first = vault.seal(Purpose.EVIDENCE, "same")
    second = vault.seal(Purpose.EVIDENCE, "same")
    assert first != second


@pytest.mark.parametrize("value", ["", "ünïcödé ✓", "x" * 100_000])
def test_any_text_round_trips(value: str) -> None:
    vault = Vault(KEY)
    assert vault.open(Purpose.EVIDENCE, vault.seal(Purpose.EVIDENCE, value)) == value


def test_a_value_sealed_for_one_purpose_will_not_open_as_another() -> None:
    vault = Vault(KEY)
    envelope = vault.seal(Purpose.PROVIDERS, "value")
    with pytest.raises(VaultError):
        vault.open(Purpose.TARGET_CREDENTIALS, envelope)


def test_a_changed_envelope_is_refused() -> None:
    vault = Vault(KEY)
    version, key_id, nonce, ciphertext = vault.seal(Purpose.PROVIDERS, "value").split(":")
    flipped = ("A" if ciphertext[0] != "A" else "B") + ciphertext[1:]
    damaged = ":".join([version, key_id, nonce, flipped])
    with pytest.raises(VaultError):
        vault.open(Purpose.PROVIDERS, damaged)


@pytest.mark.parametrize(
    "envelope",
    ["", "plain text", "v2:00000000:AAAA:AAAA", "v1:only:three", "v1::::"],
)
def test_text_that_is_not_an_envelope_is_refused(envelope: str) -> None:
    vault = Vault(KEY)
    with pytest.raises(VaultError):
        vault.open(Purpose.PROVIDERS, envelope)


@pytest.mark.parametrize("damage", ["A:A", "!!!!:!!!!", "AAAAAAAAAAAAAAAA:AAAA"])
def test_damaged_encoding_is_refused(damage: str) -> None:
    vault = Vault(KEY)
    envelope = f"v1:{KEY.id}:{damage}"
    with pytest.raises(VaultError, match="damaged"):
        vault.open(Purpose.PROVIDERS, envelope)


def test_a_value_from_an_unknown_key_is_refused() -> None:
    envelope = Vault(OTHER).seal(Purpose.PROVIDERS, "value")
    vault = Vault(KEY)
    with pytest.raises(VaultError, match="does not have"):
        vault.open(Purpose.PROVIDERS, envelope)


def test_a_previous_key_still_opens_what_it_sealed() -> None:
    old = Vault(OTHER).seal(Purpose.PROVIDERS, "value")
    vault = Vault(KEY, [OTHER])
    assert vault.open(Purpose.PROVIDERS, old) == "value"
    assert vault.needs_rotation(old)
    assert not vault.needs_rotation(vault.seal(Purpose.PROVIDERS, "value"))
