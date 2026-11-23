"""Spec rules, the diff between two snapshots and the pieces the store builds on."""

import copy
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError
from tests.methodology_helpers import PLAYBOOK

from app.methodology.build import Draft, PackError, ToolsFile, assemble, describe, parse
from app.methodology.defaults import GENERIC, generated_playbook, template_for
from app.methodology.packs import bundled
from app.methodology.spec import MethodologySpec, Playbook, RiskClass, hash_of, slug
from app.methodology.store import SpecDiff, diff_specs, with_overrides


def wstg() -> MethodologySpec:
    return bundled()[0]


def edited(spec: MethodologySpec, change: Callable[[dict[str, Any]], None]) -> MethodologySpec:
    document = copy.deepcopy(spec.model_dump(mode="json"))
    change(document)
    return MethodologySpec.model_validate(document)


def test_a_playbook_needs_tools_or_manual_review() -> None:
    with pytest.raises(ValidationError, match="list the tools to use"):
        Playbook.model_validate(PLAYBOOK | {"tools": []})
    assert Playbook.model_validate(PLAYBOOK | {"tools": [], "manual_review": True}).manual_review


def test_a_playbook_needs_evidence_and_refuses_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Playbook.model_validate(PLAYBOOK | {"evidence": []})
    with pytest.raises(ValidationError, match="Extra inputs"):
        Playbook.model_validate(PLAYBOOK | {"colour": "red"})


def test_the_hash_ignores_key_order_and_changes_with_content() -> None:
    assert hash_of({"a": 1, "b": 2}) == hash_of({"b": 2, "a": 1})
    assert hash_of({"a": 1}) != hash_of({"a": 2})

    def rename(document: dict[str, Any]) -> None:
        document["categories"][0]["tests"][0]["name"] = "Renamed"

    changed = edited(wstg(), rename)
    assert changed.content_hash() != wstg().content_hash()


def test_slug_makes_a_tag_from_a_title() -> None:
    assert slug("Configuration and Deployment Management") == "configuration-and-deployment-man"
    assert slug("!!!") == "other"
    assert slug("Client-side") == "client-side"


def test_a_diff_of_a_methodology_with_itself_is_empty() -> None:
    assert diff_specs(wstg(), wstg()).is_empty


def test_a_diff_lists_added_removed_and_changed_tests_and_details() -> None:
    def change(document: dict[str, Any]) -> None:
        tests = document["categories"][0]["tests"]
        tests.pop(0)
        tests[0]["objectives"] = ["A different objective"]
        tests[1]["playbook"]["summary"] = "A different summary"
        added = copy.deepcopy(tests[2])
        added["id"] = "WSTG-INFO-10"
        tests.append(added)
        document["categories"].pop()
        document["categories"].append(
            {"id": "WSTG-NEW", "name": "New", "tests": [{**added, "id": "WSTG-NEW-01"}]}
        )
        document["version"] = "snapshot later"
        document["license"] = "Another"

    diff = diff_specs(wstg(), edited(wstg(), change))
    assert diff.removed[0] == "WSTG-INFO-01"
    assert "WSTG-WASM-01" in diff.removed
    assert diff.added == ["WSTG-INFO-10", "WSTG-NEW-01"]
    assert {(item.id, tuple(item.fields)) for item in diff.changed} == {
        ("WSTG-INFO-02", ("objectives",)),
        ("WSTG-INFO-03", ("playbook",)),
    }
    assert diff.categories_added == ["WSTG-NEW"]
    assert diff.categories_removed == ["WSTG-WASM"]
    assert diff.details_changed == ["version", "license"]
    assert not diff.is_empty
    assert SpecDiff(details_changed=["name"]).is_empty is False


def test_overrides_replace_a_playbook_and_leave_the_stored_snapshot_alone() -> None:
    spec = wstg()
    custom = Playbook.model_validate(PLAYBOOK)
    merged = with_overrides(spec, {"WSTG-INFO-01": custom, "WSTG-GONE-01": custom})
    found = merged.find("WSTG-INFO-01")
    original = spec.find("WSTG-INFO-01")
    assert found is not None
    assert original is not None
    assert found[1].playbook == custom
    assert found[1].playbook_source == "custom"
    assert original[1].playbook_source == "generated"
    assert merged.content_hash() != spec.content_hash()


def test_the_default_for_a_category_nobody_wrote_a_template_for_is_generic() -> None:
    assert template_for("WSTG-INJT").focus.startswith("whether input")
    assert template_for("OTHER-THING") is GENERIC
    playbook = generated_playbook(
        category_id="OTHER-THING",
        test_name="A test",
        objectives=[],
        tools=["b.http"],
        manual_review=False,
        risk_class=RiskClass.INTRUSIVE,
        approach=None,
    )
    assert "Establish whether it is present." in playbook.instructions
    assert playbook.intrusive_steps
    assert "Suggested approach" not in playbook.instructions


def test_an_approach_is_added_to_the_instructions_without_a_double_stop() -> None:
    playbook = generated_playbook(
        category_id="WSTG-INFO",
        test_name="A test",
        objectives=["Find it"],
        tools=[],
        manual_review=True,
        risk_class=RiskClass.SAFE,
        approach="Look closely.",
    )
    assert "Suggested approach: Look closely.\n" in playbook.instructions
    assert "judgement work" in playbook.instructions
    assert not playbook.active_steps


def test_errors_say_where_the_problem_is() -> None:
    with pytest.raises(PackError, match=r"tests.WSTG-X-01.tools.0"):
        parse(ToolsFile, {"tests": {"WSTG-X-01": {"tools": ["NotATool"]}}}, "tools.yaml")
    with pytest.raises(ValidationError) as raised:
        MethodologySpec.model_validate({})
    assert "id: Field required" in describe(raised.value)


def test_assembling_a_draft_that_builds_an_invalid_spec_is_a_pack_error() -> None:
    draft = Draft.model_validate(
        {
            "id": "tiny",
            "name": "Tiny",
            "version": "1",
            "source_url": "https://example.com/",
            "license": "MIT",
            "categories": [
                {"id": "TINY-A", "name": "A", "tests": [{"id": "TINY-A-01", "name": "x"}]}
            ],
        }
    )
    tools = ToolsFile.model_validate({"tests": {"TINY-A-01": {"tools": ["b.http"] * 21}}})
    with pytest.raises(PackError, match="The methodology is not valid"):
        assemble(draft, tools, {})


def test_a_stored_methodology_with_a_repeated_id_is_not_accepted() -> None:
    def repeat(document: dict[str, Any]) -> None:
        document["categories"][0]["tests"][1]["id"] = "WSTG-INFO-01"

    with pytest.raises(ValidationError, match="WSTG-INFO-01 appears twice"):
        edited(wstg(), repeat)
