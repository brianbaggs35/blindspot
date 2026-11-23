"""Putting a methodology together from its parts.

Every methodology, WSTG included, reaches `assemble` as the same four pieces: the list of
categories and tests (the draft), which tools can do each test, any playbooks somebody wrote by
hand, and how the categories read in reports. That is what lets a new methodology be added with
files alone.
"""

from pydantic import BaseModel, Field, ValidationError

from app.methodology.defaults import generated_playbook
from app.methodology.spec import (
    RISK_ORDER,
    Category,
    Identifier,
    Line,
    MethodologyId,
    MethodologySpec,
    Playbook,
    RiskClass,
    Strict,
    Tag,
    Test,
    Title,
    ToolId,
    Url,
    Version,
    structure_problem,
)


class PackError(Exception):
    """A methodology could not be read. The message says what is wrong in plain words."""


def describe(error: ValidationError) -> str:
    """The first few problems in a document, each with where it is."""
    parts: list[str] = []
    for problem in error.errors()[:5]:
        where = ".".join(str(step) for step in problem["loc"]) or "the document"
        parts.append(f"{where}: {problem['msg']}")
    return "; ".join(parts)


class ToolEntry(Strict):
    """Which tools can do one test."""

    tools: list[ToolId] = Field(default_factory=list)
    risk: RiskClass = RiskClass.ACTIVE
    manual_review: bool = False
    approach: Line | None = None


class ToolsFile(Strict):
    """`tools.yaml`: the test-to-tool map."""

    tests: dict[Identifier, ToolEntry]


class TestDraft(Strict):
    """A test before it has a playbook."""

    id: Identifier
    name: Title
    reference: Url | None = None
    objectives: list[Line] = Field(default_factory=list)
    tags: list[Tag] = Field(default_factory=list)
    risk_class: RiskClass | None = None
    requires: list[Tag] = Field(default_factory=list)


class CategoryDraft(Strict):
    id: Identifier
    name: Title
    tests: list[TestDraft]


class Draft(Strict):
    """`methodology.yaml`."""

    id: MethodologyId
    name: Title
    version: Version
    source_url: Url
    license: Title
    upstream_url: Url | None = None
    categories: list[CategoryDraft]


class ReportingFile(Strict):
    """`reporting.yaml`: the short name of each category in reports and charts."""

    categories: dict[Identifier, Title]


def _check_known(label: str, ids: set[str], known: set[str], *, strict: bool) -> None:
    unknown = sorted(ids - known)
    if unknown and strict:
        raise PackError(
            f"{label} names tests that are not in the methodology: {', '.join(unknown)}"
        )


def assemble(
    draft: Draft,
    tools: ToolsFile,
    authored: dict[str, Playbook],
    reporting: ReportingFile | None = None,
    *,
    strict: bool = True,
) -> MethodologySpec:
    """The finished methodology, or a `PackError` that says what is wrong. With `strict`, a name in
    `tools`, `authored` or `reporting` that the draft does not have is an error (a typo in a pack).
    An import from upstream passes `strict=False`, because upstream may drop a test the map
    still lists."""
    try:
        return _assemble(draft, tools, authored, reporting, strict=strict)
    except ValidationError as error:
        raise PackError(f"The methodology is not valid: {describe(error)}") from None


def _risk_of_steps(playbook: Playbook) -> RiskClass:
    """The highest class of step a playbook lists."""
    if playbook.intrusive_steps:
        return RiskClass.INTRUSIVE
    return RiskClass.ACTIVE if playbook.active_steps else RiskClass.SAFE


def _at_least(risk: RiskClass, floor: RiskClass) -> RiskClass:
    return max(risk, floor, key=RISK_ORDER.index)


def _assemble(
    draft: Draft,
    tools: ToolsFile,
    authored: dict[str, Playbook],
    reporting: ReportingFile | None = None,
    *,
    strict: bool,
) -> MethodologySpec:
    problem = structure_problem(
        [(category.id, [test.id for test in category.tests]) for category in draft.categories]
    )
    if problem:
        raise PackError(f"The methodology is not valid: {problem}")
    known = {test.id for category in draft.categories for test in category.tests}
    _check_known("tools.yaml", set(tools.tests), known, strict=strict)
    _check_known("The playbooks", set(authored), known, strict=strict)
    labels = reporting.categories if reporting else {}
    _check_known("reporting.yaml", set(labels), {c.id for c in draft.categories}, strict=strict)
    categories: list[Category] = []
    for category in draft.categories:
        tests: list[Test] = []
        for test in category.tests:
            entry = tools.tests.get(test.id)
            # A test nobody mapped to a tool is judgement work until somebody does.
            manual = True if entry is None else entry.manual_review or not entry.tools
            risk = test.risk_class or (entry.risk if entry else RiskClass.ACTIVE)
            playbook = authored.get(test.id)
            if playbook is not None:
                risk = _at_least(risk, _risk_of_steps(playbook))
            else:
                playbook = generated_playbook(
                    category_id=category.id,
                    test_name=test.name,
                    objectives=test.objectives,
                    tools=entry.tools if entry else [],
                    manual_review=manual,
                    risk_class=risk,
                    approach=entry.approach if entry else None,
                )
            tests.append(
                Test(
                    id=test.id,
                    name=test.name,
                    reference=test.reference,
                    objectives=test.objectives,
                    tags=test.tags,
                    risk_class=risk,
                    requires=test.requires,
                    approach=entry.approach if entry else None,
                    playbook=playbook,
                    playbook_source="authored" if test.id in authored else "generated",
                )
            )
        categories.append(
            Category(
                id=category.id,
                name=category.name,
                reporting_label=labels.get(category.id),
                tests=tests,
            )
        )
    return MethodologySpec(
        id=draft.id,
        name=draft.name,
        version=draft.version,
        source_url=draft.source_url,
        license=draft.license,
        upstream_url=draft.upstream_url,
        categories=categories,
    )


def parse[T: BaseModel](model: type[T], document: object, label: str) -> T:
    """Read a document into a model, or say what is wrong with it."""
    try:
        return model.model_validate(document)
    except ValidationError as error:
        raise PackError(f"{label} is not valid: {describe(error)}") from None
