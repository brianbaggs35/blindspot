<p align="center">
  <img src="docs/assets/logo.svg" alt="Blindspot: find what you cannot see" width="420">
</p>

# Blindspot

Blindspot is a self-hosted platform for **web application penetration testing with AI agents**. It follows the [OWASP Web Security Testing Guide](https://owasp.org/www-project-web-security-testing-guide/) (WSTG) test by test, shows you what has and has not been tested, and explains every result in plain language, with the raw tool output one click away for experts.

> **Use Blindspot only on systems you own or have written permission to test.** It can launch real attacks. The authors accept no liability for misuse. See the [disclaimer section of the plan](docs/PLAN.md#127-authorization-and-no-liability-warnings).

## Status

**Planning.** Nothing is built yet. [The plan](docs/PLAN.md) is waiting for approval; work is tracked on the BLI board in Jira, one ticket per pull request, as a stack of pull requests that can be merged in order.

## What it will do

- **Run a whole pentest**: black box, grey box or white box, with a guided form for scope, access, rules of engagement, written authorization and contacts.
- **Agents that mirror the methodology**: a Mission Commander, one agent per WSTG category (`WSTG-INFO`, `WSTG-ATHN`, ...), one sub-agent per test (`WSTG-INFO-01`, ...). Other methodologies (PTES, OSSTMM, ASVS) plug in as data.
- **Mission Control**: a live command center with a "blindspot radar" of what is untested, an attack-surface graph, an event stream, approvals, and an emergency stop.
- **Any security tool, safely**: nmap, nuclei, ffuf, sqlmap and more behind one sandboxed, permissioned, scope-checked path, with an optional Docker runner for stronger isolation.
- **Results anyone can read**: friendly, technical and raw views; findings linked to CVEs with EPSS and CISA KEV priority.
- **Your choice of AI**: Anthropic, OpenAI, and Ollama (local and cloud), with prompt caching, token and cost tracking per agent and per run.
- **Secure by design**: one hardened container (nginx with TLS, API, PostgreSQL 18 on a unix socket), passkey sign-in, secrets encrypted at rest.

## Documentation

| | |
| --- | --- |
| [Platform plan](docs/PLAN.md) | Architecture, agents, tools, security, UI, CI, the PR stack and open questions |
| [Agent framework comparison](docs/research/agent-frameworks.md) | Why Pydantic AI, and what else was considered |
| [How pentest agents are built](docs/research/pentest-agents.md) | What open-source projects do, and what Blindspot borrows |
| [Models and pricing](docs/research/models-and-pricing.md) | Verified model IDs, prices and caching rules for Anthropic, OpenAI and Ollama |

How-to guides (quick start, running your first pentest, providers, operations) are added to `docs/` with the features they describe.

## Contributing

Every change starts with a Jira ticket on the BLI board. Branch names, commit subjects and PR titles start with the ticket key, for example `BLI-5-scaffold`, and commit messages are a single line such as `BLI-5 Scaffold backend and frontend`.
