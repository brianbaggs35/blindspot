"""The shape of a methodology.

A methodology is data: categories of tests, and for each test a playbook that tells an agent what
to do. WSTG is imported into this shape; any other methodology is a folder of YAML files that
validates against it (`MethodologySpec.model_json_schema()` is the JSON Schema, written out in
`docs/methodologies.md`). Nothing outside this module and its siblings knows which methodology a
pentest uses.
"""

import hashlib
import json
import re
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MAX_CATEGORIES = 40
MAX_TESTS = 1000

MethodologyId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{1,31}$")]
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$")]
ToolId = Annotated[str, StringConstraints(pattern=r"^[a-z]\.[a-z0-9]{1,30}$")]
Tag = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,31}$")]
Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Url = Annotated[str, StringConstraints(pattern=r"^https://[^\s]{1,480}$")]
Version = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class Strict(BaseModel):
    """A document with no fields that are not in the schema, so a typo is an error, not a silent
    default."""

    model_config = ConfigDict(extra="forbid")


class RiskClass(StrEnum):
    """The most intrusive thing a test may do. Safe tests only observe; active ones send requests
    the application was not built to expect; intrusive ones can change data or disturb the
    service and always need approval."""

    SAFE = "safe"
    ACTIVE = "active"
    INTRUSIVE = "intrusive"


RISK_ORDER = (RiskClass.SAFE, RiskClass.ACTIVE, RiskClass.INTRUSIVE)


class Playbook(Strict):
    """What a test agent is told to do for one test, and what it must bring back."""

    summary: Line
    instructions: Body
    tools: list[ToolId] = Field(default_factory=list, max_length=20)
    manual_review: bool = False
    safe_steps: list[Line] = Field(default_factory=list, max_length=30)
    active_steps: list[Line] = Field(default_factory=list, max_length=30)
    intrusive_steps: list[Line] = Field(default_factory=list, max_length=30)
    evidence: list[Line] = Field(min_length=1, max_length=30)
    success: Text
    failure: Text
    not_applicable: list[Line] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def _has_a_way_to_run(self) -> Self:
        if not self.tools and not self.manual_review:
            raise ValueError("list the tools to use, or mark the test as manual review")
        return self


class Test(Strict):
    """One test in a category."""

    id: Identifier
    name: Title
    reference: Url | None = None
    objectives: list[Line] = Field(default_factory=list, max_length=30)
    tags: list[Tag] = Field(default_factory=list, max_length=20)
    risk_class: RiskClass = RiskClass.ACTIVE
    # What the target must show for the test to apply, such as "saml" or "upload". Empty means the
    # test always applies.
    requires: list[Tag] = Field(default_factory=list, max_length=20)
    approach: Line | None = None
    playbook: Playbook
    playbook_source: Literal["generated", "authored", "custom"] = "generated"


class Category(Strict):
    """A group of tests. Each category gets its own agent."""

    id: Identifier
    name: Title
    reporting_label: Title | None = None
    tests: list[Test] = Field(min_length=1, max_length=MAX_TESTS)


class MethodologySpec(Strict):
    """A whole methodology, ready to store."""

    id: MethodologyId
    name: Title
    version: Version
    source_url: Url
    license: Title
    upstream_url: Url | None = None
    categories: list[Category] = Field(min_length=1, max_length=MAX_CATEGORIES)

    @model_validator(mode="after")
    def _ids_are_unique_and_nested(self) -> Self:
        problem = structure_problem(
            [(category.id, [test.id for test in category.tests]) for category in self.categories]
        )
        if problem:
            raise ValueError(problem)
        return self

    def tests(self) -> list[Test]:
        """Every test, in order."""
        return [test for category in self.categories for test in category.tests]

    def find(self, test_id: str) -> tuple[Category, Test] | None:
        for category in self.categories:
            for test in category.tests:
                if test.id == test_id:
                    return category, test
        return None

    def content_hash(self) -> str:
        """A fingerprint of everything in the methodology. The same content always gives the same
        hash, so importing it again changes nothing."""
        return hash_of(self.model_dump(mode="json"))


def structure_problem(categories: list[tuple[str, list[str]]]) -> str | None:
    """What is wrong with the ids of a methodology, or None: every id must be used once and every
    test id must start with its category's id."""
    seen: set[str] = set()
    total = 0
    for category_id, test_ids in categories:
        if category_id in seen:
            return f"category {category_id} appears twice"
        seen.add(category_id)
        for test_id in test_ids:
            total += 1
            if not test_id.startswith(f"{category_id}-"):
                return f"test {test_id} does not belong to category {category_id}"
            if test_id in seen:
                return f"test {test_id} appears twice"
            seen.add(test_id)
    return f"a methodology has at most {MAX_TESTS} tests" if total > MAX_TESTS else None


def hash_of(document: object) -> str:
    """SHA-256 of a document written the same way every time."""
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


_SLUG = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    """A tag-shaped word from a title."""
    return _SLUG.sub("-", text.lower()).strip("-")[:32] or "other"
