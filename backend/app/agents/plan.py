"""The commander's plan: which tests run, in what order, and why some do not.

This is code, not a model: the order and the skips follow from the methodology, what the target
shows, what a person has already recorded, and the most intrusive thing the pentest allows.
Categories whose tests only observe go first (reconnaissance feeds what comes after), then the
active ones, then the intrusive ones; inside a phase the methodology's own order is kept.
"""

from dataclasses import dataclass, field

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
) -> list[PlannedCategory]:
    """The categories in the order they run, each with every test and whether it runs."""
    categories: list[PlannedCategory] = []
    for category in spec.categories:
        planned = [
            PlannedTest(test, _skip_reason(test, checks.get(test.id), features, max_risk))
            for test in category.tests
        ]
        running = [p.test.risk_class for p in planned if p.skip is None]
        phase = max((_rank(risk) for risk in running), default=0)
        categories.append(PlannedCategory(category.id, category.name, phase, planned))
    return sorted(categories, key=lambda one: one.phase)  # stable: the methodology's order stays
