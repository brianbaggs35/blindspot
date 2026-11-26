"""Findings in and out of the app: JSON, CSV and SARIF 2.1.0.

Nothing secret leaves in an export. Evidence that is sealed goes out as the mask, the rest has
anything that looks like a secret taken out, and a screenshot goes out as its title only.
"""

import csv
import io
import json
import re
from collections.abc import Iterable
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.db.models import Finding, FindingEvidence
from app.errors import AppError
from app.findings.schemas import FindingIn, Status
from app.findings.service import category_of, shown_body
from app.tools.parsers.schema import Severity

MAX_IMPORTED = 1000
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_LEVEL = {"critical": "error", "high": "error", "medium": "warning", "low": "note"}
LEVEL_SEVERITY = {"error": "high", "warning": "medium", "note": "low", "none": "info"}
STATUSES = ("new", "confirmed", "false_positive", "accepted_risk", "fixed", "retest_needed")
CSV_COLUMNS = (
    "number",
    "title",
    "severity",
    "status",
    "confidence",
    "cvss4_score",
    "cvss4_vector",
    "cvss31_score",
    "cvss31_vector",
    "target",
    "tests",
    "category",
    "cwe",
    "owasp",
    "verification",
    "description",
    "remediation",
    "references",
    "evidence",
)
_FORMULA = ("=", "+", "-", "@", "\t", "\r")
_CWE = re.compile(r"cwe-(\d{1,5})", re.IGNORECASE)
_SLUG = re.compile(r"[^a-z0-9]+")
StringList = list[str]


def _evidence_of(rows: Iterable[FindingEvidence]) -> list[dict[str, object]]:
    return [
        {"kind": e.kind, "title": e.title, "sealed": e.sealed, "body": shown_body(e)} for e in rows
    ]


def finding_dict(row: Finding, evidence: Iterable[FindingEvidence]) -> dict[str, object]:
    return {
        "number": row.number,
        "title": row.title,
        "description": row.description,
        "target": row.target,
        "test_ids": list(row.test_ids),
        "cwe": list(row.cwe),
        "owasp": row.owasp,
        "cvss31_vector": row.cvss31_vector,
        "cvss31_score": float(row.cvss31_score) if row.cvss31_score is not None else None,
        "cvss4_vector": row.cvss4_vector,
        "cvss4_score": float(row.cvss4_score) if row.cvss4_score is not None else None,
        "severity": row.severity,
        "confidence": row.confidence,
        "status": row.status,
        "verification": row.verification,
        "remediation": row.remediation,
        "references": list(row.references),
        "evidence": _evidence_of(evidence),
    }


def export_json(items: list[dict[str, object]]) -> str:
    return json.dumps({"blindspot_findings": 1, "findings": items}, indent=2)


def _safe(value: object) -> str:
    """A cell a spreadsheet will not run as a formula."""
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_FORMULA) else text


