"""Providers, their models, the price catalog and the default model per role."""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.kinds import KINDS, ProviderKind
from app.ai.ledger import overrides_of, spend_this_month
from app.ai.netguard import BaseUrlRejected, Resolver, check_base_url, system_resolver
from app.ai.pricing import Price, load_catalog, price_for
from app.ai.roles import ROLE_LABELS, AgentRole
from app.ai.schemas import (
    CatalogModelOut,
    CatalogOut,
    KindOut,
    ModelIn,
    ModelOut,
    ModelUpdate,
    PriceOut,
    ProviderIn,
    ProviderOut,
    ProviderUpdate,
    RoleDefaultIn,
    RoleDefaultOut,
)
from app.auth import audit
from app.auth.deps import ADMIN, Admin, SignedIn
from app.db.base import utc_now
from app.db.models import AiModel, AiProvider, AiRoleDefault
from app.db.session import SessionDep
from app.errors import AppError

router = APIRouter(prefix="/api", tags=["ai"])


def get_resolver() -> Resolver:
    """How host names are looked up (the tests replace this one)."""
    return system_resolver


ResolverDep = Annotated[Resolver, Depends(get_resolver)]


async def _provider(session: AsyncSession, provider_id: uuid.UUID) -> AiProvider:
    found = await session.get(AiProvider, provider_id)
    if found is None:
        raise AppError(404, "not_found", "There is no such provider")
    return found


async def _model(session: AsyncSession, provider_id: uuid.UUID, model_ref: uuid.UUID) -> AiModel:
    found = await session.get(AiModel, model_ref)
    if found is None or found.provider_id != provider_id:
        raise AppError(404, "not_found", "There is no such model")
    return found


async def _checked_url(url: str, kind: ProviderKind, resolver: Resolver) -> str:
    try:
        return await check_base_url(url, kind, resolver)
    except BaseUrlRejected as error:
        raise AppError(422, "base_url_rejected", str(error)) from None


async def _provider_out(session: AsyncSession, providers: list[AiProvider]) -> list[ProviderOut]:
    rows = await session.execute(
        select(AiModel.provider_id, func.count()).group_by(AiModel.provider_id)
    )
    counts = dict(rows.all())
    spent = await spend_this_month(session, utc_now())
    return [
        ProviderOut(
            id=one.id,
            kind=ProviderKind(one.kind),
            name=one.name,
            base_url=one.base_url,
            enabled=one.enabled,
            has_key=one.api_key is not None,
            key_last4=one.api_key_last4,
            monthly_budget_usd=one.monthly_budget_usd,
            hard_stop=one.hard_stop,
            spent_this_month_usd=spent.get(one.id, Decimal(0)),
            model_count=counts.get(one.id, 0),
            created_at=one.created_at,
        )
        for one in providers
    ]


def _model_out(provider: AiProvider, model: AiModel) -> ModelOut:
    kind = ProviderKind(provider.kind)
    overrides = overrides_of(model) or Price()
    effective = price_for(kind, model.model_id, overrides)
    if overrides != Price():
        source = "override"
    elif kind is ProviderKind.OLLAMA_LOCAL:
        source = "free"
    elif load_catalog().find(kind, model.model_id) is not None:
        source = "catalog"
    else:
        source = "unknown"
    return ModelOut(
        id=model.id,
        provider_id=model.provider_id,
        model_id=model.model_id,
        display_name=model.display_name,
        context_tokens=model.context_tokens,
        max_output_tokens=model.max_output_tokens,
        capabilities=list(model.capabilities),
        supports_tools="tools" in model.capabilities,
        enabled=model.enabled,
        price=PriceOut.of(effective),
        price_source=source,
        overrides=PriceOut.of(overrides),
    )


@router.get("/ai/kinds")
async def kinds(_who: SignedIn) -> list[KindOut]:
    """The kinds of provider that can be added, with their usual addresses."""
    return [
        KindOut(
            kind=kind,
            label=info.label,
            default_base_url=info.default_base_url,
            needs_key=info.needs_key,
        )
        for kind, info in KINDS.items()
    ]


@router.get("/ai/catalog")
async def catalog(_who: SignedIn) -> CatalogOut:
    """The models and prices Blindspot knows, and when they were last checked."""
    found = load_catalog()
    return CatalogOut(
        verified_on=found.verified_on,
        source=found.source,
        models=[
            CatalogModelOut(
                kind=one.kind,
                id=one.id,
                name=one.name,
                context=one.context,
                max_output=one.max_output,
                capabilities=list(one.capabilities),
                price=PriceOut.of(one.price),
                long_prompt_above=None if one.long_prompt is None else one.long_prompt.above,
                long_prompt_price=None
                if one.long_prompt is None
                else PriceOut.of(one.long_prompt.price),
            )
            for one in found.models
        ],
    )


@router.get("/providers")
async def list_providers(_who: SignedIn, session: SessionDep) -> list[ProviderOut]:
    """Every provider, oldest first."""
    rows = list(await session.scalars(select(AiProvider).order_by(AiProvider.created_at)))
    return await _provider_out(session, rows)


