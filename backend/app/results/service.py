"""Storing results and reading them back. The runner and the import route both call
`record_result`; nothing else makes a result row."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PentestResult
from app.errors import AppError
from app.results.friendly import friendly
from app.results.schemas import (
    MASK,
    MAX_RAW_SHOWN,
    CredentialOut,
    RawOut,
    ResultOut,
    ResultSummary,
)
from app.tools.parsers import ToolResult
from app.tools.parsers.schema import Severity
from app.tools.parsers.summary import summarize

MAX_RESULTS_PER_PENTEST = 5000
_SEVERITIES = (Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)


def worst(result: ToolResult) -> Severity | None:
    """The most serious thing in a result: an issue, or a TLS finding that is more than a note."""
    levels = [i.severity for i in result.issues] + [
        t.severity for t in result.tls if t.severity is not Severity.INFO
    ]
    return max(levels, key=_SEVERITIES.index) if levels else None


async def ensure_room(session: AsyncSession, pentest_id: uuid.UUID) -> None:
    count = await session.scalar(
        select(func.count())
        .select_from(PentestResult)
        .where(PentestResult.pentest_id == pentest_id)
    )
    if (count or 0) >= MAX_RESULTS_PER_PENTEST:
        raise AppError(
            409,
            "too_many_results",
            f"A pentest keeps at most {MAX_RESULTS_PER_PENTEST} results",
            "Delete results you no longer need.",
        )


@dataclass(frozen=True)
class Run:
    """How a result came about, when a tool ran: who asked, for which test, and what happened."""

    tool_id: str | None = None
    agent_role: str | None = None
    test_id: str | None = None
    command: list[str] = field(default_factory=list[str])
    exit_code: int | None = None
    duration_ms: int | None = None
    ran_at: datetime | None = None


def record_result(  # noqa: PLR0913  # one row, every field of it
    session: AsyncSession,
    pentest_id: uuid.UUID,
    *,
    source: str,
    title: str,
    status: str = "ok",
    result: ToolResult | None = None,
    raw: str | None = None,
    run: Run = Run(),  # frozen, so one shared default is safe
    notes: str = "",
    tags: list[str] | None = None,
    severity: Severity | None = None,
    created_by: uuid.UUID | None = None,
) -> PentestResult:
    """Add a result. Any secret in `result` is taken out of the normalized copy and sealed on its
    own; the raw output is sealed too."""
    credentials = (
        [
            {
                "target": c.target,
                "kind": c.kind,
                "username": c.username,
                "secret": c.secret.get_secret_value(),
            }
            for c in result.credentials
        ]
        if result
        else []
    )
    level = worst(result) if result else severity
    row = PentestResult(
        pentest_id=pentest_id,
        source=source,
        status=status,
        title=title[:200],
        tool_id=run.tool_id,
        agent_role=run.agent_role,
        test_id=run.test_id,
        parser=result.parser if result else None,
        command=list(run.command),
        exit_code=run.exit_code,
        duration_ms=run.duration_ms,
        normalized=result.model_dump(mode="json", exclude={"credentials"}) if result else None,
        top_severity=level.value if level else None,
        issue_count=len(result.issues) if result else 0,
        raw_output=raw,
        credentials=credentials or None,
        notes=notes,
        tags=sorted(set(tags or [])),
        created_by=created_by,
    )
    if run.ran_at is not None:
        row.ran_at = run.ran_at
    session.add(row)
    return row


def tool_result_of(row: PentestResult) -> ToolResult | None:
    return ToolResult.model_validate(row.normalized) if row.normalized is not None else None


def summary_of(row: PentestResult) -> ResultSummary:
    result = tool_result_of(row)
    return ResultSummary(
        id=row.id,
        title=row.title,
        source=row.source,  # pyright: ignore[reportArgumentType]
        status=row.status,  # pyright: ignore[reportArgumentType]
        tool_id=row.tool_id,
        agent_role=row.agent_role,
        test_id=row.test_id,
        top_severity=Severity(row.top_severity) if row.top_severity else None,
        issue_count=row.issue_count,
        ran_at=row.ran_at,
        tags=list(row.tags),
        deleted=row.deleted_at is not None,
        summary=summarize(result)[:2] if result else [],
    )


def credentials_of(row: PentestResult) -> list[dict[str, Any]]:
    return list(row.credentials or [])


def detail_of(row: PentestResult) -> ResultOut:
    result = tool_result_of(row)
    head = summary_of(row)
    return ResultOut(
        **head.model_dump(),
        parser=row.parser,
        command=list(row.command),
        exit_code=row.exit_code,
        duration_ms=row.duration_ms,
        notes=row.notes,
        friendly=friendly(result) if result else None,
        technical=result.model_dump(mode="json", exclude={"credentials"}) if result else None,
        credentials=[
            CredentialOut(
                index=index,
                target=c["target"],
                kind=c["kind"],
                username=c.get("username"),
                secret=MASK,
            )
            for index, c in enumerate(credentials_of(row))
        ],
        has_raw=row.raw_output is not None,
        created_by=row.created_by,
    )


def raw_of(row: PentestResult) -> RawOut:
    text = row.raw_output or ""
    shown = text[:MAX_RAW_SHOWN]
    return RawOut(
        command=list(row.command),
        exit_code=row.exit_code,
        duration_ms=row.duration_ms,
        output=shown,
        truncated=len(shown) < len(text),
        size=len(text),
    )
