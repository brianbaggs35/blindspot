"""Replace the app secret key: seal everything again with the new one.

Rotation reads every sealed column in the schema and, for each value that the current key did not
seal, opens it (with the previous key) and seals it with the current one, all in one transaction.
It is safe to run again: values already under the current key are left alone.
"""

from typing import Any

from sqlalchemy import Column, MetaData, Table, Text, column, select, table, type_coerce, update
from sqlalchemy.engine import Connection

from app.db.migrate import take_migration_lock
from app.vault.seal import Purpose, Vault
from app.vault.types import SealedJSON, SealedString


def sealed_columns(metadata: MetaData) -> list[tuple[Table, Column[Any], Purpose]]:
    """Every column that holds sealed values, and what each is sealed for."""
    return [
        (found, one, one.type.purpose)
        for found in metadata.sorted_tables
        for one in found.columns
        if isinstance(one.type, SealedString | SealedJSON)
    ]


def rotate(connection: Connection, metadata: MetaData, vault: Vault) -> int:
    """Seal every value with the vault's current key. Returns how many values changed."""
    take_migration_lock(connection)  # no migration, and no second rotation, at the same time
    changed = 0
    for found, sealed, purpose in sealed_columns(metadata):
        keys = list(found.primary_key.columns)
        raw = type_coerce(sealed, Text)  # the envelope as stored, not opened
        plain = table(
            found.name, *(column(one.name, one.type) for one in keys), column(sealed.name, Text)
        )
        rows = connection.execute(select(*keys, raw).where(sealed.is_not(None)))
        for *key_values, envelope in rows.all():
            if not vault.needs_rotation(envelope):
                continue
            new = vault.seal(purpose, vault.open(purpose, envelope))
            where = [
                plain.c[one.name] == value for one, value in zip(keys, key_values, strict=True)
            ]
            connection.execute(update(plain).where(*where).values({sealed.name: new}))
            changed += 1
    return changed
