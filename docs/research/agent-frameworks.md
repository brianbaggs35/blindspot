# Agent framework comparison

_Verified 2026-11-23. Versions, release dates and release counts come straight from the PyPI JSON API. Star counts come from one third-party snapshot and were not checked against GitHub (see "What I could not verify")._

## The question

Pick the most advanced open-source agent framework that is actively developed and widely used, and that works with Anthropic, OpenAI and Ollama (local and cloud), reports token and cache usage, and fits a Python 3.14 container.

## Comparison

| Framework | Latest | Released | Releases in last 6 months | Python | Notes |
| --- | --- | --- | --- | --- | --- |
| **Pydantic AI** | 2.71.0 | 2026-11-19 | 101 | 3.11+ | Stable v2 since 2026-06-23. Typed, schema-validated output; native Anthropic, OpenAI and Ollama support; usage objects with cache read/write tokens; MCP; OpenTelemetry. |
| LangGraph | 1.2.24 | 2026-11-20 | 23 | 3.10+ | Best-in-class durable graph execution and human-in-the-loop interrupts. Sits on the LangChain ecosystem; provider usage metadata is less uniform. |
| OpenAI Agents SDK | 0.25.0 | 2026-11-18 | 24 | 3.10+ | Thin and well designed, but pre-1.0 and OpenAI-first; other providers go through adapters. |
| Claude Agent SDK | 0.2.187 | 2026-11-20 | 99 | 3.10+ | The loop behind Claude Code. Claude-only, so it cannot meet the multi-provider requirement. |
| CrewAI | 1.15.44 | 2026-11-19 | 210 | **<3.14**, 3.10+ | Very popular role-based crews. Its `requires_python` excludes 3.14, which our container uses. |
| AG2 (AutoGen) | 1.3.4 | 2026-11-22 | 24 | 3.11+ | Conversation-centred multi-agent. Less suited to a deterministic, auditable orchestrator. |
| Agno | 3.2.1 | 2026-11-17 | 70 | 3.9+ | Active; teams and memory built in; smaller ecosystem for typed validation. |
| Google ADK | 2.15.0 | 2026-11-20 | 34 | 3.11+ | Gemini-first. |
| smolagents | 1.26.0 | 2026-05-29 | 1 | 3.10+ | Effectively stalled (one release in six months). Excluded. |

Third-party star snapshot (about November 2026, treat as indicative): CrewAI ~60.8k, LangGraph ~44.8k, OpenAI Agents SDK ~30.6k, Pydantic AI ~21.1k.

## Recommendation: Pydantic AI 2.x

1. **Provider neutrality.** First-class Anthropic, OpenAI and Ollama (local and cloud) models behind one `Agent` API, so the provider layer is a thin settings concern.
2. **Structured output by default.** Every agent step returns a validated Pydantic model, which is exactly the rule that model output is untrusted input and must be parsed against a schema.
3. **Accurate usage accounting.** `RunUsage` exposes input, output, cache-read and cache-write tokens per run, which feeds the AI usage page and cost ledger.
4. **Active and stable.** 101 releases in six months, stable v2 since June 2026, MIT licensed, Python 3.14 compatible.
5. **Fits our architecture.** It is a library, not a runtime. We keep the mission state machine, scope guard and approval policy as our own deterministic code in PostgreSQL, and use Pydantic AI for the model loop, tool calling, MCP and tracing.

### Why not the others

- **LangGraph** is the strongest alternative and the one to switch to if we later want its checkpointer. We would still need our own safety layer, and its heavier abstraction buys little when the mission state already lives in our database.
- **CrewAI** has the most stars but cannot install on Python 3.14 today.
- **Claude Agent SDK** and **OpenAI Agents SDK** are each tied to one vendor.

## What I could not verify

- Star counts against GitHub itself, and monthly download counts (pypistats was not reachable from the build environment).
- Pydantic AI durable-execution integrations (not needed for our design, which keeps mission state in PostgreSQL).
- Whether Ollama's cached-token count passes through Pydantic AI's OpenAI-compatible path; measured in the provider ticket.

**Verified since the first draft** from the Pydantic AI docs: a unified `cache` setting, Anthropic cache settings (`anthropic_cache`, `anthropic_cache_instructions`, `anthropic_cache_tool_definitions`, `anthropic_cache_messages`, `CachePoint`), usage fields `cache_read_tokens`, `cache_write_tokens` and `cache_hit_ratio`, an `OllamaModel` for local and cloud, and the Ollama Cloud limitation on JSON-schema output (use `ToolOutput` or `PromptedOutput`).

## Sources

- PyPI JSON API for each package, queried 2026-11-23.
- [Pydantic AI v2 announcement](https://pydantic.dev/articles/pydantic-ai-v2) and [usage API docs](https://pydantic.dev/docs/ai/api/pydantic-ai/usage/).
- [Choosing an agent framework in 2026 (Speakeasy)](https://www.speakeasy.com/blog/ai-agent-framework-comparison) and [Agent frameworks in mid-2026 (The Agent Report)](https://the-agent-report.com/2026/07/ai-agent-frameworks-comparison-2026-langgraph-crewai-autogen/) for star snapshots and positioning.
