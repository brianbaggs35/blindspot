"""What the AI provider routes accept and return."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints

from app.ai.kinds import ProviderKind
from app.ai.pricing import Price
from app.ai.roles import AgentRole

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
ModelId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
PriceValue = Annotated[Decimal, Field(ge=0, le=100000, max_digits=14, decimal_places=6)]
Budget = Annotated[Decimal, Field(ge=0, le=100000000, max_digits=14, decimal_places=4)]
PriceSource = Literal["override", "catalog", "free", "unknown"]
Capability = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]


class Strict(BaseModel):
    """A request body with no extra fields."""

    model_config = ConfigDict(extra="forbid")


class PriceFields(Strict):
    """Prices set by an administrator, in USD per million tokens. Leave a field out (or null) to
    use the catalog's."""

    price_input: PriceValue | None = None
    price_output: PriceValue | None = None
    price_cache_read: PriceValue | None = None
    price_cache_write: PriceValue | None = None
    price_cache_write_long: PriceValue | None = None


class ProviderIn(Strict):
    """A new provider. The address is the kind's usual one when left out."""

    kind: ProviderKind
    name: Name
    base_url: Annotated[str, Field(max_length=300)] = ""
    api_key: SecretStr | None = Field(default=None, max_length=512)
    enabled: bool = True
    monthly_budget_usd: Budget | None = None
    hard_stop: bool = False


class ProviderUpdate(Strict):
    """Changes to a provider; leave out what stays. Setting `api_key` replaces the key;
    `remove_key` deletes it. A null budget removes the budget."""

    name: Name | None = None
    base_url: Annotated[str, Field(min_length=1, max_length=300)] | None = None
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=512)
    remove_key: bool = False
    enabled: bool | None = None
    monthly_budget_usd: Budget | None = None
    hard_stop: bool | None = None


class ProviderOut(BaseModel):
    """A provider, with the key hidden: only whether there is one, and its last four characters."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ProviderKind
    name: str
    base_url: str
    enabled: bool
    has_key: bool
    key_last4: str | None
    monthly_budget_usd: Decimal | None
    hard_stop: bool
    spent_this_month_usd: Decimal
    model_count: int
    created_at: datetime


class ModelIn(PriceFields):
    """A model added by hand. What is left out comes from the catalog when it knows the model."""

    model_id: ModelId
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    context_tokens: Annotated[int, Field(ge=1, le=100_000_000_000)] | None = None
    max_output_tokens: Annotated[int, Field(ge=1, le=100_000_000_000)] | None = None
    capabilities: list[Capability] | None = Field(default=None, max_length=16)
    enabled: bool = True


class ModelUpdate(PriceFields):
    """Changes to a model. For the prices, null means "use the catalog's"; leave a field out to
    keep what is set."""

    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = (
        None
    )
    enabled: bool | None = None
    capabilities: list[Capability] | None = Field(default=None, max_length=16)


class PriceOut(BaseModel):
    """A price in USD per million tokens; null means not known."""

    input: Decimal | None
    output: Decimal | None
    cache_read: Decimal | None
    cache_write: Decimal | None
    cache_write_long: Decimal | None

    @classmethod
    def of(cls, price: Price) -> PriceOut:
        """From a price."""
        return cls(
            input=price.input,
            output=price.output,
            cache_read=price.cache_read,
            cache_write=price.cache_write,
            cache_write_long=price.cache_write_long,
        )


class ModelOut(BaseModel):
    """A model, with the price that will be used and where it comes from."""

    id: uuid.UUID
    provider_id: uuid.UUID
    model_id: str
    display_name: str
    context_tokens: int | None
    max_output_tokens: int | None
    capabilities: list[str]
    supports_tools: bool
    enabled: bool
    price: PriceOut
    price_source: PriceSource
    overrides: PriceOut


class KindOut(BaseModel):
    """A kind of provider, for the add form."""

    kind: ProviderKind
    label: str
    default_base_url: str
    needs_key: bool


class CatalogModelOut(BaseModel):
    """A model in the price catalog."""

    kind: ProviderKind
    id: str
    name: str
    context: int | None
    max_output: int | None
    capabilities: list[str]
    price: PriceOut
    long_prompt_above: int | None
    long_prompt_price: PriceOut | None


class CatalogOut(BaseModel):
    """The price catalog and when its prices were last checked."""

    verified_on: date
    source: str
    models: list[CatalogModelOut]


class RoleDefaultIn(Strict):
    """The model to use for a role."""

    model_ref: uuid.UUID


class RoleDefaultOut(BaseModel):
    """A role and its default model, if one is chosen."""

    role: AgentRole
    label: str
    model_ref: uuid.UUID | None
    provider_name: str | None
    model_id: str | None


class ConnectionOut(BaseModel):
    """The result of trying a provider. A failure is a result, not an error, so the page can show
    it next to the button."""

    ok: bool
    latency_ms: int
    model_count: int | None
    failure: str | None
    detail: str


class DiscoveredOut(BaseModel):
    """A model the provider offers, with what the app would use if it were added."""

    model_id: str
    display_name: str
    context_tokens: int | None
    max_output_tokens: int | None
    capabilities: list[str]
    added: bool
    price_source: PriceSource
