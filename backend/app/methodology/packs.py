"""Where methodologies come from: the one that ships with the app, the upstream WSTG checklist, and
packs that an administrator drops into `<data dir>/methodologies`.

A pack is a folder named after the methodology:

    methodology.yaml    id, name, version, source and license, categories and tests
    tools.yaml          which tools can do each test (or mark it manual review)
    playbooks/*.yaml    optional hand-written playbooks, by test id
    reporting.yaml      optional short names for the categories in reports
"""

import json
from datetime import date
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from app.methodology.build import (
    CategoryDraft,
    Draft,
    PackError,
    ReportingFile,
    TestDraft,
    ToolsFile,
    assemble,
    describe,
    parse,
)
from app.methodology.spec import MethodologySpec, Playbook, Tag, slug

BUNDLED = Path(__file__).parent / "bundled"
WSTG_UPSTREAM = "https://raw.githubusercontent.com/OWASP/wstg/master/checklists/checklist.json"
WSTG_SNAPSHOT_DATE = date(2026, 11, 23)
MAX_FILE_BYTES = 2_000_000
TOOLS_FILE = "tools.yaml"

# What the target must show for a WSTG test to apply. Tests not listed here always apply.
WSTG_REQUIRES: dict[str, list[Tag]] = {
    "WSTG-IDNT-02": ["registration"],
    "WSTG-IDNT-05": ["registration"],
    "WSTG-ATHN-11": ["saml"],
    "WSTG-ATHN-12": ["webauthn"],
    "WSTG-ATHN-13": ["oidc"],
    "WSTG-ATHZ-05": ["oauth"],
    "WSTG-SESS-10": ["jwt"],
    "WSTG-INJT-06": ["xml"],
    "WSTG-INJT-09": ["mail"],
    "WSTG-INJT-26": ["documents"],
    "WSTG-BUSL-08": ["upload"],
    "WSTG-BUSL-09": ["upload"],
    "WSTG-BUSL-10": ["payments"],
    "WSTG-CLNT-09": ["websocket"],
    "WSTG-CLNT-18": ["service-worker"],
    "WSTG-CLNT-20": ["sse"],
    "WSTG-APIT-09": ["webhooks"],
    "WSTG-APIT-10": ["grpc"],
    "WSTG-APIT-99": ["graphql"],
    "WSTG-WASM-01": ["wasm"],
    "WSTG-WASM-02": ["wasm"],
    "WSTG-WASM-03": ["wasm"],
}


class _Loose(BaseModel):
    """Upstream's own fields, read with everything we do not use ignored, so a new field there
    never breaks an import."""

    model_config = ConfigDict(extra="ignore")


class _UpstreamTest(_Loose):
    id: str
    name: str
    reference: str | None = None
    objectives: list[str] = []


class _UpstreamCategory(_Loose):
    id: str
    tests: list[_UpstreamTest]


class _UpstreamChecklist(_Loose):
    categories: dict[str, _UpstreamCategory]


def _read_yaml(path: Path) -> Any:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise PackError(f"{path.name} is larger than {MAX_FILE_BYTES // 1_000_000} MB")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError, UnicodeDecodeError:
        raise PackError(f"{path.name} is not valid YAML") from None


def _authored(documents: list[Any], label: str) -> dict[str, Playbook]:
    found: dict[str, Playbook] = {}
    for document in documents:
        if not isinstance(document, dict):
            raise PackError(f"{label} must map test ids to playbooks")
        for test_id, body in cast("dict[str, Any]", document).items():
            try:
                found[str(test_id)] = Playbook.model_validate(body)
            except ValidationError as error:
                raise PackError(
                    f"The playbook for {test_id} is not valid: {describe(error)}"
                ) from None
    return found


def _wstg_draft(upstream: _UpstreamChecklist, version: str) -> Draft:
    categories = [
        CategoryDraft(
            id=category.id,
            name=name,
            tests=[
                TestDraft(
                    id=test.id,
                    name=test.name,
                    reference=test.reference,
                    objectives=[goal.strip() for goal in test.objectives],
                    tags=[slug(name)],
                    requires=WSTG_REQUIRES.get(test.id, []),
                )
                for test in category.tests
            ],
        )
        for name, category in upstream.categories.items()
    ]
    return Draft(
        id="wstg",
        name="OWASP Web Security Testing Guide",
        version=version,
        source_url="https://owasp.org/www-project-web-security-testing-guide/",
        license="CC BY-SA 4.0",
        upstream_url=WSTG_UPSTREAM,
        categories=categories,
    )


def wstg_spec(checklist: bytes, *, version: str) -> MethodologySpec:
    """The WSTG methodology from an upstream `checklist.json`, with the bundled tool map and the
    hand-written playbooks."""
    try:
        upstream = parse(_UpstreamChecklist, json.loads(checklist), "The WSTG checklist")
    except ValueError, RecursionError:
        raise PackError("The WSTG checklist is not valid JSON") from None
    try:
        draft = _wstg_draft(upstream, version)
    except ValidationError as error:
        raise PackError(f"The WSTG checklist is not valid: {describe(error)}") from None
    folder = BUNDLED / "wstg"
    tools = parse(ToolsFile, _read_yaml(folder / TOOLS_FILE), "The WSTG tool map")
    authored = _authored([_read_yaml(folder / "playbooks.yaml")], "playbooks.yaml")
    return assemble(draft, tools, authored, strict=False)


def snapshot_version(day: date) -> str:
    return f"snapshot {day.isoformat()}"


def bundled() -> list[MethodologySpec]:
    """The methodologies that ship with the app."""
    checklist = (BUNDLED / "wstg" / "checklist.json").read_bytes()
    return [wstg_spec(checklist, version=snapshot_version(WSTG_SNAPSHOT_DATE))]


def load_pack(folder: Path) -> MethodologySpec:
    """One pack folder, validated, or a `PackError` saying what is wrong with it."""
    main = folder / "methodology.yaml"
    if not main.is_file():
        raise PackError("There is no methodology.yaml")
    draft = parse(Draft, _read_yaml(main), "methodology.yaml")
    if draft.id != folder.name:
        raise PackError(f"The folder is called {folder.name} but the methodology id is {draft.id}")
    tools_path = folder / TOOLS_FILE
    if not tools_path.is_file():
        raise PackError("There is no tools.yaml: every test needs its tools, or manual review")
    tools = parse(ToolsFile, _read_yaml(tools_path), TOOLS_FILE)
    playbooks = sorted((folder / "playbooks").glob("*.yaml"))
    authored = _authored([_read_yaml(path) for path in playbooks], "A playbook file")
    reporting_path = folder / "reporting.yaml"
    reporting = (
        parse(ReportingFile, _read_yaml(reporting_path), "reporting.yaml")
        if reporting_path.is_file()
        else None
    )
    spec = assemble(draft, tools, authored, reporting)
    # A pack has to say what each test is run with. A test left out of tools.yaml would quietly
    # become manual review, which is not what a pack author meant by leaving it out.
    missing = sorted(test.id for test in spec.tests() if test.id not in tools.tests)
    if missing:
        raise PackError(f"tools.yaml has no entry for: {', '.join(missing)}")
    return spec


def load_packs(root: Path) -> tuple[list[MethodologySpec], dict[str, str]]:
    """Every pack under `root`, and the reason each broken one was skipped. A missing folder means
    there are no packs."""
    specs: list[MethodologySpec] = []
    problems: dict[str, str] = {}
    if not root.is_dir():
        return specs, problems
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        try:
            specs.append(load_pack(folder))
        except PackError as error:
            problems[folder.name] = str(error)
    return specs, problems
