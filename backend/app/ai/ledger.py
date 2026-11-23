"""The usage ledger and the budget: every call is recorded, and a provider can be set to stop at
its monthly budget."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.kinds import ProviderKind
from app.ai.pricing import Price, Usage, cost_usd, price_for
from app.db.models import AiModel, AiProvider, UsageLedger
from app.errors import BudgetExceeded


def month_start(now: datetime) -> datetime:
    """The first moment of the month, in UTC, that `now` falls in."""
    now = now.astimezone(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def overrides_of(model: AiModel | None) -> Price | None:
    """The prices an administrator set on a model, if any."""
    if model is None:
        return None
    return Price(
        input=model.price_input,
        output=model.price_output,
        cache_read=model.price_cache_read,
        cache_write=model.price_cache_write,
        cache_write_long=model.price_cache_write_long,
    )


async def record_usage(  # noqa: PLR0913  # a call has this many facts; keywords keep them clear
    session: AsyncSession,
    provider: AiProvider,
    model_id: str,
    usage: Usage,
    *,
    latency_ms: int,
    model: AiModel | None = None,
    agent: str | None = None,
    run_id: uuid.UUID | None = None,
) -> UsageLedger:
    """Add one call to the ledger, with its cost when the price is known."""
    price = price_for(
        ProviderKind(provider.kind), model_id, overrides_of(model), usage.prompt_tokens
    )
    entry = UsageLedger(
        provider_id=provider.id,
        provider_name=provider.name,
        model_id=model_id,
        agent=agent,
        run_id=run_id,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_write_tokens=usage.cache_write_tokens,
        cache_write_long_tokens=usage.cache_write_long_tokens,
        thinking_tokens=usage.thinking_tokens,
        latency_ms=latency_ms,
        cost_usd=cost_usd(price, usage),
    )
    session.add(entry)
    return entry


async def spend_this_month(
    session: AsyncSession, now: datetime, provider_id: uuid.UUID | None = None
) -> dict[uuid.UUID, Decimal]:
    """What each provider (or the one asked for) has cost since the month began. Calls with an
    unknown price add nothing here; their tokens are in the ledger."""
    query = (
        select(UsageLedger.provider_id, func.coalesce(func.sum(UsageLedger.cost_usd), 0))
        .where(UsageLedger.created_at >= month_start(now), UsageLedger.provider_id.is_not(None))
        .group_by(UsageLedger.provider_id)
    )
    if provider_id is not None:
        query = query.where(UsageLedger.provider_id == provider_id)
    rows = await session.execute(query)
    return {key: Decimal(total or 0) for key, total in rows.all() if key is not None}


async def check_budget(session: AsyncSession, provider: AiProvider, now: datetime) -> None:
    """Raise BudgetExceeded when the provider has a budget, is set to stop at it, and has spent
    it. Called before every call."""
    if not provider.hard_stop or provider.monthly_budget_usd is None:
        return
    spent = (await spend_this_month(session, now, provider.id)).get(provider.id, Decimal(0))
    if spent >= provider.monthly_budget_usd:
        raise BudgetExceeded(provider.name)
