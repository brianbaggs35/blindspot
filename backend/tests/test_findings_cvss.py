"""CVSS scoring against the reference vectors of the CVSS specifications (FIRST)."""

from decimal import Decimal

import pytest

from app.findings import cvss

V31 = [
    # The worked examples of the CVSS 3.1 specification and the user guide.
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", "9.8", "critical"),
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N", "6.1", "medium"),
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H", "10.0", "critical"),
    ("CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H", "7.8", "high"),
    ("CVSS:3.1/AV:L/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N", "1.8", "low"),
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N", "0.0", "info"),
]
V4 = [
    # The examples of the CVSS 4.0 specification and calculator.
    ("CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N", "9.3", "critical"),
    ("CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:H/SI:H/SA:H", "10.0", "critical"),
    ("CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:L/VI:L/VA:N/SC:N/SI:N/SA:N", "6.9", "medium"),
    ("CVSS:4.0/AV:L/AC:L/AT:N/PR:N/UI:N/VC:N/VI:N/VA:N/SC:N/SI:N/SA:N", "0.0", "info"),
]


@pytest.mark.parametrize(("vector", "score", "severity"), V31 + V4)
def test_the_reference_vectors_score_as_first_publishes(
    vector: str, score: str, severity: str
) -> None:
    scored = cvss.score(vector)
    assert (scored.score, scored.severity) == (Decimal(score), severity)
    assert scored.vector == vector


def test_a_version_can_be_asked_for_by_name() -> None:
    assert cvss.score_v31(V31[0][0]).score == Decimal("9.8")
    assert cvss.score_v4(V4[0][0]).score == Decimal("9.3")


def test_temporal_and_environmental_metrics_move_the_3_1_score() -> None:
    base = cvss.score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H")
    softer = cvss.score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H/E:P/RL:O/RC:U")
    assert softer.score < base.score


def test_the_severity_names_follow_the_bands() -> None:
    bands = {"0": "info", "0.1": "low", "3.9": "low", "4.0": "medium", "6.9": "medium"}
    bands |= {"7.0": "high", "8.9": "high", "9.0": "critical", "10.0": "critical"}
    for score, name in bands.items():
        assert cvss.severity_of(Decimal(score)) == name


@pytest.mark.parametrize(
    "vector",
    [
        "",
        "nonsense",
        "CVSS:2.0/AV:N/AC:L/Au:N/C:P/I:P/A:P",
        "CVSS:3.1/AV:N",
        "CVSS:3.1/AV:X/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "CVSS:4.0/AV:N",
        "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:Z",
        "CVSS:3.1/" + "A" * 300,
    ],
)
def test_text_that_is_not_a_vector_is_refused(vector: str) -> None:
    with pytest.raises(cvss.VectorError):
        cvss.score(vector)


def test_each_version_refuses_the_others_prefix() -> None:
    with pytest.raises(cvss.VectorError, match=r"CVSS:3\.1/"):
        cvss.score_v31(V4[0][0])
    with pytest.raises(cvss.VectorError, match=r"CVSS:4\.0/"):
        cvss.score_v4(V31[0][0])
