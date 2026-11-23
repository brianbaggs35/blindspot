"""The jobs a model can be chosen for. An administrator picks a default model for each."""

from enum import StrEnum


class AgentRole(StrEnum):
    """What the model is doing."""

    COMMANDER = "commander"
    CATEGORY_AGENT = "category-agent"
    TEST_AGENT = "test-agent"
    REPORTER = "reporter"
    CHAT = "chat"


ROLE_LABELS: dict[AgentRole, str] = {
    AgentRole.COMMANDER: "Commander: plans the pentest and hands out the work",
    AgentRole.CATEGORY_AGENT: "Category agents: one per group of tests",
    AgentRole.TEST_AGENT: "Test agents: run one test each",
    AgentRole.REPORTER: "Reporter: writes findings and reports",
    AgentRole.CHAT: "Chat: answers your questions",
}
