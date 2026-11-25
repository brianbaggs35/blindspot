"""The findings of a pentest: written by hand, made from a result or an agent's work, scored with
CVSS, backed by evidence, moved along a status workflow, merged when they repeat, and exported.

Anyone signed in can read. Changing anything needs an administrator, and a pentest that is
archived or in the trash cannot be changed. Evidence marked sealed is hidden everywhere; showing
it is a request of its own and is written to the audit trail.
"""

import base64
import uuid
from collections import Counter
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import Float, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import Text

from app.auth import audit
from app.auth.deps import Admin, SignedIn
from app.db.base import utc_now
from app.db.models import Finding, FindingEvidence, Pentest, PentestResult
from app.db.session import SessionDep
from app.errors import AppError
from app.findings import cvss, exchange, service
from app.findings.schemas import (
    MAX_PAGE,
    OWASP,
    TRANSITIONS,
    BulkIn,
    BulkOut,
    CommentIn,
    EvidenceIn,
    EvidencePatch,
    FindingIn,
    FindingList,
    FindingOut,
    FindingPatch,
    FindingSummary,
    Group,
    GroupBy,
    ImportIn,
    ImportOut,
    MergeIn,
    PromoteIn,
    RevealOut,
    ScoreOut,
    Sort,
    Status,
    StatusIn,
    VerifyIn,
)
from app.pentests.service import ensure_editable, find
from app.results.service import tool_result_of
from app.tools.parsers.schema import Severity

router = APIRouter(prefix="/api", tags=["findings"])

Short = Annotated[str, Query(max_length=120)]
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
_RANK = case(
    *[(Finding.severity == name.value, index) for index, name in enumerate(service.SEVERITIES)],
    else_=0,
)
_SCORE = func.coalesce(Finding.cvss4_score, Finding.cvss31_score)


async def _row(session: AsyncSession, pentest_id: uuid.UUID, finding_id: uuid.UUID) -> Finding:
    row = await session.get(Finding, finding_id)
    if row is None or row.pentest_id != pentest_id:
        raise AppError(404, "finding_not_found", "There is no such finding")
    return row


async def _evidence(
    session: AsyncSession, finding: Finding, evidence_id: uuid.UUID
) -> FindingEvidence:
    row = await session.get(FindingEvidence, evidence_id)
    if row is None or row.finding_id != finding.id:
        raise AppError(404, "evidence_not_found", "This finding has no such evidence")
    return row


async def _editable(session: AsyncSession, pentest_id: uuid.UUID) -> Pentest:
    row = await find(session, pentest_id)
    ensure_editable(row)
    return row


def _live(row: Finding) -> None:
    if row.deleted_at is not None:
        raise AppError(
            409, "in_trash", "This finding is in the trash", "Restore it before changing it."
        )


@router.get("/cvss/score")
async def score_vector(vector: Annotated[str, Query(max_length=300)], _who: SignedIn) -> ScoreOut:
    """The score and rating of a CVSS 3.1 or 4.0 vector, for the form to show as it is filled."""
    try:
        scored = cvss.score(vector)
    except cvss.VectorError as error:
        raise AppError(422, "bad_vector", str(error)) from None
    return ScoreOut(
        vector=scored.vector,
        version="4.0" if scored.vector.startswith(cvss.V4) else "3.1",
        score=scored.score,
        severity=Severity(scored.severity),
    )


@router.get("/findings/reference")
async def reference(_who: SignedIn) -> dict[str, object]:
    """The OWASP Top 10 categories and the status workflow, for the forms."""
    return {"owasp": OWASP, "transitions": TRANSITIONS}


def _like(text: str) -> str:
    return f"%{text.strip().lower().replace('%', r'\%').replace('_', r'\_')}%"


