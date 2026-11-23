"""Methodologies: browse them, read a test's playbook, replace a playbook, and bring in updates
after seeing what they change."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, cast

import httpx2
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.adapters.factory import HttpClientFactoryDep
from app.auth import audit
from app.auth.deps import Admin, SignedIn
from app.config import get_settings
from app.db.base import utc_now
from app.db.models import Methodology, MethodologyVersion, PlaybookOverride
from app.db.session import SessionDep
from app.errors import AppError
from app.methodology.build import PackError
from app.methodology.packs import (
    WSTG_UPSTREAM,
    bundled,
    load_pack,
    load_packs,
    snapshot_version,
    wstg_spec,
)
from app.methodology.schemas import (
    ApplyIn,
    CategoryOut,
    EnabledIn,
    MethodologyDetail,
    MethodologyOut,
    ReloadOut,
    TestDetail,
    TestSummary,
    UpdateCheck,
    UpdateSource,
    VersionOut,
)
from app.methodology.spec import MethodologySpec, Playbook, Test
from app.methodology.store import (
    Origin,
    Stored,
    add_missing,
    add_snapshot,
    diff_specs,
    overrides,
    stored,
    with_overrides,
)

router = APIRouter(prefix="/api", tags=["methodologies"])

MAX_UPSTREAM_BYTES = 2_000_000
UPSTREAM_HOST = "raw.githubusercontent.com"


def get_packs_dir() -> Path:
    """Where administrators put methodology packs (the tests replace this one)."""
    return get_settings().data_dir / "methodologies"


PacksDir = Annotated[Path, Depends(get_packs_dir)]


async def seed(session: AsyncSession) -> None:
    """Store the methodologies that ship with the app, the first time anything asks."""
    if await session.get(Methodology, "wstg") is None:
        await add_missing(session, bundled(), "bundled")


async def _stored(session: AsyncSession, methodology_id: str) -> Stored:
    await seed(session)
    found = await stored(session, methodology_id)
    if found is None:
        raise AppError(404, "not_found", "There is no such methodology")
    return found


async def _effective(session: AsyncSession, found: Stored) -> MethodologySpec:
    return with_overrides(found.spec, await overrides(session, found.row.id))


def _out(found: Stored, spec: MethodologySpec) -> MethodologyOut:
    tests = spec.tests()
    return MethodologyOut(
        id=found.row.id,
        name=found.row.name,
        source_url=found.row.source_url,
        license=found.row.license,
        origin=cast("Origin", found.row.origin),
        enabled=found.row.enabled,
        version_number=found.version.number,
        version_label=found.version.label,
        content_hash=found.version.content_hash,
        categories=len(spec.categories),
        tests=len(tests),
        authored_playbooks=sum(test.playbook_source == "authored" for test in tests),
        custom_playbooks=sum(test.playbook_source == "custom" for test in tests),
        manual_review_tests=sum(test.playbook.manual_review for test in tests),
        imported_at=found.version.created_at,
        can_update_from_upstream=found.row.id == "wstg",
    )


def _summary(test: Test) -> TestSummary:
    return TestSummary(
        id=test.id,
        name=test.name,
        reference=test.reference,
        risk_class=test.risk_class,
        tags=test.tags,
        requires=test.requires,
        tools=test.playbook.tools,
        manual_review=test.playbook.manual_review,
        playbook_source=test.playbook_source,
    )


def _test_of(found: Stored, spec: MethodologySpec, test_id: str) -> TestDetail:
    located = spec.find(test_id)
    if located is None:
        raise AppError(404, "not_found", "There is no such test")
    category, test = located
    return TestDetail(
        methodology_id=found.row.id, category_id=category.id, category_name=category.name, test=test
    )


@router.get("/methodologies")
async def list_methodologies(_who: SignedIn, session: SessionDep) -> list[MethodologyOut]:
    """Every methodology."""
    await seed(session)
    rows = await session.scalars(select(Methodology.id).order_by(Methodology.name))
    out: list[MethodologyOut] = []
    for methodology_id in rows.all():
        found = await _stored(session, methodology_id)
        out.append(_out(found, await _effective(session, found)))
    return out


@router.post("/methodologies/reload")
async def reload_packs(
    request: Request, who: Admin, session: SessionDep, folder: PacksDir
) -> ReloadOut:
    """Read the packs folder. New packs are added; a pack that changed is only reported, so it can
    be reviewed and applied from its updates."""
    await seed(session)
    specs, problems = load_packs(folder)
    built_in = {spec.id for spec in bundled()}
    allowed: list[MethodologySpec] = []
    for spec in specs:
        if spec.id in built_in:
            problems[spec.id] = "This id belongs to a methodology that ships with Blindspot"
        else:
            allowed.append(spec)
    added = await add_missing(session, allowed, "folder")
    waiting: list[str] = []
    for spec in allowed:
        current = await stored(session, spec.id)
        if current and spec.id not in added and current.version.content_hash != spec.content_hash():
            waiting.append(spec.id)
    audit.record(
        session,
        request,
        "methodology.reload",
        actor=who.user,
        detail={"added": ", ".join(added), "problems": len(problems)},
    )
    return ReloadOut(added=added, updates_available=waiting, problems=problems)


@router.get("/methodologies/{methodology_id}")
async def get_methodology(
    methodology_id: str, _who: SignedIn, session: SessionDep
) -> MethodologyDetail:
    """A methodology with every category and an outline of each test."""
    found = await _stored(session, methodology_id)
    spec = await _effective(session, found)
    base = _out(found, spec)
    return MethodologyDetail(
        **base.model_dump(),
        category_list=[
            CategoryOut(
                id=category.id,
                name=category.name,
                reporting_label=category.reporting_label,
                tests=[_summary(test) for test in category.tests],
            )
            for category in spec.categories
        ],
    )


@router.patch("/methodologies/{methodology_id}")
async def set_enabled(
    methodology_id: str, body: EnabledIn, request: Request, who: Admin, session: SessionDep
) -> MethodologyOut:
    """Turn a methodology on or off. One that is off cannot be chosen for a new pentest."""
    found = await _stored(session, methodology_id)
    found.row.enabled = body.enabled
    audit.record(
        session,
        request,
        "methodology.enable" if body.enabled else "methodology.disable",
        actor=who.user,
        target=("methodology", methodology_id),
    )
    return _out(found, await _effective(session, found))


@router.get("/methodologies/{methodology_id}/versions")
async def list_versions(
    methodology_id: str, _who: SignedIn, session: SessionDep
) -> list[VersionOut]:
    """The snapshots of a methodology, newest first."""
    await _stored(session, methodology_id)
    rows = await session.scalars(
        select(MethodologyVersion)
        .where(MethodologyVersion.methodology_id == methodology_id)
        .order_by(MethodologyVersion.number.desc())
    )
    return [
        VersionOut(
            number=row.number,
            label=row.label,
            content_hash=row.content_hash,
            source=row.source,
            created_at=row.created_at,
            tests=len(MethodologySpec.model_validate(row.spec).tests()),
        )
        for row in rows
    ]


@router.get("/methodologies/{methodology_id}/tests/{test_id}")
async def get_test(
    methodology_id: str, test_id: str, _who: SignedIn, session: SessionDep
) -> TestDetail:
    """One test with its playbook as it is used now."""
    found = await _stored(session, methodology_id)
    return _test_of(found, await _effective(session, found), test_id)


@router.put("/methodologies/{methodology_id}/tests/{test_id}/playbook")
async def replace_playbook(
    methodology_id: str,
    test_id: str,
    body: Playbook,
    request: Request,
    *,
    who: Admin,
    session: SessionDep,
) -> TestDetail:
    """Replace a test's playbook. The original stays in the snapshot and comes back if this is
    removed."""
    found = await _stored(session, methodology_id)
    if found.spec.find(test_id) is None:
        raise AppError(404, "not_found", "There is no such test")
    row = await session.get(PlaybookOverride, (methodology_id, test_id))
    if row is None:
        row = PlaybookOverride(methodology_id=methodology_id, test_id=test_id)
        session.add(row)
    row.playbook, row.updated_by = body.model_dump(mode="json"), who.user.id
    audit.record(
        session,
        request,
        "methodology.playbook.change",
        actor=who.user,
        target=("methodology", methodology_id),
        detail={"test": test_id},
    )
    return _test_of(found, await _effective(session, found), test_id)


@router.delete("/methodologies/{methodology_id}/tests/{test_id}/playbook", status_code=204)
async def reset_playbook(
    methodology_id: str, test_id: str, request: Request, who: Admin, session: SessionDep
) -> Response:
    """Go back to the playbook the test came with."""
    await _stored(session, methodology_id)
    row = await session.get(PlaybookOverride, (methodology_id, test_id))
    if row is None:
        raise AppError(404, "not_found", "That playbook has not been changed")
    await session.delete(row)
    audit.record(
        session,
        request,
        "methodology.playbook.reset",
        actor=who.user,
        target=("methodology", methodology_id),
        detail={"test": test_id},
    )
    return Response(status_code=204)


async def _fetch_upstream(factory: Callable[[], httpx2.AsyncClient]) -> bytes:
    """The upstream WSTG checklist. The address is fixed here, so nobody can aim this at another
    host; it follows no redirects and reads at most two megabytes."""
    try:
        async with factory() as client, client.stream("GET", WSTG_UPSTREAM) as answer:
            if answer.status_code != 200:
                raise AppError(
                    502, "upstream_failed", f"{UPSTREAM_HOST} answered {answer.status_code}"
                )
            body = bytearray()
            async for chunk in answer.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_UPSTREAM_BYTES:
                    raise AppError(502, "upstream_failed", "The checklist is larger than expected")
            return bytes(body)
    except httpx2.HTTPError:
        raise AppError(502, "upstream_failed", f"Could not reach {UPSTREAM_HOST}") from None


async def _candidate(
    found: Stored, source: UpdateSource, folder: Path, factory: Callable[[], httpx2.AsyncClient]
) -> MethodologySpec:
    """The methodology an update would bring in."""
    methodology_id = found.row.id
    try:
        if source == "upstream":
            if methodology_id != "wstg":
                raise AppError(
                    422, "no_upstream", "This methodology has no upstream to update from"
                )
            raw = await _fetch_upstream(factory)
            return wstg_spec(raw, version=snapshot_version(utc_now().date()))
        if found.row.origin == "bundled":
            shipped = next((spec for spec in bundled() if spec.id == methodology_id), None)
            if shipped is None:
                raise AppError(404, "not_found", "This release no longer ships that methodology")
            return shipped
        return load_pack(folder / methodology_id)
    except PackError as error:
        raise AppError(422, "pack_invalid", str(error)) from None


@router.get("/methodologies/{methodology_id}/updates")
async def check_for_update(
    methodology_id: str,
    _who: Admin,
    session: SessionDep,
    folder: PacksDir,
    factory: HttpClientFactoryDep,
    source: Annotated[UpdateSource, Query()] = "origin",
) -> UpdateCheck:
    """What an update would change, without applying it. `source` is where the methodology came
    from (the app's own copy, or its pack folder) or, for WSTG, the upstream checklist."""
    found = await _stored(session, methodology_id)
    candidate = await _candidate(found, source, folder, factory)
    return UpdateCheck(
        source=source,
        current_hash=found.version.content_hash,
        candidate_hash=candidate.content_hash(),
        candidate_label=candidate.version,
        changed=candidate.content_hash() != found.version.content_hash,
        diff=diff_specs(found.spec, candidate),
    )


@router.post("/methodologies/{methodology_id}/updates")
async def apply_update(
    methodology_id: str,
    body: ApplyIn,
    request: Request,
    *,
    who: Admin,
    session: SessionDep,
    folder: PacksDir,
    factory: HttpClientFactoryDep,
) -> MethodologyOut:
    """Apply the update that was reviewed. If what is on offer has changed since, nothing is
    applied and the administrator sees the new diff first."""
    found = await _stored(session, methodology_id)
    candidate = await _candidate(found, body.source, folder, factory)
    if candidate.content_hash() != body.candidate_hash:
        raise AppError(
            409, "candidate_changed", "The update changed since you reviewed it. Check again."
        )
    if candidate.content_hash() != found.version.content_hash:
        version = await add_snapshot(
            session,
            candidate,
            origin=cast("Origin", found.row.origin),
            source=body.source if body.source == "upstream" else found.row.origin,
            user_id=who.user.id,
        )
        audit.record(
            session,
            request,
            "methodology.update",
            actor=who.user,
            target=("methodology", methodology_id),
            detail={"version": version.number, "source": body.source},
        )
        found = await _stored(session, methodology_id)
    return _out(found, await _effective(session, found))
