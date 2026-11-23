"""Keeping methodologies in the database: versioned snapshots, what changed between two of them,
and the playbooks an administrator replaced."""

import uuid
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Methodology, MethodologyVersion, PlaybookOverride
from app.methodology.spec import MethodologySpec, Playbook, Test

Origin = Literal["bundled", "folder"]

# What `diff` compares in a test. The playbook is compared as a whole.
_TEST_FIELDS = (
    "name",
    "reference",
    "objectives",
    "tags",
    "risk_class",
    "requires",
    "approach",
    "playbook",
)
_META_FIELDS = ("name", "version", "source_url", "license", "upstream_url")


class TestChange(BaseModel):
    """A test that is in both snapshots but differs."""

    __test__ = False

    id: str
    fields: list[str]


class SpecDiff(BaseModel):
    """What differs between the snapshot in use and another."""

    added: list[str] = []
    removed: list[str] = []
    changed: list[TestChange] = []
    categories_added: list[str] = []
    categories_removed: list[str] = []
    details_changed: list[str] = []

    @property
    def is_empty(self) -> bool:
        return not (
            self.added
            or self.removed
            or self.changed
            or self.categories_added
            or self.categories_removed
            or self.details_changed
        )


def diff_specs(old: MethodologySpec, new: MethodologySpec) -> SpecDiff:
    """Compare two snapshots, test by test."""
    before = {test.id: test for test in old.tests()}
    after = {test.id: test for test in new.tests()}
    changed: list[TestChange] = []
    for test_id in sorted(before.keys() & after.keys()):
        fields = _differing_fields(before[test_id], after[test_id])
        if fields:
            changed.append(TestChange(id=test_id, fields=fields))
    old_categories = {category.id for category in old.categories}
    new_categories = {category.id for category in new.categories}
    return SpecDiff(
        added=sorted(after.keys() - before.keys()),
        removed=sorted(before.keys() - after.keys()),
        changed=changed,
        categories_added=sorted(new_categories - old_categories),
        categories_removed=sorted(old_categories - new_categories),
        details_changed=[name for name in _META_FIELDS if getattr(old, name) != getattr(new, name)],
    )


def _differing_fields(old: Test, new: Test) -> list[str]:
    return [name for name in _TEST_FIELDS if getattr(old, name) != getattr(new, name)]


@dataclass
class Stored:
    """A methodology as stored: its row, its newest snapshot and its snapshot's content."""

    row: Methodology
    version: MethodologyVersion
    spec: MethodologySpec = field(init=False)

    def __post_init__(self) -> None:
        self.spec = MethodologySpec.model_validate(self.version.spec)


async def latest_version(session: AsyncSession, methodology_id: str) -> MethodologyVersion | None:
    """The newest snapshot, which is the one in use."""
    return await session.scalar(
        select(MethodologyVersion)
        .where(MethodologyVersion.methodology_id == methodology_id)
        .order_by(MethodologyVersion.number.desc())
        .limit(1)
    )


async def stored(session: AsyncSession, methodology_id: str) -> Stored | None:
    row = await session.get(Methodology, methodology_id)
    if row is None:
        return None
    version = await latest_version(session, methodology_id)
    return Stored(row, version) if version else None


async def add_snapshot(
    session: AsyncSession,
    spec: MethodologySpec,
    *,
    origin: Origin,
    source: str,
    user_id: uuid.UUID | None,
) -> MethodologyVersion:
    """Store a snapshot as the newest. The methodology's name, source and licence follow it."""
    row = await session.get(Methodology, spec.id)
    if row is None:
        row = Methodology(id=spec.id, origin=origin, enabled=True)
        session.add(row)
    row.name, row.source_url, row.license = spec.name, spec.source_url, spec.license
    top = await session.scalar(
        select(func.max(MethodologyVersion.number)).where(
            MethodologyVersion.methodology_id == spec.id
        )
    )
    version = MethodologyVersion(
        methodology_id=spec.id,
        number=(top or 0) + 1,
        label=spec.version,
        content_hash=spec.content_hash(),
        spec=spec.model_dump(mode="json"),
        source=source,
        created_by=user_id,
    )
    session.add(version)
    await session.flush()
    return version


async def add_missing(
    session: AsyncSession, specs: list[MethodologySpec], origin: Origin
) -> list[str]:
    """Store the methodologies that are not stored yet. One that is stored is left alone, even if
    this copy differs: a change is only ever applied by an administrator, after the diff."""
    added: list[str] = []
    for spec in specs:
        if await session.get(Methodology, spec.id) is None:
            await add_snapshot(session, spec, origin=origin, source=origin, user_id=None)
            added.append(spec.id)
    return added


async def overrides(session: AsyncSession, methodology_id: str) -> dict[str, Playbook]:
    rows = await session.scalars(
        select(PlaybookOverride).where(PlaybookOverride.methodology_id == methodology_id)
    )
    return {row.test_id: Playbook.model_validate(row.playbook) for row in rows}


def with_overrides(spec: MethodologySpec, changed: dict[str, Playbook]) -> MethodologySpec:
    """A copy of the methodology with the replaced playbooks in place."""
    merged = spec.model_copy(deep=True)
    for test in merged.tests():
        playbook = changed.get(test.id)
        if playbook is not None:
            test.playbook, test.playbook_source = playbook, "custom"
    return merged
