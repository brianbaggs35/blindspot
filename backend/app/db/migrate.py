"""Run the migrations: `python -m app.db.migrate`.

Only one process migrates at a time. The runner takes a PostgreSQL advisory lock for the length
of its transaction, so a second one waits and then finds nothing left to do.
"""

import hashlib
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Connection

BACKEND = Path(__file__).resolve().parents[2]

# One number for the whole application; derived from a name so nobody has to pick one.
MIGRATION_LOCK_KEY = int.from_bytes(
    hashlib.sha256(b"blindspot-migrations").digest()[:8], "big", signed=True
)


def alembic_config(url: str | None = None) -> Config:
    """Alembic's settings, pointing at this project's migrations."""
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    if url is not None:
        config.attributes["url"] = url
    return config


def take_migration_lock(connection: Connection) -> None:
    """Wait for any other migration to finish, then hold the lock until this transaction ends."""
    connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK_KEY})


def upgrade(url: str | None = None, revision: str = "head") -> None:
    """Bring the database to a revision (the newest by default)."""
    command.upgrade(alembic_config(url), revision)


def main() -> int:
    """Upgrade the configured database."""
    upgrade()
    return 0


if __name__ == "__main__":
    sys.exit(main())
