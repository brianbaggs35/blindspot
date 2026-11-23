"""Column types that seal what is written and open what is read.

A model declares `api_key: Mapped[str] = mapped_column(SealedString(Purpose.PROVIDERS))` and can
no longer write the value to the database in the clear. A sealed column cannot be searched or
sorted by its value; keep a separate, non-secret field (a name, the last four characters) for
that.
"""

import json
from typing import Any

from sqlalchemy import Dialect, Text
from sqlalchemy.types import TypeDecorator

from app.vault.current import get_vault
from app.vault.seal import Purpose


class SealedString(TypeDecorator[str]):
    """A text value stored as a sealed envelope."""

    impl = Text
    cache_ok = True

    def __init__(self, purpose: Purpose) -> None:
        super().__init__()
        self.purpose = purpose

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        return None if value is None else get_vault().seal(self.purpose, value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        return None if value is None else get_vault().open(self.purpose, value)


class SealedJSON(TypeDecorator[Any]):
    """Any JSON value, stored as a sealed envelope."""

    impl = Text
    cache_ok = True

    def __init__(self, purpose: Purpose) -> None:
        super().__init__()
        self.purpose = purpose

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return get_vault().seal(self.purpose, json.dumps(value, separators=(",", ":")))

    def process_result_value(self, value: str | None, dialect: Dialect) -> Any:
        return None if value is None else json.loads(get_vault().open(self.purpose, value))
