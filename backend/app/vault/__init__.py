"""The secrets vault: every credential is sealed before it reaches the database."""

from app.vault.current import get_vault, set_vault
from app.vault.keys import SecretKey, VaultError, generate_key
from app.vault.seal import Purpose, Vault
from app.vault.setup import build_vault, open_vault
from app.vault.types import SealedJSON, SealedString

__all__ = [
    "Purpose",
    "SealedJSON",
    "SealedString",
    "SecretKey",
    "Vault",
    "VaultError",
    "build_vault",
    "generate_key",
    "get_vault",
    "open_vault",
    "set_vault",
]
