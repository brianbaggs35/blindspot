"""Commands for the key: `python -m app.vault generate` and `python -m app.vault rotate`.

`generate` prints a new key. `rotate` seals every value again with the configured key (see
docs/how-to/secrets.md for the steps around it).
"""

import sys

from sqlalchemy import create_engine

from app.config import get_settings
from app.db import models  # registers the tables on Base.metadata
from app.vault.keys import VaultError, generate_key
from app.vault.rotate import rotate
from app.vault.setup import build_vault


def main(argv: list[str]) -> int:
    """Run a command; returns the exit status."""
    if argv == ["generate"]:
        print(generate_key())  # noqa: T201 - the output is the point
        return 0
    if argv == ["rotate"]:
        settings = get_settings()
        try:
            vault = build_vault(settings)
        except VaultError as error:
            print(f"error: {error}", file=sys.stderr)  # noqa: T201
            return 1
        engine = create_engine(settings.database_url)
        try:
            with engine.begin() as connection:
                changed = rotate(connection, models.Base.metadata, vault)
        except VaultError as error:
            print(f"error: {error}", file=sys.stderr)  # noqa: T201
            return 1
        finally:
            engine.dispose()
        print(f"{changed} values sealed with the current key.")  # noqa: T201
        return 0
    print("usage: python -m app.vault generate | rotate", file=sys.stderr)  # noqa: T201
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
