"""The two doors of the engine: the brain that decides what to do next, and the executor that
runs a tool. Both are typed, so a model's answer is checked before the engine looks at it.

A model's answer has no place to say "this is allowed" or "skip the scope check": the engine asks
the scope guard and the permission policy about every request itself.
"""

from dataclasses import dataclass, field
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.tools.argv import Call
from app.tools.parsers.schema import Severity, ToolResult
from app.tools.registry import Tool

Confidence = Literal["low", "medium", "high"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolRequest(Strict):
    """The agent wants to run a tool."""

    kind: Literal["tool"] = "tool"
    tool: Annotated[str, Field(max_length=32)]
    values: dict[str, JsonValue] = Field(default_factory=dict)
    why: Annotated[str, Field(max_length=300)] = ""


class FactIn(Strict):
    """Something learned about the target, for the other agents to reuse."""

    subject: Annotated[str, Field(min_length=1, max_length=200)]
    fact: Annotated[str, Field(min_length=1, max_length=2000)]
    confidence: Confidence = "medium"


class FindingIn(Strict):
    """A weakness the agent claims. `evidence` lists the step numbers of this test that show it."""

    title: Annotated[str, Field(min_length=1, max_length=200)]
    severity: Severity
    detail: Annotated[str, Field(max_length=4000)] = ""
    evidence: list[Annotated[int, Field(ge=1, le=10_000)]] = Field(
        default_factory=list[int], max_length=20
    )
    confidence: Confidence = "medium"


class Finish(Strict):
    """The agent is done with its test."""

    kind: Literal["finish"] = "finish"
    status: Literal["passed", "finding", "blocked", "not_applicable"]
    summary: Annotated[str, Field(min_length=1, max_length=2000)]
    findings: list[FindingIn] = Field(default_factory=list[FindingIn], max_length=50)
    facts: list[FactIn] = Field(default_factory=list[FactIn], max_length=50)


Decision = Annotated[ToolRequest | Finish, Field(discriminator="kind")]


@dataclass(frozen=True)
class Spend:
    """What one model call used."""

    tokens: int = 0
    cost_usd: float = 0.0


@dataclass(frozen=True)
class Turn:
    decision: ToolRequest | Finish
    spend: Spend = field(default_factory=Spend)


@dataclass(frozen=True)
class Verification:
    confirmed: bool
    reason: str
    spend: Spend = field(default_factory=Spend)


@dataclass(frozen=True)
class HistoryItem:
    """One step as the agent sees it: the request, the verdict and a short account of the result."""

    seq: int
    tool: str
    status: str
    account: str


@dataclass(frozen=True)
class Brief:
    """What the test agent is told about its test."""

    test_id: str
    name: str
    risk_class: str
    objectives: list[str]
    instructions: str
    safe_steps: list[str]
    active_steps: list[str]
    intrusive_steps: list[str]
    evidence_wanted: list[str]
    success: str
    failure: str


@dataclass(frozen=True)
class Context:
    """Everything one decision is made from."""

    mission_id: str
    pentest_name: str
    box: str
    in_scope: list[str]
    max_risk: str
    brief: Brief
    tools: dict[str, str]  # the tools it may ask for, with what each is for
    history: list[HistoryItem]
    facts: list[str]
    steps_left: int


class Brain(Protocol):
    """Decides the next step of one test, and checks a finding."""

    async def decide(self, context: Context) -> Turn: ...

    async def verify(
        self, finding: FindingIn, original: list[HistoryItem], replay: list[HistoryItem]
    ) -> Verification: ...


@dataclass(frozen=True)
class Execution:
    """How a tool run ended."""

    result: ToolResult | None
    raw: str | None
    exit_code: int | None
    duration_ms: int
    error: str | None = None


class Executor(Protocol):
    """Runs one authorized call. It is only ever given a call the engine has checked."""

    async def run(self, tool: Tool, call: Call) -> Execution: ...
