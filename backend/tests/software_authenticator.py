"""A software WebAuthn authenticator for the tests: it makes the same answers a browser would
forward from a real passkey (ES256, "none" attestation, user verification), so the app's checks
run for real instead of being mocked."""

import hashlib
import json
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

USER_PRESENT = 0x01
USER_VERIFIED = 0x04
BACKUP_ELIGIBLE = 0x08
BACKED_UP = 0x10
ATTESTED = 0x40


def b64(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text: str) -> bytes:
    return urlsafe_b64decode(text + "=" * (-len(text) % 4))


class SoftwareAuthenticator:
    """One passkey."""

    def __init__(self, *, synced: bool = False) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = secrets.token_bytes(32)
        self.sign_count = 0
        self.synced = synced
        self.user_handle = b""

    def _flags(self, *extra: int) -> int:
        flags = USER_PRESENT | USER_VERIFIED
        for one in extra:
            flags |= one
        if self.synced:
            flags |= BACKUP_ELIGIBLE | BACKED_UP
        return flags

    def _cose_key(self) -> bytes:
        numbers = self.key.public_key().public_numbers()
        return cbor2.dumps(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def make_credential(
        self, options: dict[str, Any], origin: str, *, verified: bool = True
    ) -> dict[str, Any]:
        """The answer to a registration challenge."""
        self.user_handle = unb64(options["user"]["id"])
        rp_id = options["rp"]["id"]
        client_data = json.dumps(
            {
                "type": "webauthn.create",
                "challenge": options["challenge"],
                "origin": origin,
                "crossOrigin": False,
            }
        ).encode()
        key = self._cose_key()
        flags = self._flags(ATTESTED)
        if not verified:
            flags &= ~USER_VERIFIED
        auth_data = (
            hashlib.sha256(rp_id.encode()).digest()
            + bytes([flags])
            + self.sign_count.to_bytes(4, "big")
            + bytes(16)
            + len(self.credential_id).to_bytes(2, "big")
            + self.credential_id
            + key
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": b64(self.credential_id),
            "rawId": b64(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64(client_data),
                "attestationObject": b64(attestation),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
        }

    def sign_in(
        self, options: dict[str, Any], origin: str, *, count: int | None = None
    ) -> dict[str, Any]:
        """The answer to a sign-in challenge. `count` overrides the counter (a synced passkey
        reports 0 every time)."""
        self.sign_count = self.sign_count + 1 if count is None else count
        client_data = json.dumps(
            {
                "type": "webauthn.get",
                "challenge": options["challenge"],
                "origin": origin,
                "crossOrigin": False,
            }
        ).encode()
        auth_data = (
            hashlib.sha256(options["rpId"].encode()).digest()
            + bytes([self._flags()])
            + self.sign_count.to_bytes(4, "big")
        )
        signature = self.key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": b64(self.credential_id),
            "rawId": b64(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64(client_data),
                "authenticatorData": b64(auth_data),
                "signature": b64(signature),
                "userHandle": b64(self.user_handle),
            },
            "clientExtensionResults": {},
        }
