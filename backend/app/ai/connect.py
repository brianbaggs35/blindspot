"""Try a provider and fetch the models it offers."""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.ai.adapters.factory import HttpClientFactory, HttpClientFactoryDep, adapter_for
from app.ai.adapters.types import Adapter, DiscoveredModel, UpstreamError
from app.ai.kinds import ProviderKind
from app.ai.netguard import Resolver
from app.ai.pricing import Price, load_catalog
from app.ai.routes import ResolverDep, checked_url, price_source, provider_by_id
from app.ai.schemas import ConnectionOut, DiscoveredOut
from app.auth import audit
from app.auth.deps import Admin
from app.db.models import AiModel, AiProvider
from app.db.session import SessionDep
from app.errors import AppError

router = APIRouter(prefix="/api", tags=["ai"])


@asynccontextmanager
async def connected(
    provider: AiProvider, resolver: Resolver, factory: HttpClientFactory
) -> AsyncGenerator[Adapter]:
    """An adapter for the provider. The address is checked again first, because a host name can
    start resolving somewhere else after it was saved."""
    await checked_url(provider.base_url, ProviderKind(provider.kind), resolver)
    client = factory()
    try:
        yield adapter_for(provider, client)
    finally:
        await client.aclose()


def milliseconds_since(started: float) -> int:
    """Whole milliseconds since a `perf_counter` reading."""
    return round((perf_counter() - started) * 1000)


@router.post("/providers/{provider_id}/test")
async def test_provider(
    provider_id: uuid.UUID,
    request: Request,
    *,
    who: Admin,
    session: SessionDep,
    resolver: ResolverDep,
    factory: HttpClientFactoryDep,
) -> ConnectionOut:
    """Check the address, the key and the network by asking the provider for its models."""
    provider = await provider_by_id(session, provider_id)
    started = perf_counter()
    try:
        async with connected(provider, resolver, factory) as adapter:
            count = len(await adapter.list_models())
        report = ConnectionOut(
            ok=True,
            latency_ms=milliseconds_since(started),
            model_count=count,
            failure=None,
            detail=f"Connected. {count} models are available.",
        )
    except UpstreamError as error:
        report = ConnectionOut(
            ok=False,
            latency_ms=milliseconds_since(started),
            model_count=None,
            failure=error.failure.value,
            detail=error.detail,
        )
    except AppError as error:  # the only one raised in there is the address check
        report = ConnectionOut(
            ok=False,
            latency_ms=milliseconds_since(started),
            model_count=None,
            failure=error.code,
            detail=error.title,
        )
    audit.record(
        session,
        request,
        "provider.test",
        actor=who.user,
        target=("provider", provider.id),
        detail={"ok": report.ok, "failure": report.failure},
    )
    return report


def offered(kind: ProviderKind, found: DiscoveredModel, added: set[str]) -> DiscoveredOut:
    """A discovered model, with the catalog filling in what the provider did not say."""
    known = load_catalog().find(kind, found.model_id)
    return DiscoveredOut(
        model_id=found.model_id,
        display_name=known.name
        if known and found.display_name == found.model_id
        else found.display_name,
        context_tokens=found.context_tokens or (known.context if known else None),
        max_output_tokens=found.max_output_tokens or (known.max_output if known else None),
        capabilities=list(found.capabilities or (known.capabilities if known else ())),
        added=found.model_id in added,
        price_source=price_source(kind, found.model_id, Price()),
    )


@router.post("/providers/{provider_id}/models/fetch")
async def fetch_models(
    provider_id: uuid.UUID,
    _who: Admin,
    session: SessionDep,
    resolver: ResolverDep,
    factory: HttpClientFactoryDep,
) -> list[DiscoveredOut]:
    """Ask the provider which models the account can use. Nothing is added: the page offers the
    list and adds the ones that are picked."""
    provider = await provider_by_id(session, provider_id)
    kind = ProviderKind(provider.kind)
    try:
        async with connected(provider, resolver, factory) as adapter:
            found = await adapter.list_models()
    except UpstreamError as error:
        raise AppError(502, f"provider_{error.failure.value}", error.detail) from None
    added = set(
        await session.scalars(select(AiModel.model_id).where(AiModel.provider_id == provider.id))
    )
    return [offered(kind, one, added) for one in found]
