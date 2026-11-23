"""Password hashing: the password is mixed with a secret pepper (HMAC-SHA256), then hashed with
Argon2id using the RFC 9106 low-memory profile. The pepper lives in the vault, so a copy of the
database alone cannot be used to guess passwords offline.

Hashing takes a tenth of a second and some memory on purpose, so it runs in a thread: the event
loop keeps serving other requests meanwhile.
"""

import asyncio
import base64
import hashlib
import hmac
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.profiles import RFC_9106_LOW_MEMORY

MIN_LENGTH = 12
MAX_LENGTH = 256
# Not a list of every weak password: just the ones that pass a length rule and are tried first.
_COMMON = frozenset(
    {
        "password1234",
        "passwordpassword",
        "123456789012",
        "1234567890123",
        "qwertyuiop12",
        "qwertyuiopas",
        "letmeinletmein",
        "administrator",
        "changemechangeme",
        "welcome12345",
        "iloveyou1234",
    }
)

_hasher = PasswordHasher.from_parameters(RFC_9106_LOW_MEMORY)


def mix(password: str, pepper: bytes) -> str:
    """The password with the pepper mixed in: what Argon2id is given."""
    digest = hmac.digest(pepper, password.encode(), hashlib.sha256)
    return base64.b64encode(digest).decode()


def password_problem(password: str, username: str) -> str | None:
    """Why a password is not acceptable, or None when it is."""
    if len(password) < MIN_LENGTH:
        return f"Use at least {MIN_LENGTH} characters."
    if len(password) > MAX_LENGTH:
        return f"Use at most {MAX_LENGTH} characters."
    if len(set(password)) < 4:
        return "Use a password with more different characters."
    folded = password.casefold()
    if folded in _COMMON:
        return "That password is far too common."
    if len(username) >= 3 and username.casefold() in folded:
        return "The password must not contain the username."
    return None


def _hash(password: str, pepper: bytes) -> str:
    return _hasher.hash(mix(password, pepper))


def _verify(stored: str, password: str, pepper: bytes) -> tuple[bool, bool]:
    try:
        _hasher.verify(stored, mix(password, pepper))
    except VerificationError, InvalidHashError:
        return False, False
    return True, _hasher.check_needs_rehash(stored)


@lru_cache
def _decoy() -> str:
    """A hash to check when the account does not exist, so that takes as long as when it does."""
    return _hasher.hash("decoy")


async def hash_password(password: str, pepper: bytes) -> str:
    """The Argon2id hash to store."""
    return await asyncio.to_thread(_hash, password, pepper)


async def verify_password(stored: str, password: str, pepper: bytes) -> tuple[bool, bool]:
    """Whether the password is right, and whether the stored hash should be made again with the
    current settings."""
    return await asyncio.to_thread(_verify, stored, password, pepper)


async def spend_the_same_time(password: str, pepper: bytes) -> None:
    """Do the work of a check for an account that does not exist."""
    await asyncio.to_thread(_verify, _decoy(), password, pepper)
