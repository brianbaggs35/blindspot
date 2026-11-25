"""What the results routes take and give."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.methodology.spec import Strict, ToolId
from app.results.friendly import Friendly
from app.tools.parsers.schema import Severity

MASK = "••••••••"
MAX_RAW_SHOWN = 2 * 1024 * 1024
MAX_IMPORT = 8 * 1024 * 1024

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Notes = Annotated[str, StringConstraints(max_length=8000)]
Tag = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9 _-]{0,31}$")]
TestRef = Annotated[str, StringConstraints(min_length=1, max_length=64)]
Tags = Annotated[list[Tag], Field(max_length=20)]

Source = Literal["tool", "import", "manual"]
Status = Literal["ok", "failed", "manual"]


class ManualIn(Strict):
    """A note a person writes into the record: what they saw, tried or found by hand."""

    title: Title
    notes: Notes = ""
    tags: Tags = Field(default_factory=list[str])
    test_id: TestRef | None = None
    severity: Severity | None = None


class ImportIn(Strict):
    """Output pasted or uploaded from a tool that ran elsewhere. It is parsed like a run's."""

    parser: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
    content: Annotated[str, StringConstraints(min_length=1, max_length=MAX_IMPORT)]
    title: Title | None = None
    tool_id: ToolId | None = None
    notes: Notes = ""
    tags: Tags = Field(default_factory=list[str])
    test_id: TestRef | None = None


class PatchIn(Strict):
    """What a person may change on a result: never the output itself, only the annotations."""

    title: Title | None = None
    notes: Notes | None = None
    tags: Tags | None = None
    test_id: TestRef | None = None


class BulkIn(Strict):
    ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=100)]
    action: Literal["delete", "restore", "tag", "untag"]
    tag: Tag | None = None


class BulkOut(BaseModel):
    changed: int


class ResultSummary(BaseModel):
    id: uuid.UUID
    title: str
    source: Source
    status: Status
    tool_id: str | None
    agent_role: str | None
    test_id: str | None
    top_severity: Severity | None
    issue_count: int
    ran_at: datetime
    tags: list[str]
    deleted: bool
    summary: list[str]


class ResultList(BaseModel):
    items: list[ResultSummary]
    total: int
    tools: list[str]
    agents: list[str]


class CredentialOut(BaseModel):
    index: int
    target: str
    kind: str
    username: str | None
    secret: str = MASK


class RevealOut(BaseModel):
    secret: str


class ResultOut(ResultSummary):
    parser: str | None
    command: list[str]
    exit_code: int | None
    duration_ms: int | None
    notes: str
    friendly: Friendly | None
    technical: dict[str, object] | None
    credentials: list[CredentialOut]
    has_raw: bool
    created_by: uuid.UUID | None


class RawOut(BaseModel):
    command: list[str]
    exit_code: int | None
    duration_ms: int | None
    output: str
    truncated: bool
    size: int