@router.post("/providers", status_code=201)
async def add_provider(
    body: ProviderIn, request: Request, who: Admin, session: SessionDep, resolver: ResolverDep
) -> ProviderOut:
    """Add a provider."""
    info = KINDS[body.kind]
    key = body.api_key.get_secret_value().strip() if body.api_key else ""
    if info.needs_key and not key:
        raise AppError(422, "key_required", f"{info.label} needs an API key")
    url = await _checked_url(body.base_url or info.default_base_url, body.kind, resolver)
    provider = AiProvider(
        kind=body.kind.value,
        name=body.name,
        base_url=url,
        api_key=key or None,
        api_key_last4=key[-4:] if key else None,
        enabled=body.enabled,
        monthly_budget_usd=body.monthly_budget_usd,
        hard_stop=body.hard_stop,
    )
    try:
        async with session.begin_nested():
            session.add(provider)
            await session.flush()
    except IntegrityError:
        raise AppError(409, "name_taken", "A provider with that name already exists") from None
    audit.record(
        session,
        request,
        "provider.create",
        actor=who.user,
        target=("provider", provider.id),
        detail={"kind": body.kind.value, "name": body.name, "has_key": bool(key)},
    )
    return (await _provider_out(session, [provider]))[0]


@router.get("/providers/{provider_id}")
async def get_provider(provider_id: uuid.UUID, _who: SignedIn, session: SessionDep) -> ProviderOut:
    """One provider."""
    return (await _provider_out(session, [await _provider(session, provider_id)]))[0]


@router.patch("/providers/{provider_id}")
async def change_provider(
    provider_id: uuid.UUID,
    body: ProviderUpdate,
    *,
    request: Request,
    who: Admin,
    session: SessionDep,
    resolver: ResolverDep,
) -> ProviderOut:
    """Change a provider. A new key replaces the old one; the old one is never shown."""
    provider = await _provider(session, provider_id)
    kind = ProviderKind(provider.kind)
    changed: list[str] = []
    if body.base_url is not None:
        provider.base_url = await _checked_url(body.base_url, kind, resolver)
        changed.append("base_url")
    if body.api_key is not None:
        key = body.api_key.get_secret_value().strip()
        provider.api_key, provider.api_key_last4 = key, key[-4:]
        changed.append("api_key")
    elif body.remove_key:
        if KINDS[kind].needs_key:
            raise AppError(422, "key_required", f"{KINDS[kind].label} needs an API key")
        provider.api_key = provider.api_key_last4 = None
        changed.append("api_key")
    if body.name is not None:
        provider.name = body.name
        changed.append("name")
    if body.enabled is not None:
        provider.enabled = body.enabled
        changed.append("enabled")
    if "monthly_budget_usd" in body.model_fields_set:
        provider.monthly_budget_usd = body.monthly_budget_usd
        changed.append("monthly_budget_usd")
    if body.hard_stop is not None:
        provider.hard_stop = body.hard_stop
        changed.append("hard_stop")
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        raise AppError(409, "name_taken", "A provider with that name already exists") from None
    audit.record(
        session,
        request,
        "provider.update",
        actor=who.user,
        target=("provider", provider.id),
        detail={"changed": ", ".join(changed)},
    )
    return (await _provider_out(session, [provider]))[0]


@router.delete("/providers/{provider_id}", status_code=204)
async def remove_provider(
    provider_id: uuid.UUID, request: Request, who: Admin, session: SessionDep
) -> Response:
    """Remove a provider, its models and its role defaults. Its usage stays in the ledger."""
    provider = await _provider(session, provider_id)
    await session.delete(provider)
    audit.record(
        session,
        request,
        "provider.delete",
        actor=who.user,
        target=("provider", provider.id),
        detail={"name": provider.name},
    )
    return Response(status_code=204)


@router.get("/providers/{provider_id}/models")
async def list_models(
    provider_id: uuid.UUID, _who: SignedIn, session: SessionDep
) -> list[ModelOut]:
    """A provider's models."""
    provider = await _provider(session, provider_id)
    rows = await session.scalars(
        select(AiModel).where(AiModel.provider_id == provider.id).order_by(AiModel.model_id)
    )
    return [_model_out(provider, one) for one in rows]


