"""Run the migrations: `python -m app.db.migrate`.

Only one process migrates at a time. The runner takes a PostgreSQL advisory lock for the length
of its transaction, so a second one waits and then finds nothing left to do.
"""

import hashlib
import sys
import time
from pathlib import Path

import structlog
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError

from app.config import get_settings
from app.db.backup import back_up
from app.log import configure_logging

log = structlog.get_logger()

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


def revisions(url: str, wait: float = 60.0) -> tuple[str | None, str]:
    """The revision the database is at (None when it has never been migrated) and the newest.
    Waits for the database to accept connections, because at start-up it may still be coming up."""
    head = ScriptDirectory.from_config(alembic_config(url)).get_current_head()
    engine = create_engine(url)
    deadline = time.monotonic() + wait
    try:
        while True:
            try:
                with engine.connect() as connection:
                    current = MigrationContext.configure(connection).get_current_revision()
                return current, str(head)
            except OperationalError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.5)
    finally:
        engine.dispose()


def main() -> int:
    """Upgrade the configured database, after copying it first when there is something to change.
    A new database has nothing worth keeping, and one already at the newest revision is left be."""
    settings = get_settings()
    configure_logging(settings.log_level)
    current, head = revisions(settings.database_url)
    if current is not None and current != head:
        copy = back_up(settings.database_url, settings.data_dir / "backups", current)
        log.info("database_backed_up", path=str(copy), revision=current)
    log.info("database_migrating", current=current, head=head)
    upgrade()
    return 0


if __name__ == "__main__":
    sys.exit(main())
