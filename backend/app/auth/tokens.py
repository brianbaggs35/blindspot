"""Session tokens: 256 random bits in the cookie, and only their SHA-256 in the database."""

import hashlib
import secrets


def new_token() -> str:
    """A token for the cookie."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """What is stored for a token."""
    return hashlib.sha256(token.encode()).hexdigest()
