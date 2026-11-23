"""Prices and cost: the catalog, overrides, caching and unknown models."""

from datetime import date
from decimal import Decimal

import pytest

from app.ai.kinds import ProviderKind
from app.ai.pricing import FREE, Price, Usage, cost_usd, load_catalog, price_for


def D(text: str) -> Decimal:  # noqa: N802  # reads like a number
    return Decimal(text)


def test_the_catalog_says_when_it_was_checked_and_lists_the_documented_models() -> None:
    catalog = load_catalog()
    assert catalog.verified_on == date(2026, 11, 23)
    assert catalog.source == "docs/research/models-and-pricing.md"
    ids = {(one.kind.value, one.id) for one in catalog.models}
    assert {
        ("anthropic", "claude-opus-5-5"),
        ("anthropic", "claude-sonnet-5-5"),
        ("anthropic", "claude-haiku-5-5"),
        ("anthropic", "claude-fable-5-2"),
        ("openai", "gpt-6-luna"),
        ("openai", "gpt-6.1-terra"),
        ("openai", "gpt-6.2-sol"),
        ("openai", "gpt-6.2-astra"),
        ("openai", "gpt-5.4-mini"),
    } <= ids
    assert load_catalog() is catalog  # read once
    assert catalog.find(ProviderKind.OPENAI, "claude-opus-5-5") is None


def test_a_call_costs_what_the_catalog_says_with_cache_reads_and_writes() -> None:
    price = price_for(ProviderKind.ANTHROPIC, "claude-opus-5-5")
    usage = Usage(
        input_tokens=1_000,
        output_tokens=2_000,
        cache_read_tokens=100_000,
        cache_write_tokens=10_000,
        cache_write_long_tokens=5_000,
        thinking_tokens=1_500,
    )
    # $4, $20, $0.20, $5 and $8 per million tokens.
    expected = (
        D("4") * 1_000 + D("20") * 2_000 + D("0.20") * 100_000 + D("5") * 10_000 + D("8") * 5_000
    ) / 1_000_000
    assert cost_usd(price, usage) == expected == D("0.154")


def test_thinking_tokens_are_part_of_the_output_and_not_charged_twice() -> None:
    price = price_for(ProviderKind.ANTHROPIC, "claude-sonnet-5-5")
    plain = Usage(output_tokens=1_000)
    thinking = Usage(output_tokens=1_000, thinking_tokens=900)
    assert cost_usd(price, plain) == cost_usd(price, thinking) == D("0.01")


def test_haiku_has_a_higher_price_for_prompts_over_100k_counting_the_cache() -> None:
    short = Usage(input_tokens=90_000, output_tokens=1_000)
    assert price_for(
        ProviderKind.ANTHROPIC, "claude-haiku-5-5", None, short.prompt_tokens
    ).input == D("0.10")
    # 50K new + 60K read = 110K prompt tokens: the long tier, for every token class.
    long = Usage(input_tokens=50_000, cache_read_tokens=60_000, output_tokens=1_000)
    assert long.prompt_tokens == 110_000
    price = price_for(ProviderKind.ANTHROPIC, "claude-haiku-5-5", None, long.prompt_tokens)
    assert (price.input, price.cache_read, price.output) == (D("0.50"), D("0.05"), D("2.50"))
    assert (
        cost_usd(price, long)
        == (D("0.50") * 50_000 + D("0.05") * 60_000 + D("2.50") * 1_000) / 1_000_000
    )
    # The boundary is "above": exactly 100K stays in the short tier.
    assert price_for(ProviderKind.ANTHROPIC, "claude-haiku-5-5", None, 100_000).input == D("0.10")


def test_openai_writes_cost_extra_and_reads_are_a_fraction() -> None:
    terra = price_for(ProviderKind.OPENAI, "gpt-6.1-terra")
    assert (terra.input, terra.cache_read, terra.cache_write, terra.cache_write_long) == (
        D("1"),
        D("0.05"),
        D("1.25"),
        D("2.50"),
    )
    sol = price_for(ProviderKind.OPENAI, "gpt-6.2-sol")
    assert sol.input is not None
    assert sol.cache_write == D("2.5") == sol.input * D("1.25")
    assert sol.cache_write_long == D("5") == sol.input * D("2.5")
    astra = price_for(ProviderKind.OPENAI, "gpt-6.2-astra")
    assert astra.input is not None
    assert astra.cache_read == astra.input * D("0.05")


def test_a_long_openai_prompt_uses_the_long_price_but_cache_prices_there_are_not_known() -> None:
    price = price_for(ProviderKind.OPENAI, "gpt-6.2-sol", None, 300_000)
    assert (price.input, price.output) == (D("4"), D("15"))
    assert cost_usd(price, Usage(input_tokens=300_000, output_tokens=1_000)) == D("1.215")
    # Cached tokens in a long prompt have no documented price, so no figure is made up.
    assert cost_usd(price, Usage(input_tokens=200_000, cache_read_tokens=100_000)) is None


def test_an_unknown_model_has_an_unknown_cost_not_a_guess() -> None:
    price = price_for(ProviderKind.OPENAI, "gpt-6-sol")
    assert price == Price()
    assert cost_usd(price, Usage(input_tokens=10)) is None
    assert cost_usd(price, Usage()) == D("0")  # nothing used, nothing owed


def test_a_cost_is_unknown_only_when_a_used_kind_of_token_has_no_price() -> None:
    price = Price(input=D("1"), output=D("2"))
    assert cost_usd(price, Usage(input_tokens=1_000_000, output_tokens=500_000)) == D("2")
    assert cost_usd(price, Usage(input_tokens=10, cache_read_tokens=1)) is None


def test_models_on_this_machine_are_free_and_ollama_cloud_is_unknown() -> None:
    assert price_for(ProviderKind.OLLAMA_LOCAL, "llama3.3:70b") == FREE
    assert cost_usd(FREE, Usage(input_tokens=5_000, output_tokens=500)) == D("0")
    assert price_for(ProviderKind.OLLAMA_CLOUD, "gemma4:31b") == Price()


def test_an_override_replaces_those_prices_and_ends_the_long_prompt_tier() -> None:
    override = Price(input=D("3"), cache_read=D("0.3"))
    price = price_for(ProviderKind.ANTHROPIC, "claude-haiku-5-5", override, 500_000)
    assert price.input == D("3")
    assert price.cache_read == D("0.3")
    assert price.output == D("0.50")  # still the catalog's short-tier price
    assert price.cache_write == D("0.125")
    # For a model the catalog does not know, an override can supply the whole price.
    own = price_for(ProviderKind.OLLAMA_CLOUD, "x", Price(input=D("1"), output=D("2")))
    assert cost_usd(own, Usage(input_tokens=1_000_000, output_tokens=1_000_000)) == D("3")
    # An empty override changes nothing.
    assert price_for(ProviderKind.OPENAI, "gpt-6-luna", Price()) == price_for(
        ProviderKind.OPENAI, "gpt-6-luna"
    )
    # Even a local model can be given a price.
    paid = price_for(ProviderKind.OLLAMA_LOCAL, "m", Price(input=D("1")))
    assert (paid.input, paid.output) == (D("1"), D("0"))


@pytest.mark.parametrize("tokens", [0, 1, 999_999])
def test_prompt_tokens_add_up_every_input_kind(tokens: int) -> None:
    usage = Usage(
        input_tokens=tokens,
        cache_read_tokens=1,
        cache_write_tokens=2,
        cache_write_long_tokens=3,
        output_tokens=99,
    )
    assert usage.prompt_tokens == tokens + 6
