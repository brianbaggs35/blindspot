"""Making, changing, scoring and reading findings. Routes call this and nothing else writes a
finding row, so the rules (the scores come from the vector, the status follows the workflow,
sealed evidence stays hidden) hold wherever a finding comes from: a person, an agent, a result or
an import."""

import base64
import binascii
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.db.models import Finding, FindingEvent, FindingEvidence, PentestResult, User
from app.errors import AppError
from app.findings import cvss
from app.findings.schemas import (
    MASK,
    MAX_IMAGE,
    TRANSITIONS,
    Confidence,
    DuplicateOut,
    EventOut,
    EvidenceIn,
    EvidenceOut,
    FindingIn,
    FindingOut,
    FindingPatch,
    FindingSummary,
    Source,
    Status,
    Verification,
)
from app.redact import redact
from app.tools.parsers.schema import Issue, Severity

MAX_FINDINGS_PER_PENTEST = 5000
MAX_EVIDENCE_PER_FINDING = 100
MAX_EVENTS_SHOWN = 300
SEVERITIES = (Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)
IMAGE_MAGIC = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    "image/webp": b"RIFF",
}


async def pairs[K, V](session: AsyncSession, statement: Select[K, V]) -> dict[K, V]:
    """What a query of two columns says, as a dictionary from the first to the second."""
    return dict((await session.execute(statement)).all())


def category_of(test_ids: list[str]) -> str:
    """The test category a finding belongs to: WSTG-CONF-06 is in CONF."""
    parts = test_ids[0].split("-") if test_ids else []
    return parts[1] if len(parts) >= 3 else "Other"  # PREFIX-CATEGORY-NN


@dataclass(frozen=True)
class Origin:
    """Where a finding came from, and what is known about it already."""

    source: Source = "manual"
    actor_id: uuid.UUID | None = None
    result_id: uuid.UUID | None = None
    verification: Verification = "unverified"
    verified_by: str | None = None
    status: Status = "new"


def severity_from(vector31: str | None, vector4: str | None) -> Severity | None:
    """The severity the vectors say: the CVSS 4.0 one when there is one."""
    try:
        scored = [cvss.score(v) for v in (vector4, vector31) if v]
    except cvss.VectorError as error:
        raise AppError(422, "bad_vector", str(error)) from None
    return Severity(scored[0].severity) if scored else None


def can_rate(data: FindingIn) -> bool:
    """Whether a finding can be made from this: its vectors are real and it has a severity."""
    try:
        derived = severity_from(data.cvss31_vector, data.cvss4_vector)
    except AppError:
        return False
    return data.severity is not None or derived is not None


def set_vectors(row: Finding, *, vector31: str | None, vector4: str | None) -> None:
    """Put the vectors on the row with the scores worked out from them. An empty vector clears."""
    for version, vector in (("3.1", vector31), ("4.0", vector4)):
        scored = None
        if vector:
            try:
                scored = cvss.score_v31(vector) if version == "3.1" else cvss.score_v4(vector)
            except cvss.VectorError as error:
                raise AppError(422, "bad_vector", str(error)) from None
        if version == "3.1":
            row.cvss31_vector, row.cvss31_score = (
                (scored.vector, scored.score) if scored else (None, None)
            )
        else:
            row.cvss4_vector, row.cvss4_score = (
                (scored.vector, scored.score) if scored else (None, None)
            )


def add_event(
    session: AsyncSession,
    finding_id: uuid.UUID,
    event: str,
    actor_id: uuid.UUID | None,
    **data: Any,
) -> None:
    session.add(FindingEvent(finding_id=finding_id, kind=event, actor_id=actor_id, data=data))


async def ensure_room(session: AsyncSession, pentest_id: uuid.UUID) -> None:
    count = await session.scalar(
        select(func.count()).select_from(Finding).where(Finding.pentest_id == pentest_id)
    )
    if (count or 0) >= MAX_FINDINGS_PER_PENTEST:
        raise AppError(
            409,
            "too_many_findings",
            f"A pentest keeps at most {MAX_FINDINGS_PER_PENTEST} findings",
            "Delete findings you no longer need.",
        )