@router.post("/providers/{provider_id}/models", status_code=201)
async def add_model(
    provider_id: uuid.UUID, body: ModelIn, request: Request, who: Admin, session: SessionDep
) -> ModelOut:
    """Add a model by hand (fetching adds them for you). What is left out comes from the catalog
    when it knows the model."""
    provider = await _provider(session, provider_id)
    known = load_catalog().find(ProviderKind(provider.kind), body.model_id)
    capabilities = body.capabilities
    if capabilities is None:
        capabilities = list(known.capabilities) if known else []
    model = AiModel(
        provider_id=provider.id,
        model_id=body.model_id,
        display_name=body.display_name or (known.name if known else body.model_id),
        context_tokens=body.context_tokens or (known.context if known else None),
        max_output_tokens=body.max_output_tokens or (known.max_output if known else None),
        capabilities=capabilities,
        enabled=body.enabled,
        price_input=body.price_input,
        price_output=body.price_output,
        price_cache_read=body.price_cache_read,
        price_cache_write=body.price_cache_write,
        price_cache_write_long=body.price_cache_write_long,
    )
    try:
        async with session.begin_nested():
            session.add(model)
            await session.flush()
    except IntegrityError:
        raise AppError(409, "model_exists", "That model is already listed") from None
    audit.record(
        session,
        request,
        "provider.model_add",
        actor=who.user,
        target=("provider", provider.id),
        detail={"model": body.model_id},
    )
    return _model_out(provider, model)


_PRICE_FIELDS = (
    "price_input",
    "price_output",
    "price_cache_read",
    "price_cache_write",
    "price_cache_write_long",
)


@router.patch("/providers/{provider_id}/models/{model_ref}")
async def change_model(
    provider_id: uuid.UUID,
    model_ref: uuid.UUID,
    body: ModelUpdate,
    *,
    request: Request,
    who: Admin,
    session: SessionDep,
) -> ModelOut:
    """Change a model's name, whether it can be chosen, its capabilities or its prices."""
    provider = await _provider(session, provider_id)
    model = await _model(session, provider_id, model_ref)
    if body.display_name is not None:
        model.display_name = body.display_name
    if body.enabled is not None:
        model.enabled = body.enabled
    if body.capabilities is not None:
        model.capabilities = body.capabilities
    for field in _PRICE_FIELDS:
        if field in body.model_fields_set:
            setattr(model, field, getattr(body, field))
    audit.record(
        session,
        request,
        "provider.model_update",
        actor=who.user,
        target=("provider", provider.id),
        detail={"model": model.model_id, "changed": ", ".join(sorted(body.model_fields_set))},
    )
    return _model_out(provider, model)


@router.delete("/providers/{provider_id}/models/{model_ref}", status_code=204)
async def remove_model(
    provider_id: uuid.UUID,
    model_ref: uuid.UUID,
    request: Request,
    who: Admin,
    session: SessionDep,
) -> Response:
    """Remove a model from the list (and from any role it was the default for)."""
    provider = await _provider(session, provider_id)
    model = await _model(session, provider_id, model_ref)
    await session.delete(model)
    audit.record(
        session,
        request,
        "provider.model_remove",
        actor=who.user,
        target=("provider", provider.id),
        detail={"model": model.model_id},
    )
    return Response(status_code=204)


@router.get("/ai/role-defaults")
async def role_defaults(_who: SignedIn, session: SessionDep) -> list[RoleDefaultOut]:
    """Every role with the model chosen for it, if any."""
    rows = await session.execute(
        select(AiRoleDefault.role, AiModel.id, AiModel.model_id, AiProvider.name)
        .join(AiModel, AiModel.id == AiRoleDefault.model_ref)
        .join(AiProvider, AiProvider.id == AiModel.provider_id)
    )
    chosen = {role: (ref, model, name) for role, ref, model, name in rows.all()}
    return [
        RoleDefaultOut(
            role=role,
            label=ROLE_LABELS[role],
            model_ref=chosen[role.value][0] if role.value in chosen else None,
            provider_name=chosen[role.value][2] if role.value in chosen else None,
            model_id=chosen[role.value][1] if role.value in chosen else None,
        )
        for role in AgentRole
    ]


@router.put("/ai/role-defaults/{role}", status_code=204, dependencies=[Depends(ADMIN)])
async def set_role_default(
    role: AgentRole, body: RoleDefaultIn, request: Request, who: Admin, session: SessionDep
) -> Response:
    """Choose the model a role uses by default."""
    model = await session.get(AiModel, body.model_ref)
    if model is None:
        raise AppError(404, "not_found", "There is no such model")
    if not model.enabled:
        raise AppError(409, "model_disabled", "That model is turned off")
    current = await session.get(AiRoleDefault, role.value)
    if current is None:
        session.add(AiRoleDefault(role=role.value, model_ref=model.id))
    else:
        current.model_ref = model.id
    audit.record(
        session,
        request,
        "ai.role_default",
        actor=who.user,
        target=("model", model.id),
        detail={"role": role.value, "model": model.model_id},
    )
    return Response(status_code=204)


@router.delete("/ai/role-defaults/{role}", status_code=204)
async def clear_role_default(
    role: AgentRole, request: Request, who: Admin, session: SessionDep
) -> Response:
    """Stop using a default for a role."""
    current = await session.get(AiRoleDefault, role.value)
    if current is not None:
        await session.delete(current)
        audit.record(
            session,
            request,
            "ai.role_default",
            actor=who.user,
            detail={"role": role.value, "model": ""},
        )
    return Response(status_code=204)
