"""The app secret key: where it comes from, and how long it must be."""

import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

import structlog

from app.config import Settings

MIN_KEY_LENGTH = 32
KEY_FILE = Path("secrets") / "secret.key"

log = structlog.get_logger()


class VaultError(Exception):
    """A key problem, or a value that cannot be opened. The message is safe to show."""


@dataclass(frozen=True)
class SecretKey:
    """Key material and a short public id, so an envelope can say which key sealed it."""

    material: bytes
    id: str

    @classmethod
    def from_text(cls, text: str) -> SecretKey:
        """Make a key from its text. Short keys are refused: the key is the vault's only secret."""
        text = text.strip()
        if len(text) < MIN_KEY_LENGTH:
            raise VaultError(
                f"The secret key must be at least {MIN_KEY_LENGTH} characters. "
                "Make one with: python -m app.vault generate"
            )
        material = text.encode()
        return cls(material=material, id=hashlib.sha256(material).hexdigest()[:8])


def generate_key() -> str:
    """A new random key: 96 hexadecimal characters (384 bits)."""
    return secrets.token_hex(48)


def _generated_key(data_dir: Path) -> str:
    """The key saved in the data directory, made on first use."""
    path = data_dir / KEY_FILE
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # O_EXCL: if two processes start together, only one writes, and both read the same key.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text()
    except OSError as error:
        raise VaultError(
            f"There is no secret key and one cannot be saved in {path.parent}. "
            "Set BLINDSPOT_SECRET_KEY or BLINDSPOT_SECRET_KEY_FILE."
        ) from error
    key = generate_key()
    with os.fdopen(descriptor, "w") as handle:
        handle.write(key)
    log.warning("secret_key_generated", path=str(path))
    return key


def load_key(settings: Settings) -> SecretKey:
    """The current key: the value, else the file, else one generated in the data directory."""
    if settings.secret_key is not None:
        return SecretKey.from_text(settings.secret_key.get_secret_value())
    if settings.secret_key_file is not None:
        try:
            return SecretKey.from_text(settings.secret_key_file.read_text())
        except OSError as error:
            raise VaultError(
                f"The secret key file {settings.secret_key_file} cannot be read."
            ) from error
    return SecretKey.from_text(_generated_key(settings.data_dir))
