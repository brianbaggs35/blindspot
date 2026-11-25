"""What the findings routes take and give."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.methodology.spec import Strict
from app.tools.parsers.schema import Severity

MASK = "••••••••"
MAX_TEXT_EVIDENCE = 100_000
MAX_IMAGE = 2 * 1024 * 1024
MAX_IMAGE_BASE64 = MAX_IMAGE * 4 // 3 + 8
MAX_IMPORT = 8 * 1024 * 1024
MAX_PAGE = 200

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text = Annotated[str, StringConstraints(max_length=20_000)]
Target = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
TestRef = Annotated[str, StringConstraints(min_length=1, max_length=64)]
Cwe = Annotated[str, StringConstraints(pattern=r"^CWE-[1-9]\d{0,4}$")]
Reference = Annotated[str, StringConstraints(pattern=r"^https?://\S{1,490}$")]
Vector = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]

# OWASP Top 10:2021, the edition whose titles are fixed.
OWASP = {
    "A01:2021": "Broken Access Control",
    "A02:2021": "Cryptographic Failures",
    "A03:2021": "Injection",
    "A04:2021": "Insecure Design",
    "A05:2021": "Security Misconfiguration",
    "A06:2021": "Vulnerable and Outdated Components",
    "A07:2021": "Identification and Authentication Failures",
    "A08:2021": "Software and Data Integrity Failures",
    "A09:2021": "Security Logging and Monitoring Failures",
    "A10:2021": "Server-Side Request Forgery",
}
Owasp = Literal[
    "A01:2021",
    "A02:2021",
    "A03:2021",
    "A04:2021",
    "A05:2021",
    "A06:2021",
    "A07:2021",
    "A08:2021",
    "A09:2021",
    "A10:2021",
]

Status = Literal["new", "confirmed", "false_positive", "accepted_risk", "fixed", "retest_needed"]
Confidence = Literal["tentative", "firm", "certain"]
Source = Literal["manual", "agent", "result", "import"]
Verification = Literal["unverified", "confirmed", "unconfirmed"]
EvidenceKind = Literal["result", "request_response", "note", "screenshot"]
Sort = Literal["number", "severity", "cvss", "updated", "title"]
GroupBy = Literal["category", "target", "severity"]

# Where a finding may go next. A status that is not here is not a step the workflow allows.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "new": ("confirmed", "false_positive", "accepted_risk", "fixed"),
    "confirmed": ("fixed", "accepted_risk", "false_positive", "retest_needed"),
    "retest_needed": ("confirmed", "fixed", "false_positive", "accepted_risk"),
    "fixed": ("retest_needed", "confirmed"),
    "false_positive": ("new", "confirmed"),
    "accepted_risk": ("new", "confirmed", "fixed"),
}


class FindingIn(Strict):
    """A finding written by hand. Give a CVSS vector and the scores and the severity follow from
    it; give a severity yourself when there is no vector, or to overrule the vector's."""

    title: Title
    description: Text = ""
    target: Target = ""
    test_ids: list[TestRef] = Field(default_factory=list[str], max_length=10)
    cwe: list[Cwe] = Field(default_factory=list[str], max_length=5)
    owasp: Owasp | None = None
    cvss31_vector: Vector | None = None
    cvss4_vector: Vector | None = None
    severity: Severity | None = None
    confidence: Confidence = "firm"
    remediation: Text = ""
    references: list[Reference] = Field(default_factory=list[str], max_length=20)


class FindingPatch(Strict):
    """What may change on a finding. The status has its own request, so it has a history."""

    title: Title | None = None
    description: Text | None = None
    target: Target | None = None
    test_ids: list[TestRef] | None = Field(default=None, max_length=10)
    cwe: list[Cwe] | None = Field(default=None, max_length=5)
    owasp: Owasp | None = None
    cvss31_vector: Vector | None = None
    cvss4_vector: Vector | None = None
    severity: Severity | None = None
    confidence: Confidence | None = None
    remediation: Text | None = None
    references: list[Reference] | None = Field(default=None, max_length=20)


class StatusIn(Strict):
    status: Status
    note: Note = ""


class VerifyIn(Strict):
    outcome: Literal["confirmed", "unconfirmed"]
    note: Note = ""


class CommentIn(Strict):
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class MergeIn(Strict):
    into: uuid.UUID


class BulkIn(Strict):
    ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=100)]
    action: Literal["set_status", "delete", "restore"]
    status: Status | None = None
    note: Note = ""


class BulkOut(BaseModel):
    changed: int
    skipped: int


class EvidenceIn(Strict):
    """What shows the finding is real. `sealed` hides it in lists and exports; leave it out and
    evidence that looks like it holds a secret is sealed for you."""

    kind: EvidenceKind
    title: Title
    body: Annotated[str, StringConstraints(max_length=MAX_IMAGE_BASE64)] | None = None
    sealed: bool | None = None
    result_id: uuid.UUID | None = None
    mime: Literal["image/png", "image/jpeg", "image/webp"] | None = None


class EvidencePatch(Strict):
    title: Title | None = None
    sealed: bool | None = None


class PromoteIn(Strict):
    """Make findings from the issues a result holds: all of them, or the ones at these places."""

    issues: (
        Annotated[list[Annotated[int, Field(ge=0, le=10_000)]], Field(max_length=100)] | None
    ) = None


class ImportIn(Strict):
    format: Literal["json", "sarif"]
    content: Annotated[str, StringConstraints(min_length=2, max_length=MAX_IMPORT)]


class ImportOut(BaseModel):
    created: int
    skipped: int


class ScoreOut(BaseModel):
    vector: str
    version: Literal["3.1", "4.0"]
    score: Decimal
    severity: Severity


class EvidenceOut(BaseModel):
    id: uuid.UUID
    kind: EvidenceKind
    title: str
    body: str | None  # the text with anything secret-looking taken out, or the mask when sealed
    sealed: bool
    mime: str | None
    result_id: uuid.UUID | None
    result_title: str | None
    created_at: datetime


class EventOut(BaseModel):
    id: uuid.UUID
    kind: str
    actor: str | None
    data: dict[str, object]
    created_at: datetime


class DuplicateOut(BaseModel):
    id: uuid.UUID
    number: int
    title: str
    status: Status
    reason: str


class FindingSummary(BaseModel):
    id: uuid.UUID
    number: int
    title: str
    target: str
    category: str
    test_ids: list[str]
    severity: Severity
    confidence: Confidence
    status: Status
    cvss31_score: Decimal | None
    cvss4_score: Decimal | None
    verification: Verification
    source: Source
    evidence_count: int
    updated_at: datetime
    deleted: bool
    merged_into: uuid.UUID | None


class Group(BaseModel):
    key: str
    count: int


class FindingList(BaseModel):
    items: list[FindingSummary]
    total: int
    statuses: dict[str, int]
    severities: dict[str, int]
    groups: list[Group]


class FindingOut(FindingSummary):
    description: str
    cwe: list[str]
    owasp: str | None
    cvss31_vector: str | None
    cvss4_vector: str | None
    remediation: str
    references: list[str]
    result_id: uuid.UUID | None
    verified_by: str | None
    verified_at: datetime | None
    created_by: uuid.UUID | None
    created_at: datetime
    allowed_statuses: list[Status]
    evidence: list[EvidenceOut]
    timeline: list[EventOut]
    duplicates: list[DuplicateOut]


class RevealOut(BaseModel):
    body: str
