"""What the permission policy reads from the database: the kill switch and the grants."""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSetting, ToolGrant
from app.tools.manifest import ToolRisk
from app.tools.policy import ApprovalMode, Grant

KILL_SWITCH_KEY = "tools.kill_switch"


async def kill_switch_on(session: AsyncSession) -> bool:
    """Whether an administrator has switched every tool off. Anything but an explicit `false`
    counts as on, so a damaged value stops the tools instead of freeing them."""
    row = await session.get(AppSetting, KILL_SWITCH_KEY)
    return False if row is None else row.value is not False


async def set_kill_switch(session: AsyncSession, *, on: bool) -> None:
    """Switch every tool off, or back on."""
    await session.execute(
        insert(AppSetting)
        .values(key=KILL_SWITCH_KEY, value=on)
        .on_conflict_do_update(index_elements=["key"], set_={"value": on})
    )


def to_grant(row: ToolGrant) -> Grant:
    """A stored rule as the policy reads it."""
    return Grant(
        role=row.role,
        tool=row.tool,
        max_risk=ToolRisk(row.max_risk),
        mode=ApprovalMode(row.mode),
        pentest_id=row.pentest_id,
    )


async def load_grants(session: AsyncSession, pentest_id: uuid.UUID | None = None) -> list[Grant]:
    """Every rule, or only those for every pentest and for this one."""
    query = select(ToolGrant).order_by(ToolGrant.created_at)
    if pentest_id is not None:
        query = query.where((ToolGrant.pentest_id.is_(None)) | (ToolGrant.pentest_id == pentest_id))
    return [to_grant(row) for row in (await session.scalars(query)).all()]
