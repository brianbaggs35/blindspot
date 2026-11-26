"""Findings an agent made: each one a test agent claimed, with what the verifier said about it.

A claim that is already a finding of the pentest (the same title for the same test) is not made
twice: the finding is marked as seen again, and one that was fixed or waiting for a retest is
confirmed again when the verifier replayed it."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.ports import FindingIn as Claim
from app.db.models import Finding, MissionStep
from app.findings.schemas import EvidenceIn, FindingIn, Verification
from app.findings.service import (
    Origin,
    add_event,
    add_evidence,
    confidence_of,
    create_finding,
)


def _mark_seen(session: AsyncSession, known: Finding, verdict: Verification) -> None:
    add_event(session, known.id, "seen_again", None, verification=verdict)
    if verdict == "confirmed" and known.status in ("fixed", "retest_needed"):
        add_event(
            session,
            known.id,
            "status",
            None,
            before=known.status,
            after="confirmed",
            note="",
        )
        known.status = "confirmed"


async def record(
    session: AsyncSession,
    *,
    pentest_id: uuid.UUID,
    task_id: uuid.UUID,
    test_ref: str,
    claims: Sequence[tuple[Claim, Verification]],
) -> list[Finding]:
    """Make findings of an agent's claims. Returns the new ones."""
    seqs = {n for claim, _ in claims for n in claim.evidence}
    steps = {
        one.seq: one
        for one in await session.scalars(
            select(MissionStep).where(MissionStep.task_id == task_id, MissionStep.seq.in_(seqs))
        )
    }
    made: list[Finding] = []
    for claim, verdict in claims:
        known = await session.scalar(
            select(Finding).where(
                Finding.pentest_id == pentest_id,
                Finding.not_deleted(),
                Finding.title == claim.title,
                Finding.test_ids.contains([test_ref]),
            )
        )
        if known is not None:
            _mark_seen(session, known, verdict)
            continue
        cited = [steps[n] for n in dict.fromkeys(claim.evidence) if n in steps]
        row = await create_finding(
            session,
            pentest_id,
            FindingIn(
                title=claim.title,
                description=claim.detail,
                test_ids=[test_ref],
                severity=claim.severity,
                confidence=confidence_of(claim.confidence),
            ),
            Origin(
                source="agent",
                result_id=next((one.result_id for one in cited if one.result_id), None),
                verification=verdict,
                verified_by="agent" if verdict != "unverified" else None,
                status="confirmed" if verdict == "confirmed" else "new",
            ),
        )
        for one in cited:
            if one.result_id:
                await add_evidence(
                    session,
                    row,
                    EvidenceIn(
                        kind="result", title=f"Step {one.seq}: {one.tool}", result_id=one.result_id
                    ),
                    None,
                )
        made.append(row)
    return made
