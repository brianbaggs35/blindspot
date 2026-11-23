"""What the methodology routes return and accept."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.methodology.spec import RiskClass, Strict, Tag, Test, ToolId
from app.methodology.store import Origin, SpecDiff

UpdateSource = Literal["origin", "upstream"]


class MethodologyOut(BaseModel):
    """A methodology in the list."""

    id: str
    name: str
    source_url: str
    license: str
    origin: Origin
    enabled: bool
    version_number: int
    version_label: str
    content_hash: str
    categories: int
    tests: int
    authored_playbooks: int
    custom_playbooks: int
    manual_review_tests: int
    imported_at: datetime
    can_update_from_upstream: bool


class TestSummary(BaseModel):
    """One test in the outline. The playbook is read with the test."""

    __test__ = False

    id: str
    name: str
    reference: str | None
    risk_class: RiskClass
    tags: list[Tag]
    requires: list[Tag]
    tools: list[ToolId]
    manual_review: bool
    playbook_source: Literal["generated", "authored", "custom"]


class CategoryOut(BaseModel):
    id: str
    name: str
    reporting_label: str | None
    tests: list[TestSummary]


class MethodologyDetail(MethodologyOut):
    """A methodology with its categories and the outline of every test."""

    category_list: list[CategoryOut]


class TestDetail(BaseModel):
    """One test with its playbook."""

    __test__ = False

    methodology_id: str
    category_id: str
    category_name: str
    test: Test


class EnabledIn(Strict):
    enabled: bool


class VersionOut(BaseModel):
    number: int
    label: str
    content_hash: str
    source: str
    created_at: datetime
    tests: int


class UpdateCheck(BaseModel):
    """What applying an update would change. Nothing is applied by looking."""

    source: str
    current_hash: str
    candidate_hash: str
    candidate_label: str
    changed: bool
    diff: SpecDiff


class ApplyIn(Strict):
    """Apply the candidate the administrator was shown. The hash says which one that was."""

    source: UpdateSource = "origin"
    candidate_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class ReloadOut(BaseModel):
    """What reading the packs folder found."""

    added: list[str]
    updates_available: list[str]
    problems: dict[str, str]
