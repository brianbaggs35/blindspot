"""Reading methodologies: the WSTG import, the pack folders and what is refused."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from tests.methodology_helpers import METHODOLOGY, PLAYBOOK, TOOLS, playbook, write_pack

from app.methodology import packs
from app.methodology import spec as spec_module
from app.methodology.build import PackError
from app.methodology.packs import (
    BUNDLED,
    WSTG_REQUIRES,
    bundled,
    load_pack,
    load_packs,
    wstg_spec,
)
from app.methodology.spec import RiskClass


def checklist() -> dict[str, Any]:
    return json.loads((BUNDLED / "wstg" / "checklist.json").read_text())


def test_all_133_wstg_tests_import_with_their_objectives_and_references() -> None:
    (spec,) = bundled()
    assert (spec.id, len(spec.categories), len(spec.tests())) == ("wstg", 13, 133)
    assert all(test.reference and test.reference.startswith("https://") for test in spec.tests())
    assert all(test.objectives for test in spec.tests())
    assert {category.id for category in spec.categories} >= {"WSTG-INFO", "WSTG-WASM", "WSTG-APIT"}
    names = {category.id: category.name for category in spec.categories}
    assert names["WSTG-INJT"] == "Injection"


def test_importing_wstg_twice_gives_the_same_fingerprint() -> None:
    first, second = bundled(), bundled()
    assert first[0].content_hash() == second[0].content_hash()


def test_every_wstg_test_has_a_way_to_run_and_a_playbook() -> None:
    for test in bundled()[0].tests():
        assert test.playbook.tools or test.playbook.manual_review, test.id
        assert test.playbook.evidence, test.id
        assert test.playbook.summary, test.id


def test_the_highest_value_tests_have_hand_written_playbooks() -> None:
    spec = bundled()[0]
    authored = {test.id for test in spec.tests() if test.playbook_source == "authored"}
    assert authored == {
        "WSTG-INFO-02",
        "WSTG-ATHN-02",
        "WSTG-ATHZ-04",
        "WSTG-SESS-02",
        "WSTG-SESS-10",
        "WSTG-INJT-01",
        "WSTG-INJT-04",
        "WSTG-INJT-18",
        "WSTG-CRYP-01",
        "WSTG-APIT-02",
    }
    generated = spec.find("WSTG-INFO-01")
    assert generated is not None
    assert generated[1].playbook_source == "generated"


def test_a_playbook_never_lists_steps_above_its_tests_risk_class() -> None:
    for test in bundled()[0].tests():
        if test.playbook.intrusive_steps:
            assert test.risk_class is RiskClass.INTRUSIVE
        if test.playbook.active_steps:
            assert test.risk_class is not RiskClass.SAFE
        if test.risk_class is RiskClass.SAFE:
            assert not test.playbook.active_steps
            assert not test.playbook.intrusive_steps
        if test.risk_class is RiskClass.ACTIVE:
            assert not test.playbook.intrusive_steps


def test_judgement_tests_are_marked_for_manual_review() -> None:
    spec = bundled()[0]
    for test_id in ("WSTG-BUSL-06", "WSTG-IDNT-01", "WSTG-SESS-08"):
        found = spec.find(test_id)
        assert found is not None
        assert found[1].playbook.manual_review
    busl = spec.find("WSTG-BUSL-06")
    assert busl is not None
    assert "judgement work" in busl[1].playbook.instructions


def test_applicability_rules_name_real_tests() -> None:
    ids = {test.id for test in bundled()[0].tests()}
    assert set(WSTG_REQUIRES) <= ids
    found = bundled()[0].find("WSTG-ATHN-11")
    assert found is not None
    assert found[1].requires == ["saml"]


def test_a_test_upstream_added_is_manual_review_until_somebody_maps_it() -> None:
    document = checklist()
    document["categories"]["Information Gathering"]["tests"].append(
        {
            "id": "WSTG-INFO-10",
            "name": "A new test",
            "reference": "https://wstg.owasp.org/latest/x",
            "objectives": ["Look at the new thing"],
            "new_field": "ignored",
        }
    )
    spec = wstg_spec(json.dumps(document).encode(), version="snapshot test")
    found = spec.find("WSTG-INFO-10")
    assert found is not None
    assert found[1].playbook.manual_review
    assert found[1].playbook.tools == []
    assert len(spec.tests()) == 134


def test_a_test_upstream_dropped_does_not_break_the_import() -> None:
    document = checklist()
    document["categories"]["Information Gathering"]["tests"].pop()
    assert len(wstg_spec(json.dumps(document).encode(), version="x").tests()) == 132


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"not json", "not valid JSON"),
        (b"[]", "The WSTG checklist is not valid"),
        (b'{"categories": {"X": {"id": "lowercase", "tests": []}}}', "not valid"),
        (
            b'{"categories": {"X": {"id": "WSTG-X", "tests": '
            b'[{"id": "WSTG-X-01", "name": "t", "reference": "http://plain"}]}}}',
            "not valid",
        ),
    ],
)
def test_a_checklist_that_is_not_right_is_refused_in_plain_words(raw: bytes, message: str) -> None:
    with pytest.raises(PackError, match=message):
        wstg_spec(raw, version="x")


def test_a_second_methodology_loads_through_the_same_loader(tmp_path: Path) -> None:
    folder = write_pack(tmp_path)
    spec = load_pack(folder)
    assert (spec.id, len(spec.categories), len(spec.tests())) == ("ptes", 2, 3)
    recon, active, exploit = spec.tests()
    assert recon.playbook_source == "authored"
    assert active.playbook_source == "generated"
    assert active.risk_class is RiskClass.ACTIVE
    assert exploit.playbook.manual_review
    assert exploit.risk_class is RiskClass.INTRUSIVE
    assert spec.categories[0].reporting_label == "Recon"
    assert spec.categories[1].reporting_label is None
    assert spec.content_hash() != bundled()[0].content_hash()


def test_a_pack_without_hand_written_playbooks_or_reporting_still_loads(tmp_path: Path) -> None:
    folder = write_pack(tmp_path, **{"playbooks/recon.yaml": None, "reporting.yaml": None})
    spec = load_pack(folder)
    assert all(test.playbook_source == "generated" for test in spec.tests())


def test_packs_are_found_in_a_folder_and_broken_ones_are_listed_not_fatal(tmp_path: Path) -> None:
    write_pack(tmp_path)
    broken = tmp_path / "broken"
    broken.mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "note.txt").write_text("not a pack")
    specs, problems = load_packs(tmp_path)
    assert [spec.id for spec in specs] == ["ptes"]
    assert problems == {"broken": "There is no methodology.yaml"}


def test_a_folder_that_does_not_exist_has_no_packs(tmp_path: Path) -> None:
    assert load_packs(tmp_path / "nothing") == ([], {})


def changed(document: dict[str, Any], *path: str | int, value: object) -> dict[str, Any]:
    edited = copy.deepcopy(document)
    target: object = edited
    for step in path[:-1]:
        target = target[step]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    return edited


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ({"methodology.yaml": None}, "There is no methodology.yaml"),
        ({"tools.yaml": None}, "There is no tools.yaml"),
        ({"methodology.yaml": "id: [unclosed"}, r"methodology.yaml is not valid YAML"),
        ({"methodology.yaml": "[]"}, "methodology.yaml is not valid"),
        (
            {"methodology.yaml": changed(METHODOLOGY, "id", value="other")},
            "folder is called ptes but the methodology id is other",
        ),
        (
            {"methodology.yaml": changed(METHODOLOGY, "unknown", value=1)},
            r"unknown: Extra inputs are not permitted",
        ),
        (
            {
                "methodology.yaml": changed(
                    METHODOLOGY, "categories", 0, "tests", 0, "id", value="X-1"
                )
            },
            "does not belong to category PTES-RECON",
        ),
        (
            {"tools.yaml": changed(TOOLS, "tests", "PTES-RECON-02", value={"tools": ["nmap"]})},
            "tools.yaml is not valid",
        ),
        (
            {"tools.yaml": {"tests": {"PTES-NOPE-01": {"tools": ["b.http"]}}}},
            "names tests that are not in the methodology: PTES-NOPE-01",
        ),
        (
            {"tools.yaml": {"tests": {"PTES-RECON-01": {"tools": ["b.osint"]}}}},
            r"tools.yaml has no entry for: PTES-EXPL-01, PTES-RECON-02",
        ),
        ({"playbooks/recon.yaml": "- not a map"}, "must map test ids to playbooks"),
        (
            {"playbooks/recon.yaml": {"PTES-RECON-01": {"summary": "only a summary"}}},
            "The playbook for PTES-RECON-01 is not valid",
        ),
        (
            {"playbooks/recon.yaml": {"PTES-RECON-01": playbook(tools=[])}},
            "list the tools to use, or mark the test as manual review",
        ),
        (
            {"playbooks/recon.yaml": {"PTES-NOPE-01": PLAYBOOK}},
            "playbooks names tests that are not in the methodology",
        ),
        (
            {"reporting.yaml": {"categories": {"PTES-NOPE": "Nope"}}},
            "reporting.yaml names tests that are not in the methodology: PTES-NOPE",
        ),
        ({"reporting.yaml": "categories: 3"}, "reporting.yaml is not valid"),
    ],
)
def test_a_pack_that_is_wrong_is_refused_with_the_reason(
    tmp_path: Path, files: dict[str, object], message: str
) -> None:
    folder = write_pack(tmp_path, **files)
    with pytest.raises(PackError, match=message):
        load_pack(folder)


def test_a_file_that_is_too_large_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = write_pack(tmp_path)
    monkeypatch.setattr(packs, "MAX_FILE_BYTES", 10)
    with pytest.raises(PackError, match=r"methodology.yaml is larger than"):
        load_pack(folder)


def test_a_file_that_is_not_text_is_refused(tmp_path: Path) -> None:
    folder = write_pack(tmp_path)
    (folder / "methodology.yaml").write_bytes(b"\xff\xfe\x00 binary")
    with pytest.raises(PackError, match="is not valid YAML"):
        load_pack(folder)


def test_two_tests_with_one_id_or_a_category_twice_are_refused(tmp_path: Path) -> None:
    twice = changed(METHODOLOGY, "categories", 0, "tests", 1, "id", value="PTES-RECON-01")
    with pytest.raises(PackError, match="appears twice"):
        load_pack(write_pack(tmp_path, **{"methodology.yaml": twice}))
    categories: list[dict[str, Any]] = copy.deepcopy(METHODOLOGY["categories"])
    both = changed(METHODOLOGY, "categories", value=[categories[0], categories[0]])
    with pytest.raises(PackError, match="category PTES-RECON appears twice"):
        load_pack(write_pack(tmp_path, **{"methodology.yaml": both}))


def test_a_methodology_with_too_many_tests_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spec_module, "MAX_TESTS", 2)
    with pytest.raises(PackError, match="at most 2 tests"):
        load_pack(write_pack(tmp_path))
