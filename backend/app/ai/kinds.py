"""The kinds of provider, and what is true of each."""

from dataclasses import dataclass
from enum import StrEnum


class ProviderKind(StrEnum):
    """Who runs the model."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA_LOCAL = "ollama-local"
    OLLAMA_CLOUD = "ollama-cloud"


@dataclass(frozen=True)
class KindInfo:
    """What a kind of provider needs."""

    label: str
    default_base_url: str
    needs_key: bool
    # Only a provider on this machine or network may be at a private address.
    allows_private_addresses: bool
    # Plain http is fine only where the traffic never leaves the machine or network.
    allows_http: bool


KINDS: dict[ProviderKind, KindInfo] = {
    ProviderKind.ANTHROPIC: KindInfo(
        label="Anthropic",
        default_base_url="https://api.anthropic.com",
        needs_key=True,
        allows_private_addresses=False,
        allows_http=False,
    ),
    ProviderKind.OPENAI: KindInfo(
        label="OpenAI",
        default_base_url="https://api.openai.com/v1",
        needs_key=True,
        allows_private_addresses=False,
        allows_http=False,
    ),
    ProviderKind.OLLAMA_LOCAL: KindInfo(
        label="Ollama (local)",
        default_base_url="http://host.docker.internal:11434",
        needs_key=False,
        allows_private_addresses=True,
        allows_http=True,
    ),
    ProviderKind.OLLAMA_CLOUD: KindInfo(
        label="Ollama (cloud)",
        default_base_url="https://ollama.com",
        needs_key=True,
        allows_private_addresses=False,
        allows_http=False,
    ),
}
