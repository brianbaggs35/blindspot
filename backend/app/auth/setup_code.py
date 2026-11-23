"""The one-time code that guards first-run setup. There are no default credentials: until the
first administrator exists, the app prints a code in its log, and whoever can read the log (the
person who started the container) can set it up."""

import hmac
import secrets

import structlog

from app.auth.service import count_users
from app.db.session import Database

log = structlog.get_logger()
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0, 1, I, O


def new_code() -> str:
    """A code like `BLND-7K2M-QX9P-HT4C`: 60 random bits."""
    groups = ["".join(secrets.choice(_ALPHABET) for _ in range(4)) for _ in range(3)]
    return "BLND-" + "-".join(groups)


class SetupGate:
    """Holds the code while setup is open, and forgets it once setup is done."""

    def __init__(self) -> None:
        self.code: str | None = None

    def open(self) -> str:
        """Make a code (if there is none) and print it."""
        if self.code is None:
            self.code = new_code()
            log.warning(
                "setup_required",
                message="No administrator exists yet. Open the app and enter this setup code "
                f"to create one: {self.code}",
            )
        return self.code

    def close(self) -> None:
        """Setup is done; the code is no use any more."""
        self.code = None

    def accepts(self, given: str) -> bool:
        """Whether this is the current code (compared in constant time)."""
        return self.code is not None and hmac.compare_digest(
            self.code.encode(), given.strip().upper().encode()
        )

    async def prepare(self, database: Database) -> None:
        """At start-up: print the code if no one can sign in yet. A database that is not there
        yet is not an error; the code is made when it is first needed."""
        try:
            async with database.sessions() as session:
                if await count_users(session) == 0:
                    self.open()
        except Exception:  # the database is still coming up
            log.warning("setup_check_deferred")
