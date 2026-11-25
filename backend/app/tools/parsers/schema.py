"""One shape for what every tool finds, so the rest of the app never reads a tool's own format.

A parser turns a tool's raw output into a `ToolResult`. Agents, the results pages and the findings
code read only this. Every list is capped (`MAX_ITEMS`) and a result says when it was cut short, so
a tool that prints a million lines cannot fill the database or the screen.

Secrets found by a tool (a password it guessed, a key it found in a file) are `SecretStr`: they are
never printed, logged or dumped to JSON by accident, and are sealed in the vault when stored.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, SecretStr, StringConstraints

from app.methodology.spec import Strict

MAX_ITEMS = 5000
MAX_WARNINGS = 20

Short = Annotated[str, StringConstraints(max_length=300)]
Long = Annotated[str, StringConstraints(max_length=4000)]
Port = Annotated[int, Field(ge=0, le=65535)]


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Confidence(StrEnum):
    """How sure the tool, or the check, is that the issue is real."""

    TENTATIVE = "tentative"
    FIRM = "firm"
    CERTAIN = "certain"


class Service(Strict):
    port: Port
    protocol: Literal["tcp", "udp", "sctp"] = "tcp"
    state: Short = "open"
    name: Short | None = None
    product: Short | None = None
    version: Short | None = None
    tunnel: Short | None = None
    cpe: list[Short] = Field(default_factory=list[str], max_length=10)


class Host(Strict):
    address: Short
    hostnames: list[Short] = Field(default_factory=list[str], max_length=20)
    state: Literal["up", "down", "unknown"] = "unknown"
    services: list[Service] = Field(default_factory=list[Service], max_length=MAX_ITEMS)


class HttpResponse(Strict):
    url: Long
    status: int | None = Field(default=None, ge=100, le=599)
    length: int | None = Field(default=None, ge=0)
    words: int | None = Field(default=None, ge=0)
    lines: int | None = Field(default=None, ge=0)
    content_type: Short | None = None
    redirect: Long | None = None
    title: Short | None = None
    server: Short | None = None
    input: Short | None = None  # what was tried, for content discovery


class Technology(Strict):
    name: Short
    version: Short | None = None
    category: Short | None = None
    target: Short | None = None


class TlsFinding(Strict):
    id: Short
    severity: Severity
    finding: Long
    host: Short | None = None
    port: Port | None = None
    cve: list[Short] = Field(default_factory=list[str], max_length=20)


class Issue(Strict):
    title: Short
    severity: Severity
    confidence: Confidence = Confidence.TENTATIVE
    target: Long | None = None
    detail: Long | None = None
    reference: Short | None = None  # a template id, a rule id, a CVE
    evidence: Long | None = None
    tags: list[Short] = Field(default_factory=list[str], max_length=20)


class Credential(Strict):
    target: Short
    kind: Short = "password"
    username: Short | None = None
    secret: SecretStr


class Artifact(Strict):
    name: Short
    kind: Short = "file"
    size: int | None = Field(default=None, ge=0)
    ref: Short | None = None


class ToolResult(Strict):
    """What a tool found. Empty lists mean it found none of that kind, not that it was not asked."""

    tool: Short
    parser: Short
    hosts: list[Host] = Field(default_factory=list[Host], max_length=MAX_ITEMS)
    http: list[HttpResponse] = Field(default_factory=list[HttpResponse], max_length=MAX_ITEMS)
    technologies: list[Technology] = Field(default_factory=list[Technology], max_length=MAX_ITEMS)
    tls: list[TlsFinding] = Field(default_factory=list[TlsFinding], max_length=MAX_ITEMS)
    issues: list[Issue] = Field(default_factory=list[Issue], max_length=MAX_ITEMS)
    credentials: list[Credential] = Field(default_factory=list[Credential], max_length=MAX_ITEMS)
    artifacts: list[Artifact] = Field(default_factory=list[Artifact], max_length=MAX_ITEMS)
    raw_ref: Short | None = None
    truncated: bool = False
    warnings: list[Short] = Field(default_factory=list[str], max_length=MAX_WARNINGS)

    def is_empty(self) -> bool:
        """Whether the tool found nothing of any kind."""
        return (
            not any(
                (self.hosts, self.http, self.technologies, self.tls, self.issues, self.credentials)
            )
            and not self.artifacts
        )
