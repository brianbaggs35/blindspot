"""The usage ledger and the monthly budget, on a real database."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import another_browser, set_up

from app.ai.kinds import ProviderKind
from app.ai.ledger import (
    check_budget,
    month_start,
    overrides_of,
    record_usage,
    spend_this_month,
)
from app.ai.pricing import Usage
from app.db.base import Base, utc_now
from app.db.migrate import upgrade
from app.db.models import AiModel, AiProvider, UsageLedger
from app.errors import BudgetExceeded
from app.vault import SecretKey, Vault, get_vault, set_vault
from app.vault.rotate import rotate

KEY = "sk-ledger-0123456789abcdefghijklmnopqr"


@pytest.fixture
def migrated(database_url: str) -> str:
    upgrade(database_url)
    return database_url


@pytest.fixture
async def session(migrated: str) -> AsyncIterator[AsyncSession]:
    set_vault(Vault(SecretKey.from_text("ledger-test-key-0123456789abcdef0123456789")))
    engine = create_async_engine(migrated)
    async with async_sessionmaker(engine, expire_on_commit=False)() as opened:
        yield opened
    await engine.dispose()


async def provider(
    session: AsyncSession,
    kind: ProviderKind = ProviderKind.OPENAI,
    name: str = "P",
    **fields: object,
) -> AiProvider:
    made = AiProvider(kind=kind.value, name=name, base_url="https://x.example.com", **fields)
    session.add(made)
    await session.flush()
    return made


def test_the_month_begins_on_the_first_in_utc() -> None:
    assert month_start(datetime(2026, 11, 23, 17, 5, 9, 123, tzinfo=UTC)) == datetime(
        2026, 11, 1, tzinfo=UTC
    )
    late = datetime(2026, 12, 1, 1, 0, tzinfo=UTC).astimezone(timezone_of(-5))
    assert month_start(late) == datetime(2026, 12, 1, tzinfo=UTC)


def timezone_of(hours: int):
    from datetime import timezone  # noqa: PLC0415

    return timezone(timedelta(hours=hours))


async def test_a_call_is_recorded_with_its_cost(session: AsyncSession) -> None:
    made = await provider(session, ProviderKind.ANTHROPIC, "A")
    run = uuid.uuid4()
    entry = record_usage(
        session,
        made,
        "claude-opus-5-5",
        Usage(input_tokens=1_000_000, output_tokens=100_000, cache_read_tokens=500_000),
        latency_ms=1234,
        agent="commander",
        run_id=run,
    )
    await session.commit()
    assert entry.cost_usd == Decimal("6.1")  # 4.00 + 2.00 + 0.10
    assert (entry.provider_name, entry.agent, entry.run_id, entry.latency_ms) == (
        "A",
        "commander",
        run,
        1234,
    )
    assert (entry.input_tokens, entry.output_tokens, entry.cache_read_tokens) == (
        1_000_000,
        100_000,
        500_000,
    )


async def test_a_price_set_on_the_model_wins_over_the_catalog(session: AsyncSession) -> None:
    made = await provider(session)
    model = AiModel(
        provider_id=made.id, model_id="gpt-6-luna", display_name="Luna", price_input=Decimal(10)
    )
    session.add(model)
    await session.flush()
    assert overrides_of(None) is None
    assert overrides_of(model) is not None
    entry = record_usage(
        session, made, "gpt-6-luna", Usage(input_tokens=1_000_000), latency_ms=1, model=model
    )
    assert entry.cost_usd == Decimal(10)


async def test_unknown_and_free_models(session: AsyncSession) -> None:
    hosted = await provider(session, name="H")
    unknown = record_usage(
        session, hosted, "nobody-knows", Usage(input_tokens=5, output_tokens=5), latency_ms=1
    )
    local = await provider(session, ProviderKind.OLLAMA_LOCAL, "L")
    free = record_usage(
        session, local, "llama3.3", Usage(input_tokens=5, output_tokens=5), latency_ms=1
    )
    assert unknown.cost_usd is None
    assert free.cost_usd == 0


async def test_spend_counts_this_month_only_and_skips_unknown_prices(
    session: AsyncSession,
) -> None:
    now = utc_now()
    one = await provider(session, name="One")
    two = await provider(session, name="Two")
    spend = Usage(input_tokens=1_000_000)  # gpt-6-luna input price is in the catalog
    first = record_usage(session, one, "gpt-6-luna", spend, latency_ms=1)
    record_usage(session, one, "gpt-6-luna", spend, latency_ms=1)
    record_usage(session, two, "gpt-6-luna", spend, latency_ms=1)
    record_usage(session, one, "nobody-knows", spend, latency_ms=1)
    old = record_usage(session, one, "gpt-6-luna", spend, latency_ms=1)
    await session.flush()
    await session.execute(
        text("UPDATE usage_ledger SET created_at = :then WHERE id = :id"),
        {"then": month_start(now) - timedelta(days=1), "id": old.id},
    )
    await session.commit()
    each = await spend_this_month(session, now)
    assert first.cost_usd is not None
    assert each[one.id] == first.cost_usd * 2
    assert each[two.id] == first.cost_usd
    only = await spend_this_month(session, now, two.id)
    assert list(only) == [two.id]


async def test_a_deleted_providers_calls_stay_in_the_ledger_but_not_in_spend(
    session: AsyncSession,
) -> None:
    made = await provider(session)
    record_usage(session, made, "gpt-6-luna", Usage(input_tokens=1_000_000), latency_ms=1)
    await session.commit()
    await session.delete(made)
    await session.commit()
    assert await spend_this_month(session, utc_now()) == {}
    kept = (await session.execute(select(UsageLedger))).scalars().all()
    assert [(one.provider_id, one.provider_name) for one in kept] == [(None, "P")]


async def test_the_budget_stops_calls_only_when_it_is_used_up_and_set_to_stop(
    session: AsyncSession,
) -> None:
    now = utc_now()
    spend = Usage(input_tokens=1_000_000)
    unlimited = await provider(session, name="None")
    soft = await provider(session, name="Soft", monthly_budget_usd=Decimal("0.01"))
    no_budget = await provider(session, name="NoBudget", hard_stop=True)
    hard = await provider(session, name="Hard", monthly_budget_usd=Decimal(1000), hard_stop=True)
    for one in (unlimited, soft, no_budget, hard):
        record_usage(session, one, "gpt-6-luna", spend, latency_ms=1)
    await session.commit()
    for one in (unlimited, soft, no_budget, hard):
        await check_budget(session, one, now)  # none of these must refuse
    hard.monthly_budget_usd = Decimal("0.01")
    with pytest.raises(BudgetExceeded) as stopped:
        await check_budget(session, hard, now)
    assert stopped.value.status == 402
    assert stopped.value.code == "budget_exceeded"
    assert "Hard" in stopped.value.title


async def test_a_new_month_starts_with_a_clean_budget(session: AsyncSession) -> None:
    made = await provider(session, monthly_budget_usd=Decimal("0.01"), hard_stop=True)
    record_usage(session, made, "gpt-6-luna", Usage(input_tokens=1_000_000), latency_ms=1)
    await session.commit()
    next_month = month_start(utc_now() + timedelta(days=40))
    await check_budget(session, made, next_month)


def test_rotating_the_key_reseals_provider_keys(api: TestClient, database_url: str) -> None:
    set_up(api)
    from app.ai.routes import get_resolver  # noqa: PLC0415

    async def resolve(host: str, port: int) -> list[str]:
        assert host
        assert port
        return ["93.184.216.34"]

    api.app.dependency_overrides[get_resolver] = lambda: resolve  # type: ignore[attr-defined]
    made = api.post("/api/providers", json={"kind": "openai", "name": "R", "api_key": KEY})
    assert made.status_code == 201
    old = get_vault()
    new = Vault(SecretKey.from_text("a-brand-new-key-0123456789abcdef0123456789"), [old.current])
    engine = create_engine(database_url)
    with engine.begin() as connection:
        assert rotate(connection, Base.metadata, new) >= 2  # the account's hash and this key
        stored = connection.execute(text("SELECT api_key FROM ai_provider")).scalar_one()
    engine.dispose()
    assert KEY not in stored
    set_vault(new)
    # The key still opens: the stored value round-trips through the new vault.
    assert another_browser(api, "admin").get("/api/providers").json()[0]["key_last4"] == KEY[-4:]
