"""Sealing and opening values: AES-256-GCM with a key of its own for each purpose.

A sealed value is a text envelope, `v1:<key id>:<nonce>:<ciphertext>`. The key id says which
app secret key sealed it, so a key can be replaced (see rotate.py) while old values still open.
The nonce is 96 random bits, new for every value. The purpose is bound into both the subkey and
the authenticated data, so a value sealed for one purpose cannot be opened as another, and a
changed envelope is refused rather than decrypted to something else.
"""

import base64
import binascii
import secrets
from collections.abc import Sequence
from enum import StrEnum

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.vault.keys import SecretKey, VaultError

VERSION = "v1"
NONCE_BYTES = 12
_SALT = b"blindspot-vault-v1"


class Purpose(StrEnum):
    """What a sealed value is for. Each purpose has its own key."""

    PROVIDERS = "providers"
    TARGET_CREDENTIALS = "target-credentials"
    DISCOVERED_CREDENTIALS = "discovered-credentials"
    EVIDENCE = "evidence"


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Vault:
    """Seals with the current key and opens with the current key or a previous one."""

    def __init__(self, current: SecretKey, previous: Sequence[SecretKey] = ()) -> None:
        self.current = current
        self._keys = {key.id: key for key in (*previous, current)}
        self._subkeys: dict[tuple[str, Purpose], bytes] = {}

    def _subkey(self, key: SecretKey, purpose: Purpose) -> bytes:
        cached = self._subkeys.get((key.id, purpose))
        if cached is None:
            cached = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=_SALT,
                info=f"blindspot/{purpose.value}".encode(),
            ).derive(key.material)
            self._subkeys[key.id, purpose] = cached
        return cached

    @staticmethod
    def _context(purpose: Purpose, key_id: str) -> bytes:
        return f"{VERSION}:{key_id}:{purpose.value}".encode()

    def seal(self, purpose: Purpose, plaintext: str) -> str:
        """The envelope for a value."""
        key = self.current
        nonce = secrets.token_bytes(NONCE_BYTES)
        box = AESGCM(self._subkey(key, purpose))
        ciphertext = box.encrypt(nonce, plaintext.encode(), self._context(purpose, key.id))
        return f"{VERSION}:{key.id}:{_encode(nonce)}:{_encode(ciphertext)}"

    def _parse(self, envelope: str) -> tuple[SecretKey, bytes, bytes]:
        parts = envelope.split(":")
        if len(parts) != 4 or parts[0] != VERSION:
            raise VaultError("The value is not sealed in a format this version knows.")
        key = self._keys.get(parts[1])
        if key is None:
            raise VaultError("The value was sealed with a key this vault does not have.")
        try:
            return key, _decode(parts[2]), _decode(parts[3])
        except (binascii.Error, ValueError) as error:
            raise VaultError("The sealed value is damaged.") from error

    def open(self, purpose: Purpose, envelope: str) -> str:
        """The value inside an envelope, or a VaultError if it was changed or is not ours."""
        key, nonce, ciphertext = self._parse(envelope)
        box = AESGCM(self._subkey(key, purpose))
        try:
            return box.decrypt(nonce, ciphertext, self._context(purpose, key.id)).decode()
        except (InvalidTag, ValueError) as error:
            raise VaultError("The sealed value is damaged or is not for this purpose.") from error

    def needs_rotation(self, envelope: str) -> bool:
        """Whether the envelope was sealed with a key other than the current one."""
        key, _, _ = self._parse(envelope)
        return key.id != self.current.id