def export_csv(items: list[dict[str, object]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for item in items:
        evidence = cast("list[dict[str, object]]", item["evidence"])
        row = dict(item) | {
            "tests": " ".join(cast(StringList, item["test_ids"])),
            "category": category_of(cast(StringList, item["test_ids"])),
            "cwe": " ".join(cast(StringList, item["cwe"])),
            "references": " ".join(cast(StringList, item["references"])),
            "evidence": "; ".join(f"{e['kind']}: {e['title']}" for e in evidence),
        }
        writer.writerow([_safe(row[name]) for name in CSV_COLUMNS])
    return out.getvalue()


def export_sarif(items: list[dict[str, object]], *, version: str) -> str:
    rules: dict[str, dict[str, object]] = {}
    results: list[dict[str, object]] = []
    for item in items:
        cwe = cast(StringList, item["cwe"])
        rule_id = cwe[0] if cwe else f"BLINDSPOT-{_SLUG.sub('-', str(item['title']).lower())[:40]}"
        rules.setdefault(
            rule_id,
            {"id": rule_id, "name": rule_id, "shortDescription": {"text": str(item["title"])}},
        )
        severity = str(item["severity"])
        result: dict[str, object] = {
            "ruleId": rule_id,
            "level": SARIF_LEVEL.get(severity, "none"),
            "message": {
                "text": str(item["title"])
                + (f"\n\n{item['description']}" if item["description"] else "")
            },
            "properties": {
                "severity": severity,
                "status": item["status"],
                "number": item["number"],
                "cvss4_score": item["cvss4_score"],
                "cvss31_score": item["cvss31_score"],
                "tests": item["test_ids"],
            },
        }
        if item["target"]:
            result["locations"] = [
                {"physicalLocation": {"artifactLocation": {"uri": str(item["target"])}}}
            ]
        results.append(result)
    document = {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Blindspot",
                        "version": version,
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(document, indent=2)


class Imported(FindingIn):
    """A finding read from a file: what `FindingIn` takes, and the status it had. Anything else in
    the file (its number, its evidence) is not read."""

    model_config = ConfigDict(extra="ignore")

    status: Status = "new"


def _unreadable(why: str) -> AppError:
    return AppError(422, "unreadable_import", why)


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class _Export(_Loose):
    findings: list[dict[str, Any]]


_FINDING_LIST = TypeAdapter(list[dict[str, Any]])


def _capped[T](items: list[T]) -> list[T]:
    if len(items) > MAX_IMPORTED:
        raise AppError(422, "too_many_to_import", f"A file may hold {MAX_IMPORTED} findings")
    return items


def _valid(objects: list[dict[str, Any]]) -> tuple[list[Imported], int]:
    good: list[Imported] = []
    bad = 0
    for one in _capped(objects):
        try:
            good.append(Imported.model_validate(one))
        except ValidationError:
            bad += 1
    return good, bad


def read_json(content: str) -> tuple[list[Imported], int]:
    """The findings of a Blindspot export (or a bare list of them), and how many were not usable."""
    try:
        listed = (
            _Export.model_validate_json(content).findings
            if content.lstrip().startswith("{")
            else _FINDING_LIST.validate_json(content)
        )
    except ValidationError:
        raise _unreadable("Expected a Blindspot export, or a list of findings") from None
    return _valid(listed)


class _Properties(_Loose):
    severity: str = ""
    security_severity: str | float = Field(default="", alias="security-severity")
    tags: list[str] = Field(default_factory=list[str])


class _Rule(_Loose):
    id: str = ""
    help_uri: str = Field(default="", alias="helpUri")
    properties: _Properties = Field(default_factory=_Properties)


class _Message(_Loose):
    text: str = ""


class _Artifact(_Loose):
    uri: str = ""


class _Physical(_Loose):
    artifact_location: _Artifact = Field(default_factory=_Artifact, alias="artifactLocation")


class _Location(_Loose):
    physical_location: _Physical = Field(default_factory=_Physical, alias="physicalLocation")


class _Result(_Loose):
    rule_id: str = Field(default="", alias="ruleId")
    level: str = "warning"
    message: _Message = Field(default_factory=_Message)
    locations: list[_Location] = Field(default_factory=list[_Location])
    properties: _Properties = Field(default_factory=_Properties)


class _Driver(_Loose):
    rules: list[_Rule] = Field(default_factory=list[_Rule])


class _Tool(_Loose):
    driver: _Driver = Field(default_factory=_Driver)


class _Run(_Loose):
    tool: _Tool = Field(default_factory=_Tool)
    results: list[_Result] = Field(default_factory=list[_Result])


class _Sarif(_Loose):
    runs: list[_Run]


def _severity_of(result: _Result, rule: _Rule) -> str:
    for properties in (result.properties, rule.properties):
        if properties.severity.lower() in Severity:
            return properties.severity.lower()
        try:
            number = float(properties.security_severity)
        except ValueError:
            continue
        bands = ((9.0, "critical"), (7.0, "high"), (4.0, "medium"), (0.1, "low"))
        return next((name for floor, name in bands if number >= floor), "info")
    return LEVEL_SEVERITY.get(result.level, "medium")


def read_sarif(content: str) -> tuple[list[Imported], int]:
    """The results of a SARIF 2.1.0 file (a scanner's report) as findings."""
    try:
        document = _Sarif.model_validate_json(content)
    except ValidationError:
        raise _unreadable("This is not a SARIF file") from None
    objects: list[dict[str, Any]] = []
    for run in document.runs:
        rules = {rule.id: rule for rule in run.tool.driver.rules}
        for result in run.results:
            rule = rules.get(result.rule_id, _Rule())
            text = result.message.text.strip()
            title = (text.splitlines()[0] if text else result.rule_id).strip()
            uri = (
                result.locations[0].physical_location.artifact_location.uri
                if result.locations
                else ""
            )
            tags = [*rule.properties.tags, result.rule_id]
            cwe = [f"CWE-{number}" for tag in tags for number in _CWE.findall(tag)]
            objects.append(
                {
                    "title": title[:200],
                    "description": text[:20_000],
                    "target": uri[:300],
                    "cwe": list(dict.fromkeys(cwe))[:5],
                    "severity": _severity_of(result, rule),
                    "references": [rule.help_uri]
                    if rule.help_uri.startswith(("http://", "https://"))
                    else [],
                }
            )
    return _valid(objects)


def read(format_: Literal["json", "sarif"], content: str) -> tuple[list[Imported], int]:
    return read_json(content) if format_ == "json" else read_sarif(content)
