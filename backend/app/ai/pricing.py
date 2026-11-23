"""What a call costs. Prices come from the catalog file (with its verified-on date), and an
administrator can override them per model. A model with no price has an unknown cost: the tokens
are still counted, and no figure is guessed."""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

from app.ai.kinds import ProviderKind

CATALOG_FILE = Path(__file__).with_name("catalog.json")
PER = Decimal(1_000_000)


@dataclass(frozen=True)
class Price:
    """USD per million tokens. None means the price is not known."""

    input: Decimal | None = None
    output: Decimal | None = None
    cache_read: Decimal | None = None
    cache_write: Decimal | None = None  # the default cache lifetime (5 minutes, 30 minutes)
    cache_write_long: Decimal | None = None  # the long one (1 hour, 12 hours)


@dataclass(frozen=True)
class Usage:
    """The tokens one call used, in the same terms for every provider.

    `input_tokens` is the prompt without what came from or went into the cache; providers that
    count cached tokens inside their input figure are adjusted by their adapter. Thinking tokens
    are part of `output_tokens` already (every provider bills them as output), so they are kept
    for display and are not charged again.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cache_write_long_tokens: int = 0
    thinking_tokens: int = 0

    @property
    def prompt_tokens(self) -> int:
        """The whole prompt, cached or not. Long-prompt prices depend on it."""
        return (
            self.input_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
            + self.cache_write_long_tokens
        )


@dataclass(frozen=True)
class LongPrompt:
    """Another price for prompts above a size."""

    above: int
    price: Price


@dataclass(frozen=True)
class CatalogModel:
    """A model the catalog knows."""

    kind: ProviderKind
    id: str
    name: str
    context: int | None
    max_output: int | None
    capabilities: tuple[str, ...]
    price: Price
    long_prompt: LongPrompt | None


@dataclass(frozen=True)
class Catalog:
    """The catalog file."""

    verified_on: date
    source: str
    models: tuple[CatalogModel, ...]

    def find(self, kind: ProviderKind, model_id: str) -> CatalogModel | None:
        """The catalog's entry for a model of this kind, if it has one."""
        return next((m for m in self.models if m.kind == kind and m.id == model_id), None)


def _price(raw: dict[str, Any]) -> Price:
    def one(key: str) -> Decimal | None:
        value = raw.get(key)
        return None if value is None else Decimal(value)

    return Price(
        input=one("input"),
        output=one("output"),
        cache_read=one("cache_read"),
        cache_write=one("cache_write"),
        cache_write_long=one("cache_write_long"),
    )


def _model(raw: dict[str, Any]) -> CatalogModel:
    long_raw = raw.get("long_prompt")
    return CatalogModel(
        kind=ProviderKind(raw["kind"]),
        id=raw["id"],
        name=raw["name"],
        context=raw["context"],
        max_output=raw["max_output"],
        capabilities=tuple(raw["capabilities"]),
        price=_price(raw["price"]),
        long_prompt=None
        if long_raw is None
        else LongPrompt(above=long_raw["above"], price=_price(long_raw["price"])),
    )


@cache
def load_catalog() -> Catalog:
    """The catalog file, read once."""
    raw = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    return Catalog(
        verified_on=date.fromisoformat(raw["verified_on"]),
        source=raw["source"],
        models=tuple(_model(one) for one in raw["models"]),
    )


FREE = Price(
    input=Decimal(0),
    output=Decimal(0),
    cache_read=Decimal(0),
    cache_write=Decimal(0),
    cache_write_long=Decimal(0),
)


def _merge(base: Price, overrides: Price) -> Price:
    return Price(
        input=base.input if overrides.input is None else overrides.input,
        output=base.output if overrides.output is None else overrides.output,
        cache_read=base.cache_read if overrides.cache_read is None else overrides.cache_read,
        cache_write=base.cache_write if overrides.cache_write is None else overrides.cache_write,
        cache_write_long=(
            base.cache_write_long
            if overrides.cache_write_long is None
            else overrides.cache_write_long
        ),
    )


def price_for(
    kind: ProviderKind, model_id: str, overrides: Price | None = None, prompt_tokens: int = 0
) -> Price:
    """The price to use for a call.

    A model on this machine is free. Any price an administrator set replaces the catalog's price
    for that kind of token and is flat (the catalog's long-prompt tier no longer applies).
    Otherwise it is the catalog's price, in the long-prompt tier when the prompt is that large.
    With neither, nothing is known.
    """
    if kind is ProviderKind.OLLAMA_LOCAL:
        base = FREE
        tier = None
    else:
        found = load_catalog().find(kind, model_id)
        base = Price() if found is None else found.price
        tier = None if found is None else found.long_prompt
    if overrides is not None and overrides != Price():
        return _merge(base, overrides)
    if tier is not None and prompt_tokens > tier.above:
        return tier.price
    return base


def cost_usd(price: Price, usage: Usage) -> Decimal | None:
    """The cost of the call, or None when a kind of token that was used has no price."""
    lines = (
        (usage.input_tokens, price.input),
        (usage.output_tokens, price.output),
        (usage.cache_read_tokens, price.cache_read),
        (usage.cache_write_tokens, price.cache_write),
        (usage.cache_write_long_tokens, price.cache_write_long),
    )
    total = Decimal(0)
    for tokens, per_million in lines:
        if tokens == 0:
            continue
        if per_million is None:
            return None
        total += per_million * tokens / PER
    return total
