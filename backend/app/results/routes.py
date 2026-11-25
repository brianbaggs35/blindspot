"""The results of a pentest: what its tools found, with three views of each (friendly, technical
and raw), notes and tags, manual notes, imported tool output, delete and restore.

Anyone signed in can read. Changing anything needs an administrator, and a pentest that is
archived or in the trash cannot be changed. Secrets a tool found are masked everywhere; revealing
one is a request of its own and is written to the audit trail.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Text

from app.auth import audit
from app.auth.deps import Admin, SignedIn
from app.db.models import Pentest, PentestResult
from app.db.session import SessionDep
from app.errors import AppError
from app.pentests.service import ensure_editable, find
from app.results.schemas import (
    BulkIn,
    BulkOut,
    ImportIn,
    ManualIn,
    PatchIn,
    RawOut,
    ResultList,
    ResultOut,
    RevealOut,
)
from app.results.service import (
    Run,
    credentials_of,
    detail_of,
    ensure_room,
    raw_of,
    record_result,
    summary_of,
)
from app.tools.parsers import PARSERS, ParseError, parse_output
from app.tools.parsers.schema import Severity
from app.tools.registry import bundled_tools

router = APIRouter(prefix="/api", tags=["results"])

MAX_PAGE = 200
Short = Annotated[str, Query(max_length=64)]


def tool_for_parser(parser: str) -> str:
    """The bundled tool that makes a parser's kind of output."""
    for tool in bundled_tools():
        if parser in tool.manifest.parsers:
            return tool.manifest.id
    return "x.import"  # pragma: no cover  # every parser belongs to a bundled tool (tested)


async def _row(session: AsyncSession, pentest_id: uuid.UUID, result_id: uuid.UUID) -> PentestResult:
    row = await session.get(PentestResult, result_id)
    if row is None or row.pentest_id != pentest_id:
        raise AppError(404, "result_not_found", "There is no such result")
    return row


@router.get("/pentests/{pentest_id}/results")
async def list_results(  # noqa: PLR0913  # one parameter for each filter of the page
    pentest_id: uuid.UUID,
    _who: SignedIn,
    session: SessionDep,
    *,
    view: Literal["live", "trash"] = "live",
    tool: Short | None = None,
    agent: Short | None = None,
    test: Short | None = None,
    severity: Severity | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> ResultList:
    """Results, newest first, with the options for the filters. `q` looks in the title, the
    notes, the tags, the tool and the test."""
    await find(session, pentest_id)
    where = [
        PentestResult.pentest_id == pentest_id,
        PentestResult.deleted_at.is_not(None) if view == "trash" else PentestResult.not_deleted(),
    ]
    if tool:
        where.append(PentestResult.tool_id == tool)
    if agent:
        where.append(PentestResult.agent_role == agent)
    if test:
        where.append(PentestResult.test_id == test)
    if severity:
        where.append(PentestResult.top_severity == severity.value)
    if since:
        where.append(PentestResult.ran_at >= since)
    if until:
        where.append(PentestResult.ran_at <= until)
    if q and q.strip():
        like = f"%{q.strip().lower().replace('%', r'\%').replace('_', r'\_')}%"
        where.append(
            or_(
                func.lower(PentestResult.title).like(like),
                func.lower(PentestResult.notes).like(like),
                func.lower(cast(PentestResult.tags, Text)).like(like),
                func.lower(func.coalesce(PentestResult.tool_id, "")).like(like),
                func.lower(func.coalesce(PentestResult.test_id, "")).like(like),
            )
        )
    total = await session.scalar(select(func.count()).select_from(PentestResult).where(*where))
    rows = await session.scalars(
        select(PentestResult)
        .where(*where)
        .order_by(PentestResult.ran_at.desc(), PentestResult.id.desc())
        .limit(limit)
        .offset(offset)
    )
    live = (PentestResult.pentest_id == pentest_id, PentestResult.not_deleted())
    tools = await session.scalars(
        select(PentestResult.tool_id).where(*live, PentestResult.tool_id.is_not(None)).distinct()
    )
    agents = await session.scalars(
        select(PentestResult.agent_role)
        .where(*live, PentestResult.agent_role.is_not(None))
        .distinct()
    )
    return ResultList(
        items=[summary_of(row) for row in rows],
        total=total or 0,
        tools=sorted(t for t in tools if t),
        agents=sorted(a for a in agents if a),
    )


async def _editable(session: AsyncSession, pentest_id: uuid.UUID) -> Pentest:
    row = await find(session, pentest_id)
    ensure_editable(row)
    return row


@router.post("/pentests/{pentest_id}/results", status_code=201)
async def add_note(
    pentest_id: uuid.UUID, body: ManualIn, request: Request, who: Admin, session: SessionDep
) -> ResultOut:
    """Write a result by hand: a note on what was seen or tried."""
    pentest = await _editable(session, pentest_id)
    await ensure_room(session, pentest.id)
    row = record_result(
        session,
        pentest.id,
        source="manual",
        status="manual",
        title=body.title,
        notes=body.notes,
        tags=body.tags,
        run=Run(test_id=body.test_id),
        severity=body.severity,
        created_by=who.user.id,
    )
    await session.flush()
    audit.record(
        session,
        request,
        "result.create",
        actor=who.user,
        target=("pentest", pentest.id),
        detail={"result": str(row.id), "source": "manual"},
    )
    return detail_of(row)


@router.post("/pentests/{pentest_id}/results/import", status_code=201)
async def import_output(
    pentest_id: uuid.UUID, body: ImportIn, request: Request, who: Admin, session: SessionDep
) -> ResultOut:
    """Add the output of a tool that ran somewhere else, read the same way a run's output is."""
    pentest = await _editable(session, pentest_id)
    if body.parser not in PARSERS:
        raise AppError(422, "unknown_parser", "There is no parser by that name")
    await ensure_room(session, pentest.id)
    tool_id = body.tool_id or tool_for_parser(body.parser)
    try:
        result = parse_output(body.parser, tool_id, body.content.encode())
    except ParseError as error:
        raise AppError(422, "unreadable_output", str(error)) from None
    row = record_result(
        session,
        pentest.id,
        source="import",
        title=body.title or f"Imported {body.parser.replace('_', ' ')} output",
        result=result,
        raw=body.content,
        run=Run(tool_id=tool_id, test_id=body.test_id),
        notes=body.notes,
        tags=body.tags,
        created_by=who.user.id,
    )
    await session.flush()
    audit.record(
        session,
        request,
        "result.import",
        actor=who.user,
        target=("pentest", pentest.id),
        detail={"result": str(row.id), "parser": body.parser, "tool": tool_id},
    )
    return detail_of(row)


@router.post("/pentests/{pentest_id}/results/bulk")
async def bulk(
    pentest_id: uuid.UUID, body: BulkIn, request: Request, who: Admin, session: SessionDep
) -> BulkOut:
    """Delete, restore, tag or untag up to 100 results at once."""
    pentest = await _editable(session, pentest_id)
    if body.action in ("tag", "untag") and body.tag is None:
        raise AppError(422, "tag_needed", "Say which tag")
    rows = list(
        await session.scalars(
            select(PentestResult).where(
                PentestResult.pentest_id == pentest.id, PentestResult.id.in_(body.ids)
            )
        )
    )
    changed = 0
    for row in rows:
        if body.action == "delete" and row.deleted_at is None:
            row.mark_deleted()
        elif body.action == "restore" and row.deleted_at is not None:
            row.restore()
        elif body.action == "tag" and body.tag and body.tag not in row.tags:
            row.tags = sorted({*row.tags, body.tag})
        elif body.action == "untag" and body.tag in row.tags:
            row.tags = [t for t in row.tags if t != body.tag]
        else:
            continue
        changed += 1
    audit.record(
        session,
        request,
        f"result.bulk_{body.action}",
        actor=who.user,
        target=("pentest", pentest.id),
        detail={"count": changed, "tag": body.tag},
    )
    return BulkOut(changed=changed)


@router.get("/pentests/{pentest_id}/results/{result_id}")
async def get_result(
    pentest_id: uuid.UUID, result_id: uuid.UUID, _who: SignedIn, session: SessionDep
) -> ResultOut:
    """One result with its friendly and technical views. The raw output is a separate request."""
    await find(session, pentest_id)
    return detail_of(await _row(session, pentest_id, result_id))


@router.get("/pentests/{pentest_id}/results/{result_id}/raw")
async def get_raw(
    pentest_id: uuid.UUID, result_id: uuid.UUID, _who: SignedIn, session: SessionDep
) -> RawOut:
    """What the tool printed, the command exactly as it ran, its exit code and how long it took."""
    await find(session, pentest_id)
    return raw_of(await _row(session, pentest_id, result_id))


@router.patch("/pentests/{pentest_id}/results/{result_id}")
async def patch_result(
    pentest_id: uuid.UUID,
    result_id: uuid.UUID,
    body: PatchIn,
    request: Request,
    *,
    who: Admin,
    session: SessionDep,
) -> ResultOut:
    """Change the title, notes, tags or test of a result. The output itself never changes."""
    pentest = await _editable(session, pentest_id)
    row = await _row(session, pentest.id, result_id)
    sent = body.model_fields_set
    if "title" in sent and body.title is not None:
        row.title = body.title
    if "notes" in sent and body.notes is not None:
        row.notes = body.notes
    if "tags" in sent and body.tags is not None:
        row.tags = sorted(set(body.tags))
    if "test_id" in sent:
        row.test_id = body.test_id
    audit.record(
        session,
        request,
        "result.update",
        actor=who.user,
        target=("pentest", pentest.id),
        detail={"result": str(row.id), "fields": sorted(sent)},
    )
    await session.flush()
    return detail_of(row)


@router.delete("/pentests/{pentest_id}/results/{result_id}", status_code=204)
async def delete_result(
    pentest_id: uuid.UUID, result_id: uuid.UUID, request: Request, who: Admin, session: SessionDep
) -> Response:
    """Move a result to the trash. Nothing is lost: restore brings it back."""
    pentest = await _editable(session, pentest_id)
    row = await _row(session, pentest.id, result_id)
    if row.deleted_at is not None:
        raise AppError(409, "in_trash", "This result is already in the trash")
    row.mark_deleted()
    audit.record(
        session,
        request,
        "result.delete",
        actor=who.user,
        target=("pentest", pentest.id),
        detail={"result": str(row.id)},
    )
    return Response(status_code=204)


@router.post("/pentests/{pentest_id}/results/{result_id}/restore")
async def restore_result(
    pentest_id: uuid.UUID, result_id: uuid.UUID, request: Request, who: Admin, session: SessionDep
) -> ResultOut:
    """Bring a result back from the trash."""
    pentest = await _editable(session, pentest_id)
    row = await _row(session, pentest.id, result_id)
    if row.deleted_at is None:
        raise AppError(409, "not_in_trash", "This result is not in the trash")
    row.restore()
    audit.record(
        session,
        request,
        "result.restore",
        actor=who.user,
        target=("pentest", pentest.id),
        detail={"result": str(row.id)},
    )
    await session.flush()
    return detail_of(row)


@router.post("/pentests/{pentest_id}/results/{result_id}/credentials/{index}/reveal")
async def reveal_credential(
    pentest_id: uuid.UUID,
    result_id: uuid.UUID,
    index: int,
    request: Request,
    *,
    who: Admin,
    session: SessionDep,
) -> RevealOut:
    """Show one secret a tool found. Every reveal is in the audit trail, with who and which result
    but never the secret."""
    await find(session, pentest_id)
    row = await _row(session, pentest_id, result_id)
    found = credentials_of(row)
    if not 0 <= index < len(found):
        raise AppError(404, "credential_not_found", "This result has no such credential")
    audit.record(
        session,
        request,
        "result.reveal",
        actor=who.user,
        target=("pentest", pentest_id),
        detail={"result": str(row.id), "index": index},
    )
    return RevealOut(secret=str(found[index]["secret"]))
