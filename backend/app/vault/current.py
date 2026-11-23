"""The vault the sealed column types use. The app opens it at start-up."""

from app.vault.keys import VaultError
from app.vault.seal import Vault

_vault: Vault | None = None


def set_vault(vault: Vault | None) -> None:
    """Use this vault from now on (or none)."""
    global _vault  # noqa: PLW0603
    _vault = vault


def get_vault() -> Vault:
    """The open vault. Sealed columns cannot be read or written without one."""
    if _vault is None:
        raise VaultError("The vault is not open.")
    return _vault