async def next_number(session: AsyncSession, pentest_id: uuid.UUID) -> int:
    """The next F-number of the pentest. Two requests at once would take the same one, so the
    pentest's findings are numbered under a lock that lasts until the request commits."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"finding:{pentest_id}"},
    )
    highest = await session.scalar(
        select(func.max(Finding.number)).where(Finding.pentest_id == pentest_id)
    )
    return (highest or 0) + 1


async def create_finding(
    session: AsyncSession, pentest_id: uuid.UUID, data: FindingIn, origin: Origin = Origin()
) -> Finding:
    """Add a finding. The severity is the one given, else the one the CVSS vectors say."""
    await ensure_room(session, pentest_id)
    level = data.severity or severity_from(data.cvss31_vector, data.cvss4_vector)
    if level is None:
        raise AppError(
            422,
            "severity_needed",
            "Give a severity or a CVSS vector",
            "A finding needs one of them to be rated.",
        )
    row = Finding(
        pentest_id=pentest_id,
        number=await next_number(session, pentest_id),
        title=data.title,
        description=data.description,
        target=data.target,
        test_ids=list(dict.fromkeys(data.test_ids)),
        cwe=list(dict.fromkeys(data.cwe)),
        owasp=data.owasp,
        severity=level.value,
        confidence=data.confidence,
        status=origin.status,
        remediation=data.remediation,
        references=list(dict.fromkeys(data.references)),
        source=origin.source,
        result_id=origin.result_id,
        verification=origin.verification,
        verified_by=origin.verified_by,
        created_by=origin.actor_id,
    )
    set_vectors(row, vector31=data.cvss31_vector, vector4=data.cvss4_vector)
    if origin.verification != "unverified":
        row.verified_at = utc_now()
    session.add(row)
    await session.flush()
    add_event(session, row.id, "created", origin.actor_id, source=origin.source)
    return row


def apply_patch(row: Finding, body: FindingPatch) -> list[str]:
    """Change the fields that were sent. A new vector without a severity re-rates the finding.
    Returns the names of the fields that changed."""
    sent = body.model_fields_set
    changed: list[str] = []
    for name in ("title", "description", "target", "confidence", "remediation"):
        value = getattr(body, name)
        if name in sent and value is not None and value != getattr(row, name):
            setattr(row, name, value)
            changed.append(name)
    for name in ("test_ids", "cwe", "references"):
        value = getattr(body, name)
        if name in sent and value is not None and list(dict.fromkeys(value)) != getattr(row, name):
            setattr(row, name, list(dict.fromkeys(value)))
            changed.append(name)
    if "owasp" in sent and body.owasp != row.owasp:
        row.owasp = body.owasp
        changed.append("owasp")
    vectors_sent = {"cvss31_vector", "cvss4_vector"} & sent
    if vectors_sent:
        vector31 = body.cvss31_vector if "cvss31_vector" in sent else row.cvss31_vector
        vector4 = body.cvss4_vector if "cvss4_vector" in sent else row.cvss4_vector
        before = (row.cvss31_vector, row.cvss4_vector)
        set_vectors(row, vector31=vector31, vector4=vector4)
        if (row.cvss31_vector, row.cvss4_vector) != before:
            changed.extend(sorted(vectors_sent))
            if "severity" not in sent:
                derived = severity_from(row.cvss31_vector, row.cvss4_vector)
                if derived is not None and derived.value != row.severity:
                    row.severity = derived.value
                    changed.append("severity")
    if "severity" in sent and body.severity is not None and body.severity.value != row.severity:
        row.severity = body.severity.value
        changed.append("severity")
    return changed


def move(row: Finding, target: Status) -> None:
    """Move a finding along the status workflow, or say why it cannot go there."""
    if target == row.status:
        raise AppError(409, "same_status", "The finding already has this status")
    if target not in TRANSITIONS[row.status]:
        raise AppError(
            409,
            "bad_transition",
            f"A {row.status.replace('_', ' ')} finding cannot become {target.replace('_', ' ')}",
            "Pick one of the statuses the finding can move to.",
        )
    row.status = target


def looks_secret(body: str) -> bool:
    """Whether the redaction that guards the logs would change this text."""
    return redact(body) != body


def check_image(data: EvidenceIn) -> None:
    """A screenshot is base64 of a PNG, JPEG or WebP that is not too large and is what it says."""
    if data.body is None or data.mime is None:
        raise AppError(422, "image_needed", "A screenshot needs its image and its type")
    try:
        raw = base64.b64decode(data.body, validate=True)
    except binascii.Error, ValueError:
        raise AppError(422, "bad_image", "The image is not valid base64") from None
    if len(raw) > MAX_IMAGE:
        raise AppError(422, "image_too_large", "A screenshot may be 2 MB at most")
    if not raw.startswith(IMAGE_MAGIC[data.mime]) or (
        data.mime == "image/webp" and raw[8:12] != b"WEBP"
    ):
        raise AppError(422, "bad_image", "The file is not the kind of image it says")


async def add_evidence(
    session: AsyncSession, finding: Finding, data: EvidenceIn, actor_id: uuid.UUID | None
) -> FindingEvidence:
    count = await session.scalar(
        select(func.count())
        .select_from(FindingEvidence)
        .where(FindingEvidence.finding_id == finding.id)
    )
    if (count or 0) >= MAX_EVIDENCE_PER_FINDING:
        raise AppError(409, "too_much_evidence", "A finding keeps 100 pieces of evidence at most")
    body, mime, result_id, sealed = data.body, data.mime, data.result_id, data.sealed
    if data.kind == "result":
        found = await session.get(PentestResult, result_id) if result_id else None
        if found is None or found.pentest_id != finding.pentest_id:
            raise AppError(422, "result_not_found", "Pick a result of this pentest")
        body, mime = None, None
    else:
        result_id = None
        if data.kind == "screenshot":
            check_image(data)
        elif not body or len(body) > 100_000:
            raise AppError(422, "evidence_needed", "Write the evidence, up to 100,000 characters")
        else:
            mime = None
    if sealed is None:
        sealed = bool(body) and data.kind != "screenshot" and looks_secret(body)
    row = FindingEvidence(
        finding_id=finding.id,
        kind=data.kind,
        title=data.title,
        body=body,
        mime=mime,
        sealed=sealed,
        result_id=result_id,
        created_by=actor_id,
    )
    session.add(row)
    await session.flush()
    add_event(session, finding.id, "evidence_added", actor_id, kind=data.kind, title=data.title)
    return row


def shown_body(row: FindingEvidence) -> str | None:
    """What a list, a page or an export may show of the evidence: the text with anything that
    looks like a secret taken out, the mask when it is sealed, nothing for a screenshot."""
    if row.body is None or row.kind == "screenshot":
        return None
    return MASK if row.sealed else redact(row.body)


async def evidence_out(session: AsyncSession, rows: list[FindingEvidence]) -> list[EvidenceOut]:
    ids = {r.result_id for r in rows if r.result_id}
    titles = (
        await pairs(
            session, select(PentestResult.id, PentestResult.title).where(PentestResult.id.in_(ids))
        )
        if ids
        else {}
    )
    return [
        EvidenceOut(
            id=r.id,
            kind=r.kind,  # pyright: ignore[reportArgumentType]
            title=r.title,
            body=shown_body(r),
            sealed=r.sealed,
            mime=r.mime,
            result_id=r.result_id,
            result_title=titles.get(r.result_id) if r.result_id else None,
            created_at=r.created_at,
        )
        for r in rows
    ]


async def duplicates_of(session: AsyncSession, row: Finding) -> list[DuplicateOut]:
    """Other findings of the pentest that look like this one: the same title, or the same target
    and one of the same tests."""
    others = await session.scalars(
        select(Finding).where(
            Finding.pentest_id == row.pentest_id, Finding.id != row.id, Finding.not_deleted()
        )
    )
    found: list[DuplicateOut] = []
    for other in others:
        if other.title.casefold() == row.title.casefold():
            reason = "The same title"
        elif (
            row.target
            and other.target.casefold() == row.target.casefold()
            and set(other.test_ids) & set(row.test_ids)
        ):
            reason = "The same target and test"
        else:
            continue
        found.append(
            DuplicateOut(
                id=other.id,
                number=other.number,
                title=other.title,
                status=other.status,  # pyright: ignore[reportArgumentType]
                reason=reason,
            )
        )
    return sorted(found, key=lambda one: one.number)


async def merge_into(
    session: AsyncSession, row: Finding, keep: Finding, actor_id: uuid.UUID | None
) -> None:
    """Fold `row` into `keep`: its evidence, tests, CWEs and references move over, a note on the
    timeline of each says so, and `row` goes to the trash with a pointer to `keep`."""
    if row.id == keep.id or row.pentest_id != keep.pentest_id:
        raise AppError(422, "bad_merge", "Pick another finding of the same pentest")
    if keep.deleted_at is not None or row.deleted_at is not None:
        raise AppError(409, "in_trash", "A finding in the trash cannot be merged")
    for one in await session.scalars(
        select(FindingEvidence).where(FindingEvidence.finding_id == row.id)
    ):
        one.finding_id = keep.id
    for name in ("test_ids", "cwe", "references"):
        setattr(keep, name, list(dict.fromkeys([*getattr(keep, name), *getattr(row, name)])))
    if SEVERITIES.index(Severity(row.severity)) > SEVERITIES.index(Severity(keep.severity)):
        keep.severity = row.severity
    row.merged_into = keep.id
    row.mark_deleted()
    add_event(session, row.id, "merged_into", actor_id, number=keep.number, title=keep.title)
    add_event(session, keep.id, "merged_from", actor_id, number=row.number, title=row.title)


def summary_of(row: Finding, evidence_count: int) -> FindingSummary:
    return FindingSummary(
        id=row.id,
        number=row.number,
        title=row.title,
        target=row.target,
        category=category_of(list(row.test_ids)),
        test_ids=list(row.test_ids),
        severity=Severity(row.severity),
        confidence=row.confidence,  # pyright: ignore[reportArgumentType]
        status=row.status,  # pyright: ignore[reportArgumentType]
        cvss31_score=row.cvss31_score,
        cvss4_score=row.cvss4_score,
        verification=row.verification,  # pyright: ignore[reportArgumentType]
        source=row.source,  # pyright: ignore[reportArgumentType]
        evidence_count=evidence_count,
        updated_at=row.updated_at,
        deleted=row.deleted_at is not None,
        merged_into=row.merged_into,
    )


async def evidence_counts(session: AsyncSession, ids: list[uuid.UUID]) -> Counter[uuid.UUID]:
    if not ids:
        return Counter()
    return Counter(
        await pairs(
            session,
            select(FindingEvidence.finding_id, func.count())
            .where(FindingEvidence.finding_id.in_(ids))
            .group_by(FindingEvidence.finding_id),
        )
    )


async def summaries(session: AsyncSession, rows: list[Finding]) -> list[FindingSummary]:
    counts = await evidence_counts(session, [r.id for r in rows])
    return [summary_of(r, counts[r.id]) for r in rows]


async def timeline_of(session: AsyncSession, row: Finding) -> list[EventOut]:
    events = list(
        await session.scalars(
            select(FindingEvent)
            .where(FindingEvent.finding_id == row.id)
            .order_by(FindingEvent.created_at.desc(), FindingEvent.id.desc())
            .limit(MAX_EVENTS_SHOWN)
        )
    )
    actors = {e.actor_id for e in events if e.actor_id}
    names = (
        await pairs(session, select(User.id, User.display_name).where(User.id.in_(actors)))
        if actors
        else {}
    )
    return [
        EventOut(
            id=e.id,
            kind=e.kind,
            actor=names.get(e.actor_id) if e.actor_id else None,
            data=dict(e.data),
            created_at=e.created_at,
        )
        for e in events
    ]


async def detail_of(session: AsyncSession, row: Finding) -> FindingOut:
    evidence = list(
        await session.scalars(
            select(FindingEvidence)
            .where(FindingEvidence.finding_id == row.id)
            .order_by(FindingEvidence.created_at, FindingEvidence.id)
        )
    )
    head = summary_of(row, len(evidence))
    return FindingOut(
        **head.model_dump(),
        description=row.description,
        cwe=list(row.cwe),
        owasp=row.owasp,
        cvss31_vector=row.cvss31_vector,
        cvss4_vector=row.cvss4_vector,
        remediation=row.remediation,
        references=list(row.references),
        result_id=row.result_id,
        verified_by=row.verified_by,
        verified_at=row.verified_at,
        created_by=row.created_by,
        created_at=row.created_at,
        allowed_statuses=list(TRANSITIONS[row.status]),  # pyright: ignore[reportArgumentType]
        evidence=await evidence_out(session, evidence),
        timeline=await timeline_of(session, row),
        duplicates=await duplicates_of(session, row) if row.deleted_at is None else [],
    )


CONFIDENCE_WORDS: dict[str, Confidence] = {
    "low": "tentative",
    "medium": "firm",
    "high": "certain",
    "tentative": "tentative",
    "firm": "firm",
    "certain": "certain",
}


def confidence_of(value: object) -> Confidence:
    """A finding's confidence from what a tool or an agent said (low, medium and high, or
    tentative, firm and certain), or `firm` when it is none of those."""
    return CONFIDENCE_WORDS.get(str(value), "firm")


async def promote(
    session: AsyncSession,
    pentest_id: uuid.UUID,
    result: PentestResult,
    issues: list[Issue],
    actor_id: uuid.UUID | None,
) -> list[Finding]:
    """A finding for each issue of a result, with the result as evidence and, when the tool
    printed proof, a note. An issue that already has a finding from this result is left out."""
    taken = {
        (f.title.casefold(), f.target.casefold())
        for f in await session.scalars(
            select(Finding).where(Finding.result_id == result.id, Finding.not_deleted())
        )
    }
    made: list[Finding] = []
    for issue in issues:
        title, target = issue.title[:200], (issue.target or "")[:300]
        if (title.casefold(), target.casefold()) in taken:
            continue
        taken.add((title.casefold(), target.casefold()))
        link = issue.reference or ""
        data = FindingIn(
            title=title,
            description=issue.detail or "",
            target=target,
            test_ids=[result.test_id] if result.test_id else [],
            severity=issue.severity,
            confidence=confidence_of(issue.confidence.value),
            references=[link] if link.startswith(("http://", "https://")) else [],
        )
        row = await create_finding(
            session,
            pentest_id,
            data,
            Origin(source="result", actor_id=actor_id, result_id=result.id),
        )
        await add_evidence(
            session,
            row,
            EvidenceIn(kind="result", title=result.title, result_id=result.id),
            actor_id,
        )
        if issue.evidence:
            await add_evidence(
                session,
                row,
                EvidenceIn(kind="note", title="What the tool showed", body=issue.evidence),
                actor_id,
            )
        made.append(row)
    return made
