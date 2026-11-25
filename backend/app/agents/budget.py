"""What a mission may spend. Every cap is checked by code before a step, never by a model."""

from pydantic import BaseModel, ConfigDict, Field


class Budget(BaseModel):
    """The caps of one mission. A test has its own, smaller steps and time caps."""

    model_config = ConfigDict(extra="forbid")

    steps: int = Field(default=300, ge=1, le=100_000)
    steps_per_test: int = Field(default=12, ge=1, le=200)
    tokens: int = Field(default=2_000_000, ge=1000, le=1_000_000_000)
    tokens_per_test: int = Field(default=120_000, ge=1000, le=100_000_000)
    cost_usd: float = Field(default=25.0, ge=0, le=100_000)
    seconds: int = Field(default=6 * 3600, ge=10, le=14 * 24 * 3600)
    seconds_per_test: int = Field(default=900, ge=5, le=24 * 3600)
    concurrency: int = Field(default=2, ge=1, le=16)
    # A finding at or above this severity is replayed by the verifier before it counts as
    # confirmed.
    verify_from: str = Field(default="medium", pattern=r"^(info|low|medium|high|critical)$")


class Spent(BaseModel):
    """What has been used so far."""

    model_config = ConfigDict(extra="forbid")

    steps: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0

    def add(
        self, *, steps: int = 0, tokens: int = 0, cost_usd: float = 0.0, seconds: float = 0.0
    ) -> Spent:
        return Spent(
            steps=self.steps + steps,
            tokens=self.tokens + tokens,
            cost_usd=round(self.cost_usd + cost_usd, 6),
            seconds=round(self.seconds + seconds, 3),
        )


def mission_exhausted(budget: Budget, spent: Spent) -> str | None:
    """Why the whole mission must stop, or None."""
    if spent.steps >= budget.steps:
        return f"The mission used its {budget.steps} steps."
    if spent.tokens >= budget.tokens:
        return f"The mission used its {budget.tokens} tokens."
    if spent.cost_usd >= budget.cost_usd:
        return f"The mission reached its cost cap of ${budget.cost_usd:.2f}."
    if spent.seconds >= budget.seconds:
        return f"The mission ran for its {budget.seconds} seconds."
    return None


def task_exhausted(budget: Budget, spent: Spent) -> str | None:
    """Why one test must stop, or None."""
    if spent.steps >= budget.steps_per_test:
        return f"The test used its {budget.steps_per_test} steps."
    if spent.tokens >= budget.tokens_per_test:
        return f"The test used its {budget.tokens_per_test} tokens."
    if spent.seconds >= budget.seconds_per_test:
        return f"The test ran for its {budget.seconds_per_test} seconds."
    return None
