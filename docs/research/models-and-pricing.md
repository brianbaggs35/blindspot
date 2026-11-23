# Model IDs and pricing

_Verified 2026-11-23 against the providers' own documentation (Anthropic, OpenAI, Ollama, Pydantic AI). Prices change: the app ships a catalog file with a "verified on" date, lets you override prices, and shows cost as "unknown" for models it has no price for._

## Anthropic

Source: [pricing](https://platform.claude.com/docs/en/about-claude/pricing) and [models overview](https://platform.claude.com/docs/en/about-claude/models/overview). Prices are USD per million tokens (MTok).

| Model | API ID | Context | Max output | Input | Output | Cache write 5m / 1h | Cache read | Batch in / out |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Opus 5.5 | `claude-opus-5-5` | 1M | 128K | $4 | $20 | $5 / $8 | $0.20 | $2 / $10 |
| Sonnet 5.5 | `claude-sonnet-5-5` | 1M | 128K | $2 | $10 | $2.50 / $4 | $0.10 | $1 / $5 |
| Haiku 5.5 (prompt up to 100K) | `claude-haiku-5-5` | 1M | 128K | $0.10 | $0.50 | $0.125 / $0.20 | $0.01 | $0.05 / $0.25 |
| Haiku 5.5 (prompt over 100K) | `claude-haiku-5-5` | 1M | 128K | $0.50 | $2.50 | $0.625 / $1 | $0.05 | $0.25 / $1.25 |
| Fable 5.2 (optional "deep" model) | `claude-fable-5-2` | 1M | 128K | $8 | $40 | $10 / $16 | $0.20 | $4 / $20 |

Notes: Haiku 5.5 is the only model with a long-prompt price tier (counts cache reads and writes). Thinking is adaptive on all of these; manual `budget_tokens` thinking is not accepted. Default effort: Opus 5.5 medium, Sonnet 5.5 high, Haiku 5.5 medium. Minimum cacheable prompt length: 512 tokens for these models (see the caching strategy below).

## OpenAI

Source: [pricing](https://developers.openai.com/api/docs/pricing), [models](https://developers.openai.com/api/docs/models), [deprecations](https://developers.openai.com/api/docs/deprecations). USD per million tokens; short context is up to 272K input tokens.

**"GPT-6 Luna" and "Sol" do exist.** The family is not one version: the version number is part of the ID.

| Model ID | Role | Input | Cached input | Output | Long context (in / out) |
| --- | --- | --- | --- | --- | --- |
| `gpt-6-luna` | Small, cheap (replaces the nano and mini models) | $0.10 | $0.01 | $0.50 | $0.20 / $0.75 |
| `gpt-6.1-terra` | Fast, efficient mid model | $1.00 | $0.05 | $5.00 | $2.00 / $7.50 |
| `gpt-6.2-sol` | Main reasoning model | $2.00 | $0.10 | $10.00 | $4.00 / $15.00 |
| `gpt-6.2-astra` | Flagship | $8.00 | $0.40 | $40.00 | $16.00 / $60.00 |
| `gpt-6-sol`, `gpt-6.1-sol`, `gpt-6-astra` | Earlier versions (still listed, not deprecated) | see page | | | |

Context for Luna, Terra, Sol 6.2 and Astra 6.2 is 1.05M tokens with 128K max output. Batch is 50% of standard.

Smaller older models: `gpt-5.4-mini` ($0.75 / $0.075 / $4.50) and `gpt-5.4-nano` ($0.20 / $0.02 / $1.25) are listed; `gpt-5-mini` and `gpt-5-nano` shut down 2026-12-11 and `gpt-4.1-mini` / `gpt-4o-mini` on 2027-01-14. **Support plan:** `gpt-6-luna` as the small model, `gpt-6.1-terra`, `gpt-6.2-sol`, `gpt-6.2-astra`, plus `gpt-5.4-mini` for users who want it; the list is fetched from the API so new IDs appear without a release.

Not verified: Chat Completions support for GPT-6 (the models and caching pages name the Responses API); the end of the deprecations page was only read as a summary. Cache **write** prices apply on top of the table: see the caching strategy below.

## Ollama (local and cloud)

Sources: [authentication](https://docs.ollama.com/api/authentication), [cloud](https://docs.ollama.com/cloud), [cloud API keys](https://docs.ollama.com/cloud/api), [cloud models](https://docs.ollama.com/cloud/models), [list models](https://docs.ollama.com/api/tags), [show model details](https://docs.ollama.com/api-reference/show-model-details), [usage](https://docs.ollama.com/api/usage), [Pydantic AI Ollama page](https://pydantic.dev/docs/ai/models/ollama/). All read 2026-11-23.

- **Local list:** `GET {base}/api/tags` returns `{"models":[{"name","model","modified_at","size","digest","details":{format,family,families,parameter_size,quantization_level}}]}`. Models that are remote (cloud models proxied through a local server) also carry `remote_model` and `remote_host`. The local API needs no authentication; the default base is `http://localhost:11434`, which inside our container is `host.docker.internal`.
- **Capabilities:** `POST {base}/api/show` with `{"model": "..."}` returns `capabilities` (the example shows `completion`, `thinking`, `vision`), `thinking` values, and `model_info` including `<architecture>.context_length`. We use it to warn when a model lacks a needed capability.
- **Cloud:** direct inference at `https://ollama.com/api` and `https://ollama.com/v1` requires an API key, created at ollama.com/settings/keys, sent as `Authorization: Bearer <key>`; keys do not expire and can be revoked. List models with `GET https://ollama.com/api/tags` and use the returned name (for example `gemma4:31b`); the `:cloud` names belong to a signed-in local Ollama.
- **Structured output:** self-hosted Ollama (0.5.0 and later) enforces JSON-schema output. **Ollama Cloud accepts `response_format` but does not enforce it**, so schemas are silently not applied. Pydantic AI raises a clear error for `NativeOutput` on cloud and works with its default `ToolOutput` or `PromptedOutput`. Blindspot therefore uses tool-call output with validation and bounded retries on cloud models.
- **Usage fields** (final streaming chunk): `prompt_eval_count`, `prompt_eval_cached_count`, `eval_count`, plus durations in nanoseconds. Local is free; cloud is plan or credit based (shown as tokens, "included in plan").

## Prompt caching strategy

Static prefix first: system prompt, methodology playbook, tool definitions, then per-run context, then the conversation. Every call records cache read and write tokens so the usage page shows what caching saved.

**Anthropic** ([docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)): minimum cacheable prompt is 512 tokens for Opus 5.5, Sonnet 5.5, Haiku 5.5 and Fable 5.2 (shorter prompts are processed without caching and without an error); up to four breakpoints per request; 5-minute and 1-hour lifetimes. Pydantic AI ([docs](https://pydantic.dev/docs/ai/models/anthropic/)) offers a unified `cache` setting, `anthropic_cache` (automatic), `anthropic_cache_instructions`, `anthropic_cache_tool_definitions`, `anthropic_cache_messages`, `CachePoint`, and reports `cache_read_tokens`, `cache_write_tokens`, `cache_write_1h_tokens`, `cache_hit_ratio`, with optional miss diagnostics.

**OpenAI** ([docs](https://developers.openai.com/api/docs/guides/prompt-caching)), GPT-5.6 and later including GPT-6: minimum 1,024 tokens; implicit mode or explicit mode (`prompt_cache_options.mode`, `prompt_cache_breakpoint`); up to four cache writes per request; stable `prompt_cache_key`. **Cache writes cost extra**: 1.25x input for the default 30-minute lifetime, 2.5x for 12 hours (Responses API). Reads are 0.1x input, or 0.05x on GPT-6.2 Astra, GPT-6.2 Sol, GPT-6.1 Sol and GPT-6.1 Terra. `cached_tokens` comes in multiples of 128.

**Ollama:** `prompt_eval_cached_count` is reported; passthrough via Pydantic AI's OpenAI-compatible path is to be measured.