def _filters(  # one argument for each filter of the page
    pentest_id: uuid.UUID,
    *,
    view: Literal["live", "trash"],
    statuses: list[Status],
    severities: list[Severity],
    test: str | None,
    target: str | None,
    q: str | None,
) -> list[ColumnElement[bool]]:
    where = [
        Finding.pentest_id == pentest_id,
        Finding.deleted_at.is_not(None) if view == "trash" else Finding.not_deleted(),
    ]
    if statuses:
        where.append(Finding.status.in_(statuses))
    if severities:
        where.append(Finding.severity.in_([s.value for s in severities]))
    if test:
        where.append(cast(Finding.test_ids, Text).like(f'%"{test}"%'))
    if target and target.strip():
        where.append(func.lower(Finding.target).like(_like(target)))
    if q and q.strip():
        like = _like(q)
        where.append(
            or_(
                func.lower(Finding.title).like(like),
                func.lower(Finding.description).like(like),
                func.lower(Finding.target).like(like),
                func.lower(cast(Finding.cwe, Text)).like(like),
                func.lower(cast(Finding.test_ids, Text)).like(like),
                cast(Finding.number, Text) == q.strip().lower().removeprefix("f-"),
            )
        )
    return where


async def _counts(
    session: AsyncSession, column: InstrumentedAttribute[str], pentest_id: uuid.UUID
) -> dict[str, int]:
    return await service.pairs(
        session,
        select(column, func.count())
        .where(Finding.pentest_id == pentest_id, Finding.not_deleted())
        .group_by(column),
    )


async def _groups(
    session: AsyncSession, where: list[ColumnElement[bool]], group_by: GroupBy | None
) -> list[Group]:
    """How many of the filtered findings fall in each group of the chosen grouping."""
    if group_by is None:
        return []
    rows = (
        await session.execute(
            select(Finding.test_ids, Finding.target, Finding.severity).where(*where)
        )
    ).all()
    keys = [
        service.category_of(list(tests))
        if group_by == "category"
        else (target or "No target")
        if group_by == "target"
        else severity
        for tests, target, severity in rows
    ]
    return [Group(key=key, count=count) for key, count in sorted(Counter(keys).items())]


