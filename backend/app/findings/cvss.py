"""Scoring a CVSS vector. The maths is the `cvss` library's; `tests/test_findings_cvss.py` checks it
against the reference vectors that FIRST publishes, so a change to the library that moves a score
fails the build. Only CVSS 3.1 and 4.0 are taken."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from cvss import CVSS3, CVSS4, CVSSError  # pyright: ignore[reportMissingTypeStubs]

V31 = "CVSS:3.1/"
V4 = "CVSS:4.0/"
MAX_VECTOR = 200


class VectorError(ValueError):
    """The text is not a CVSS 3.1 or 4.0 vector."""


@dataclass(frozen=True)
class Scored:
    vector: str  # in the library's canonical order
    score: Decimal
    severity: str  # info (a score of 0), low, medium, high or critical


def severity_of(score: Decimal) -> str:
    """The rating FIRST names for a score: 0.1 to 3.9 low, 4 to 6.9 medium, 7 to 8.9 high, 9 and
    over critical. A score of 0 is "none"; findings call that informational."""
    for ceiling, name in (
        (Decimal("0.1"), "info"),
        (Decimal("4.0"), "low"),
        (Decimal("7.0"), "medium"),
    ):
        if score < ceiling:
            return name
    return "high" if score < Decimal("9.0") else "critical"


def _failed(error: Exception) -> VectorError:
    return VectorError(f"This is not a valid CVSS vector: {error}")


def score_v31(vector: str) -> Scored:
    """A CVSS 3.1 vector's score: the environmental one when the vector has such metrics, else the
    temporal one, else the base score (the library gives that one in every case)."""
    if not vector.startswith(V31):
        raise VectorError("A CVSS 3.1 vector starts with CVSS:3.1/")
    try:
        parsed: Any = CVSS3(vector)
        final = Decimal(str(parsed.scores()[2]))
        clean = str(parsed.clean_vector())
    except (CVSSError, ValueError, KeyError, IndexError, TypeError) as error:
        raise _failed(error) from None
    return Scored(clean, final, severity_of(final))


def score_v4(vector: str) -> Scored:
    """A CVSS 4.0 vector's score (the library's `base_score` is the overall score, threat and
    environmental metrics included)."""
    if not vector.startswith(V4):
        raise VectorError("A CVSS 4.0 vector starts with CVSS:4.0/")
    try:
        parsed: Any = CVSS4(vector)
        final = Decimal(str(parsed.base_score))
        clean = str(parsed.clean_vector())
    except (CVSSError, ValueError, KeyError, IndexError, TypeError) as error:
        raise _failed(error) from None
    return Scored(clean, final, severity_of(final))


def score(vector: str) -> Scored:
    """Score a vector of either version."""
    text = vector.strip()
    if len(text) > MAX_VECTOR:
        raise VectorError("This vector is too long")
    if text.startswith(V4):
        return score_v4(text)
    if text.startswith(V31):
        return score_v31(text)
    raise VectorError("Start the vector with CVSS:3.1/ or CVSS:4.0/")
