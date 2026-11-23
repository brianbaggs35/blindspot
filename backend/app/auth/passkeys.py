"""Passkeys (WebAuthn): the rules, apart from the web layer. The protocol itself is done by the
`webauthn` library (py_webauthn); this module decides what to ask it for and what to keep.

Passkeys here always require user verification (a PIN or a biometric on the device), and are
discoverable, so the sign-in page needs no username.
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.config import Settings, passkey_origin, passkey_rp_id
from app.db.models import Passkey, User, WebAuthnChallenge

MAX_PER_ACCOUNT = 20
REGISTER = "register"
AUTHENTICATE = "authenticate"


class PasskeyError(Exception):
    """The browser's answer was refused. The message is safe to log, not to show."""

    def __init__(self, reason: str, *, cloned: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.cloned = cloned


async def _issue(
    session: AsyncSession,
    settings: Settings,
    *,
    now: datetime,
    purpose: str,
    challenge: bytes,
    user_id: uuid.UUID | None,
) -> uuid.UUID:
    """Remember a challenge until it is used or expires."""
    await session.execute(delete(WebAuthnChallenge).where(WebAuthnChallenge.expires_at < now))
    row = WebAuthnChallenge(
        challenge=challenge,
        purpose=purpose,
        user_id=user_id,
        expires_at=now + timedelta(minutes=settings.passkey_challenge_minutes),
    )
    session.add(row)
    await session.flush()
    return row.id


async def take_challenge(
    session: AsyncSession,
    challenge_id: uuid.UUID,
    purpose: str,
    user_id: uuid.UUID | None,
    now: datetime,
) -> bytes:
    """Use up a challenge: it is deleted as it is read, so it cannot be used twice, and it only
    works for the purpose (and the person) it was made for."""
    statement = (
        delete(WebAuthnChallenge)
        .where(
            WebAuthnChallenge.id == challenge_id,
            WebAuthnChallenge.purpose == purpose,
            WebAuthnChallenge.expires_at >= now,
        )
        .returning(WebAuthnChallenge.challenge, WebAuthnChallenge.user_id)
    )
    row = (await session.execute(statement)).first()
    if row is None or row.user_id != user_id:
        raise PasskeyError("The challenge is unknown, used or expired.")
    return bytes(row.challenge)


async def count_passkeys(session: AsyncSession, user_id: uuid.UUID) -> int:
    """How many passkeys an account has."""
    found = await session.scalar(
        select(func.count()).select_from(Passkey).where(Passkey.user_id == user_id)
    )
    return found or 0


async def registration_options(
    session: AsyncSession, settings: Settings, user: User, now: datetime
) -> tuple[uuid.UUID, dict[str, Any]]:
    """What the browser needs to make a passkey for this person."""
    existing = await session.scalars(select(Passkey).where(Passkey.user_id == user.id))
    options = generate_registration_options(
        rp_id=passkey_rp_id(settings),
        rp_name="Blindspot",
        user_id=user.id.bytes,
        user_name=user.username,
        user_display_name=user.display_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=one.credential_id) for one in existing
        ],
    )
    challenge_id = await _issue(
        session, settings, now=now, purpose=REGISTER, challenge=options.challenge, user_id=user.id
    )
    return challenge_id, json.loads(options_to_json(options))


async def register(
    session: AsyncSession,
    settings: Settings,
    user: User,
    *,
    challenge_id: uuid.UUID,
    credential: dict[str, Any],
    name: str,
    now: datetime,
) -> Passkey:
    """Check the browser's new credential and keep it."""
    challenge = await take_challenge(session, challenge_id, REGISTER, user.id, now)
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=passkey_rp_id(settings),
            expected_origin=passkey_origin(settings),
            require_user_verification=True,
        )
    except InvalidRegistrationResponse as error:
        raise PasskeyError(str(error)) from None
    response = cast("dict[str, Any]", credential.get("response") or {})
    transports = cast("list[Any]", response.get("transports") or [])
    passkey = Passkey(
        user_id=user.id,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        transports=[str(one) for one in transports][:8],
        name=name,
        backup_eligible=verified.credential_device_type == "multi_device",
        backed_up=verified.credential_backed_up,
    )
    session.add(passkey)
    await session.flush()
    return passkey


async def authentication_options(
    session: AsyncSession, settings: Settings, now: datetime
) -> tuple[uuid.UUID, dict[str, Any]]:
    """What the browser needs to sign in with a passkey (any passkey: no username is asked)."""
    options = generate_authentication_options(
        rp_id=passkey_rp_id(settings),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    challenge_id = await _issue(
        session, settings, now=now, purpose=AUTHENTICATE, challenge=options.challenge, user_id=None
    )
    return challenge_id, json.loads(options_to_json(options))


async def authenticate(
    session: AsyncSession,
    settings: Settings,
    *,
    challenge_id: uuid.UUID,
    credential: dict[str, Any],
    now: datetime,
) -> tuple[User, Passkey]:
    """Check a sign-in with a passkey; returns the account and the passkey used."""
    challenge = await take_challenge(session, challenge_id, AUTHENTICATE, None, now)
    raw_id = credential.get("rawId")
    try:
        credential_id = base64url_to_bytes(raw_id) if isinstance(raw_id, str) else b""
    except ValueError:
        credential_id = b""
    passkey = await session.scalar(select(Passkey).where(Passkey.credential_id == credential_id))
    user = await session.get(User, passkey.user_id) if passkey else None
    if passkey is None or user is None or not user.is_active:
        raise PasskeyError("The passkey is not known, or its account is switched off.")
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=passkey_rp_id(settings),
            expected_origin=passkey_origin(settings),
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except InvalidAuthenticationResponse as error:
        # A counter that did not go up means the passkey may have been copied. Passkeys that
        # sync between devices report 0 every time, and the library lets those through.
        raise PasskeyError(str(error), cloned="sign count" in str(error)) from None
    passkey.sign_count = verified.new_sign_count
    passkey.backed_up = verified.credential_backed_up
    passkey.last_used_at = now
    user.last_sign_in_at = now
    return user, passkey