@router.get("/pentests/{pentest_id}/findings")
async def list_findings(  # noqa: PLR0913  # one parameter for each filter of the page
    pentest_id: uuid.UUID,
    _who: SignedIn,
    session: SessionDep,
    *,
    view: Literal["live", "trash"] = "live",
    status: Annotated[list[Status] | None, Query()] = None,
    severity: Annotated[list[Severity] | None, Query()] = None,
    test: Short | None = None,
    target: Short | None = None,
    q: Short | None = None,
    sort: Sort = "severity",
    order: Literal["asc", "desc"] = "desc",
    group_by: GroupBy | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> FindingList:
    """Findings, with the counts for the filters and, when asked, for a grouping. `q` looks in the
    title, the description, the target, the CWEs and the tests, and F-12 finds finding 12."""
    await find(session, pentest_id)
    where = _filters(
        pentest_id,
        view=view,
        statuses=status or [],
        severities=severity or [],
        test=test,
        target=target,
        q=q,
    )
    column = {
        "number": Finding.number,
        "severity": _RANK,
        "cvss": cast(_SCORE, Float),
        "updated": Finding.updated_at,
        "title": func.lower(Finding.title),
    }[sort]
    ordered = column.desc().nulls_last() if order == "desc" else column.asc().nulls_last()
    total = await session.scalar(select(func.count()).select_from(Finding).where(*where))
    rows = list(
        await session.scalars(
            select(Finding)
            .where(*where)
            .order_by(ordered, Finding.number.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return FindingList(
        items=await service.summaries(session, rows),
        total=total or 0,
        statuses=await _counts(session, Finding.status, pentest_id),
        severities=await _counts(session, Finding.severity, pentest_id),
        groups=await _groups(session, where, group_by),
    )


def _record(
    session: AsyncSession,
    request: Request,
    who: Admin,
    action: str,
    pentest_id: uuid.UUID,
    **detail: object,
) -> None:
    audit.record(
        session,
        request,
        f"finding.{action}",
        actor=who.user,
        target=("pentest", pentest_id),
        detail=detail,
    )


@router.post("/pentests/{pentest_id}/findings", status_code=201)
async def create_finding(
    pentest_id: uuid.UUID, body: FindingIn, request: Request, who: Admin, session: SessionDep
) -> FindingOut:
    """Write a finding by hand. The severity comes from the CVSS vector unless one is given."""
    pentest = await _editable(session, pentest_id)
    row = await service.create_finding(
        session, pentest.id, body, service.Origin(actor_id=who.user.id)
    )
    _record(session, request, who, "create", pentest.id, finding=str(row.id), number=row.number)
    return await service.detail_of(session, row)


@router.get("/pentests/{pentest_id}/findings/export")
async def export_findings(
    pentest_id: uuid.UUID,
    request: Request,
    who: SignedIn,
    session: SessionDep,
    *,
    format: Literal["json", "csv", "sarif"] = "json",  # noqa: A002  # the name the query has
    view: Literal["live", "trash"] = "live",
) -> Response:
    """Download the findings as JSON, CSV or SARIF. Sealed evidence goes out as a mask."""
    pentest = await find(session, pentest_id)
    rows = list(
        await session.scalars(
            select(Finding)
            .where(
                *_filters(
                    pentest.id,
                    view=view,
                    statuses=[],
                    severities=[],
                    test=None,
                    target=None,
                    q=None,
                )
            )
            .order_by(Finding.number)
        )
    )
    evidence: dict[uuid.UUID, list[FindingEvidence]] = {r.id: [] for r in rows}
    for one in await session.scalars(
        select(FindingEvidence)
        .where(FindingEvidence.finding_id.in_(list(evidence)))
        .order_by(FindingEvidence.created_at)
    ):
        evidence[one.finding_id].append(one)
    items = [exchange.finding_dict(r, evidence[r.id]) for r in rows]
    if format == "csv":
        content, kind = exchange.export_csv(items), "text/csv"
    elif format == "sarif":
        content = exchange.export_sarif(items, version=request.app.version)
        kind = "application/sarif+json"
    else:
        content, kind = exchange.export_json(items), "application/json"
    audit.record(
        session,
        request,
        "finding.export",
        actor=who.user,
        target=("pentest", pentest.id),
        detail={"format": format, "count": len(rows)},
    )
    extension = "sarif" if format == "sarif" else format
    return Response(
        content,
        media_type=kind,
        headers={
            "Content-Disposition": f'attachment; filename="findings-{pentest.id}.{extension}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/pentests/{pentest_id}/findings/import", status_code=201)
async def import_findings(
    pentest_id: uuid.UUID, body: ImportIn, request: Request, who: Admin, session: SessionDep
) -> ImportOut:
    """Add the findings of a Blindspot export or of a SARIF report. One that has the title and the
    target of a finding already here is skipped."""
    pentest = await _editable(session, pentest_id)
    items, unusable = exchange.read(body.format, body.content)
    known = {
        (r.title.casefold(), r.target.casefold())
        for r in await session.scalars(
            select(Finding).where(Finding.pentest_id == pentest.id, Finding.not_deleted())
        )
    }
    created = skipped = 0
    for item in items:
        key = (item.title.casefold(), item.target.casefold())
        if key in known:
            skipped += 1
            continue
        known.add(key)
        if not service.can_rate(item):
            skipped += 1
            continue
        await service.create_finding(
            session,
            pentest.id,
            item,
            service.Origin(source="import", actor_id=who.user.id, status=item.status),
        )
        created += 1
    _record(session, request, who, "import", pentest.id, format=body.format, created=created)
    return ImportOut(created=created, skipped=skipped + unusable)


@router.post("/pentests/{pentest_id}/findings/bulk")
async def bulk(
    pentest_id: uuid.UUID, body: BulkIn, request: Request, who: Admin, session: SessionDep
) -> BulkOut:
    """Change the status of, delete or restore up to 100 findings. A finding that cannot take the
    change (the workflow does not allow it, it is in the wrong place) is skipped, not an error."""
    pentest = await _editable(session, pentest_id)
    if body.action == "set_status" and body.status is None:
        raise AppError(422, "status_needed", "Say which status")
    rows = list(
        await session.scalars(
            select(Finding).where(Finding.pentest_id == pentest.id, Finding.id.in_(body.ids))
        )
    )
    changed = 0
    for row in rows:
        if body.action == "delete" and row.deleted_at is None:
            row.mark_deleted()
            service.add_event(session, row.id, "deleted", who.user.id)
        elif body.action == "restore" and row.deleted_at is not None and row.merged_into is None:
            row.restore()
            service.add_event(session, row.id, "restored", who.user.id)
        elif body.action == "set_status" and body.status and row.deleted_at is None:
            if body.status == row.status or body.status not in TRANSITIONS[row.status]:
                continue
            before = row.status
            service.move(row, body.status)
            service.add_event(
                session,
                row.id,
                "status",
                who.user.id,
                before=before,
                after=row.status,
                note=body.note,
            )
        else:
            continue
        changed += 1
    _record(
        session, request, who, f"bulk_{body.action}", pentest.id, count=changed, status=body.status
    )
    return BulkOut(changed=changed, skipped=len(body.ids) - changed)


@router.post("/pentests/{pentest_id}/results/{result_id}/promote", status_code=201)
async def promote_result(
    pentest_id: uuid.UUID,
    result_id: uuid.UUID,
    body: PromoteIn,
    request: Request,
    *,
    who: Admin,
    session: SessionDep,
) -> list[FindingSummary]:
    """Make findings from the issues in a result, each with the result as its evidence. An issue
    that was already promoted is not made twice."""
    pentest = await _editable(session, pentest_id)
    result = await session.get(PentestResult, result_id)
    parsed = tool_result_of(result) if result is not None else None
    if result is None or result.pentest_id != pentest.id:
        raise AppError(404, "result_not_found", "There is no such result")
    if parsed is None or not parsed.issues:
        raise AppError(422, "no_issues", "This result holds no issues to promote")
    chosen = (
        list(enumerate(parsed.issues))
        if body.issues is None
        else [(i, parsed.issues[i]) for i in dict.fromkeys(body.issues) if i < len(parsed.issues)]
    )
    if not chosen:
        raise AppError(422, "no_issues", "None of those issues is in this result")
    made = await service.promote(
        session, pentest.id, result, [issue for _, issue in chosen], who.user.id
    )
    _record(session, request, who, "promote", pentest.id, result=str(result.id), count=len(made))
    return await service.summaries(session, made)


@router.get("/pentests/{pentest_id}/findings/{finding_id}")
async def get_finding(
    pentest_id: uuid.UUID, finding_id: uuid.UUID, _who: SignedIn, session: SessionDep
) -> FindingOut:
    """One finding with its evidence, its timeline and the findings that look like it."""
    await find(session, pentest_id)
    return await service.detail_of(session, await _row(session, pentest_id, finding_id))


@router.patch("/pentests/{pentest_id}/findings/{finding_id}")
async def patch_finding(
    pentest_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: FindingPatch,
    request: Request,
    *,
    who: Admin,
    session: SessionDep,
) -> FindingOut:
    """Change what a finding says. A new CVSS vector re-rates it unless a severity is sent too."""
    pentest = await _editable(session, pentest_id)
    row = await _row(session, pentest.id, finding_id)
    _live(row)
    changed = service.apply_patch(row, body)
    if changed:
        service.add_event(session, row.id, "updated", who.user.id, fields=changed)
        _record(session, request, who, "update", pentest.id, finding=str(row.id), fields=changed)
    await session.flush()
    return await service.detail_of(session, row)


@router.delete("/pentests/{pentest_id}/findings/{finding_id}", status_code=204)
async def delete_finding(
    pentest_id: uuid.UUID, finding_id: uuid.UUID, request: Request, who: Admin, session: SessionDep
) -> Response:
    """Move a finding to the trash. Nothing is lost: restore brings it back."""
    pentest = await _editable(session, pentest_id)
    row = await _row(session, pentest.id, finding_id)
    _live(row)
    row.mark_deleted()
    service.add_event(session, row.id, "deleted", who.user.id)
    _record(session, request, who, "delete", pentest.id, finding=str(row.id))
    return Response(status_code=204)


@router.post("/pentests/{pentest_id}/findings/{finding_id}/restore")
async def restore_finding(
    pentest_id: uuid.UUID, finding_id: uuid.UUID, request: Request, who: Admin, session: SessionDep
) -> FindingOut:
    """Bring a finding back from the trash. One that was merged into another stays merged."""
    pentest = await _editable(session, pentest_id)
    row = await _row(session, pentest.id, finding_id)
    if row.deleted_at is None:
        raise AppError(409, "not_in_trash", "This finding is not in the trash")
    if row.merged_into is not None:
        raise AppError(409, "merged", "This finding was merged into another one")
    row.restore()
    service.add_event(session, row.id, "restored", who.user.id)
    _record(session, request, who, "restore", pentest.id, finding=str(row.id))
    await session.flush()
    return await service.detail_of(session, row)


@router.post("/pentests/{pentest_id}/findings/{finding_id}/status")
async def set_status(
    pentest_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: StatusIn,
    request: Request,
    *,
    who: Admin,
    session: SessionDep,
) -> FindingOut:
    """Move a finding along the workflow, with a note about why."""
    pentest = await _editable(session, pentest_id)
    row = await _row(session, pentest.id, finding_id)
    _live(row)
    before = row.status
    service.move(row, body.status)
    service.add_event(
        session, row.id, "status", who.user.id, before=before, after=row.status, note=body.note
    )
    _record(session, request, who, "status", pentest.id, finding=str(row.id), after=row.status)
    await session.flush()
    return await service.detail_of(session, row)


@router.post("/pentests/{pentest_id}/findings/{finding_id}/verification")
async def verify_finding(
    pentest_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: VerifyIn,
    request: Request,
    *,
    who: Admin,
    session: SessionDep,
) -> FindingOut:
    """A person says whether the finding is real. Confirming a new finding confirms its status
    too."""
    pentest = await _editable(session, pentest_id)
    row = await _row(session, pentest.id, finding_id)
    _live(row)
    row.verification = body.outcome
    row.verified_by = "manual"
    row.verified_at = utc_now()
    service.add_event(
        session, row.id, "verified", who.user.id, outcome=body.outcome, by="manual", note=body.note
    )
    if body.outcome == "confirmed" and row.status == "new":
        row.status = "confirmed"
        service.add_event(
            session, row.id, "status", who.user.id, before="new", after="confirmed", note=""
        )
    _record(session, request, who, "verify", pentest.id, finding=str(row.id), outcome=body.outcome)
    await session.flush()
    return await service.detail_of(session, row)


@router.post("/pentests/{pentest_id}/findings/{finding_id}/retest")
async def request_retest(
    pentest_id: uuid.UUID, finding_id: uuid.UUID, request: Request, who: Admin, session: SessionDep
) -> FindingOut:
    """Ask for the finding's test to be run again. The finding moves to "retest needed"; the
    agents page then runs just that test, after the usual confirmation."""
    pentest = await _editable(session, pentest_id)
    row = await _row(session, pentest.id, finding_id)
    _live(row)
    if not row.test_ids:
        raise AppError(
            409, "no_test", "This finding has no test to run again", "Add the test it came from."
        )
    before = row.status
    service.move(row, "retest_needed")
    service.add_event(
        session, row.id, "retest_requested", who.user.id, before=before, tests=list(row.test_ids)
    )
    _record(session, request, who, "retest", pentest.id, finding=str(row.id))
    await session.flush()
    return await service.detail_of(session, row)


@router.post("/pentests/{pentest_id}/findings/{finding_id}/comments", status_code=201)
async def comment(
    pentest_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: CommentIn,
    request: Request,
    *,
    who: Admin,
    session: SessionDep,
) -> FindingOut:
    """Write a comment on the finding's timeline."""
    pentest = await _editable(session, pentest_id)
    row = await _row(session, pentest.id, finding_id)
    _live(row)
    service.add_event(session, row.id, "comment", who.user.id, body=body.body)
    _record(session, request, who, "comment", pentest.id, finding=str(row.id))
    await session.flush()
    return await service.detail_of(session, row)


@router.post("/pentests/{pentest_id}/findings/{finding_id}/merge")
async def merge_finding(
    pentest_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: MergeIn,
    request: Request,
    *,
    who: Admin,
    session: SessionDep,
) -> FindingOut:
    """Fold this finding into another that it repeats. Returns the one that was kept."""
    pentest = await _editable(session, pentest_id)
    row = await _row(session, pentest.id, finding_id)
    keep = await _row(session, pentest.id, body.into)
    await service.merge_into(session, row, keep, who.user.id)
    _record(session, request, who, "merge", pentest.id, finding=str(row.id), into=str(keep.id))
    await session.flush()
    return await service.detail_of(session, keep)


@router.post("/pentests/{pentest_id}/findings/{finding_id}/evidence", status_code=201)
async def add_evidence(
    pentest_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: EvidenceIn,
    request: Request,
    *,
    who: Admin,
    session: SessionDep,
) -> FindingOut:
    """Add evidence: a result of the pentest, a request and its response, a note or a
    screenshot. Anything that looks like a secret is sealed unless `sealed` says otherwise."""
    pentest = await _editable(session, pentest_id)
    row = await _row(session, pentest.id, finding_id)
    _live(row)
    one = await service.add_evidence(session, row, body, who.user.id)
    _record(session, request, who, "evidence_add", pentest.id, finding=str(row.id), kind=one.kind)
    return await service.detail_of(session, row)


@router.patch("/pentests/{pentest_id}/findings/{finding_id}/evidence/{evidence_id}")
async def patch_evidence(
    pentest_id: uuid.UUID,
    finding_id: uuid.UUID,
    evidence_id: uuid.UUID,
    body: EvidencePatch,
    request: Request,
    *,
    who: Admin,
    session: SessionDep,
) -> FindingOut:
    """Rename a piece of evidence or seal or unseal it."""
    pentest = await _editable(session, pentest_id)
    row = await _row(session, pentest.id, finding_id)
    _live(row)
    one = await _evidence(session, row, evidence_id)
    if body.title is not None:
        one.title = body.title
    if body.sealed is not None:
        one.sealed = body.sealed
    _record(session, request, who, "evidence_update", pentest.id, evidence=str(one.id))
    await session.flush()
    return await service.detail_of(session, row)


@router.delete(
    "/pentests/{pentest_id}/findings/{finding_id}/evidence/{evidence_id}", status_code=204
)
async def delete_evidence(
    pentest_id: uuid.UUID,
    finding_id: uuid.UUID,
    evidence_id: uuid.UUID,
    request: Request,
    *,
    who: Admin,
    session: SessionDep,
) -> Response:
    """Take a piece of evidence off the finding. It is not kept anywhere else."""
    pentest = await _editable(session, pentest_id)
    row = await _row(session, pentest.id, finding_id)
    _live(row)
    one = await _evidence(session, row, evidence_id)
    service.add_event(session, row.id, "evidence_removed", who.user.id, title=one.title)
    await session.delete(one)
    _record(session, request, who, "evidence_delete", pentest.id, evidence=str(evidence_id))
    return Response(status_code=204)


@router.post("/pentests/{pentest_id}/findings/{finding_id}/evidence/{evidence_id}/reveal")
async def reveal_evidence(
    pentest_id: uuid.UUID,
    finding_id: uuid.UUID,
    evidence_id: uuid.UUID,
    request: Request,
    *,
    who: Admin,
    session: SessionDep,
) -> RevealOut:
    """Show sealed evidence as it was written (a screenshot as base64). Every reveal is in the
    audit trail, with who and which finding but never the content."""
    await find(session, pentest_id)
    row = await _row(session, pentest_id, finding_id)
    one = await _evidence(session, row, evidence_id)
    if one.body is None:
        raise AppError(404, "nothing_to_reveal", "This evidence has no text")
    _record(session, request, who, "evidence_reveal", pentest_id, evidence=str(one.id))
    return RevealOut(body=one.body)


@router.get("/pentests/{pentest_id}/findings/{finding_id}/evidence/{evidence_id}/image")
async def evidence_image(
    pentest_id: uuid.UUID,
    finding_id: uuid.UUID,
    evidence_id: uuid.UUID,
    _who: SignedIn,
    session: SessionDep,
) -> Response:
    """A screenshot that is not sealed, as the image."""
    await find(session, pentest_id)
    row = await _row(session, pentest_id, finding_id)
    one = await _evidence(session, row, evidence_id)
    if one.kind != "screenshot" or one.body is None or one.mime not in IMAGE_TYPES:
        raise AppError(404, "no_image", "This evidence is not an image")
    if one.sealed:
        raise AppError(
            403, "sealed", "This screenshot is sealed", "An administrator can reveal it."
        )
    return Response(
        base64.b64decode(one.body),
        media_type=one.mime,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )
