"""Open the vault from the settings."""

from app.config import Settings
from app.vault.current import set_vault
from app.vault.keys import SecretKey, load_key
from app.vault.seal import Vault


def build_vault(settings: Settings) -> Vault:
    """The vault for the configured key, which also opens what a previous key sealed."""
    previous = settings.previous_secret_key
    older = [SecretKey.from_text(previous.get_secret_value())] if previous is not None else []
    return Vault(load_key(settings), older)


def open_vault(settings: Settings) -> Vault:
    """Build the vault and make it the one the sealed column types use."""
    vault = build_vault(settings)
    set_vault(vault)
    return vault
