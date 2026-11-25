"""The commander's plan: which tests run, in what order, and why some do not.

This is code, not a model: the order and the skips follow from the methodology, what the target
shows, what a person has already recorded, and the most intrusive thing the pentest allows.
Categories whose tests only observe go first (reconnaissance feeds what comes after), then the
active ones, then the intrusive ones; inside a phase the methodology's own order is kept.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.db.models import CheckStatus, PentestCheck
from app.methodology.spec import RISK_ORDER, MethodologySpec, RiskClass, Test

# A person's word stands: a test they already settled is not run again.
SETTLED = frozenset(
    {CheckStatus.PASSED.value, CheckStatus.FINDING.value, CheckStatus.NOT_APPLICABLE.value}
)


@dataclass(frozen=True)
class PlannedTest:
    test: Test
    skip: str | None  # why it will not run, or None


@dataclass(frozen=True)
class PlannedCategory:
    id: str
    name: str
    phase: int
    tests: list[PlannedTest] = field(default_factory=list[PlannedTest])


def _rank(risk: RiskClass) -> int:
    return RISK_ORDER.index(risk)


NOT_PICKED = "This test was not picked for this mission."


def _skip_reason(
    test: Test, check: PentestCheck | None, features: list[str], max_risk: RiskClass
) -> str | None:
    if not all(need in features for need in test.requires):
        return "The target does not show what this test needs."
    if check is not None and check.status in SETTLED:
        return "A person has already recorded the result."
    if _rank(test.risk_class) > _rank(max_risk):
        return (
            f"The test is {test.risk_class.value}, above the pentest's limit of {max_risk.value}."
        )
    if test.playbook.manual_review:
        return "This test is for a person to review."
    return None


def plan_mission(
    spec: MethodologySpec,
    checks: dict[str, PentestCheck],
    features: list[str],
    max_risk: RiskClass,
    only: frozenset[str] | None = None,
) -> list[PlannedCategory]:
    """The categories in the order they run, each with every test and whether it runs. When `only`
    is given, just the tests and categories it names run (the rest are shown as not picked)."""
    categories: list[PlannedCategory] = []
    for category in spec.categories:
        picked = only is None or category.id in only
        planned = [
            PlannedTest(
                test,
                NOT_PICKED
                if not picked and test.id not in (only or ())
                else _skip_reason(test, checks.get(test.id), features, max_risk),
            )
            for test in category.tests
        ]
        running = [p.test.risk_class for p in planned if p.skip is None]
        phase = max((_rank(risk) for risk in running), default=0)
        categories.append(PlannedCategory(category.id, category.name, phase, planned))
    return sorted(categories, key=lambda one: one.phase)  # stable: the methodology's order stays


def summarize(plan: list[PlannedCategory]) -> dict[str, Any]:
    """What a plan comes to, for a person to read before a mission starts."""
    running = [p.test for one in plan for p in one.tests if p.skip is None]
    reasons = Counter(p.skip for one in plan for p in one.tests if p.skip is not None)
    return {
        "runs": len(running),
        "skipped": sum(reasons.values()),
        "risk": {
            risk.value: sum(1 for t in running if t.risk_class is risk) for risk in RISK_ORDER
        },
        "tools": sorted({tool for t in running for tool in t.playbook.tools}),
        "skips": [{"reason": reason, "tests": count} for reason, count in reasons.most_common()],
        "categories": [
            {
                "id": one.id,
                "name": one.name,
                "phase": one.phase,
                "runs": sum(1 for p in one.tests if p.skip is None),
                "skipped": sum(1 for p in one.tests if p.skip is not None),
            }
            for one in plan
        ],
    }
