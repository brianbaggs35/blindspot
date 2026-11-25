<p align="center">
  <img src="docs/assets/logo.svg" alt="Blindspot: find what you cannot see" width="420">
</p>

# Blindspot

Blindspot is a self-hosted platform for **web application penetration testing with AI agents**. It follows the [OWASP Web Security Testing Guide](https://owasp.org/www-project-web-security-testing-guide/) (WSTG) test by test, shows you what has and has not been tested, and explains every result in plain language, with the raw tool output one click away for experts.

> **Use Blindspot only on systems you own or have written permission to test.** It can launch real attacks. The authors accept no liability for misuse. Read the [terms of use](DISCLAIMER.md) and the [acceptable use](ACCEPTABLE_USE.md) page; the app asks everyone to accept the terms before they can use it.

## Status

**Version 0.0.1, the foundation.** The container, sign-in, the secrets vault, the AI provider settings, the methodology engine with the WSTG checklist, and pentests with their authorization gate and checklist are built. The agents and the security tools are next, so Blindspot cannot run a test yet. See the [changelog](CHANGELOG.md) and [the plan](docs/PLAN.md); work is tracked on the BLI board in Jira, one ticket per pull request, as a stack of pull requests that can be merged in order.

## What it will do

- **Run a whole pentest**: black box, grey box or white box, with a guided form for scope, access, rules of engagement, written authorization and contacts.
- **Agents that mirror the methodology**: a Mission Commander, one agent per WSTG category (`WSTG-INFO`, `WSTG-ATHN`, ...), one sub-agent per test (`WSTG-INFO-01`, ...). Other methodologies (PTES, OSSTMM, ASVS) plug in as data.
- **Mission Control**: a live command center with a "blindspot radar" of what is untested, an attack-surface graph, an event stream, approvals, and an emergency stop.
- **Any security tool, safely**: nmap, nuclei, ffuf, sqlmap and more behind one sandboxed, permissioned, scope-checked path, with an optional Docker runner for stronger isolation.
- **Results anyone can read**: friendly, technical and raw views; findings linked to CVEs with EPSS and CISA KEV priority.
- **Your choice of AI**: Anthropic, OpenAI, and Ollama (local and cloud), with prompt caching, token and cost tracking per agent and per run.
- **Secure by design**: one hardened container (nginx with TLS, API, PostgreSQL 18 on a unix socket), passkey sign-in, secrets encrypted at rest.

## Documentation

|                                                                 |                                                                                                                         |
| --------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| [Changelog](CHANGELOG.md)                                       | What changed in each version                                                                                            |
| [Contributing](docs/how-to/contributing.md)                     | Tickets, branch names, one-line commits, stacked pull requests, what must pass and how to release                       |
| [Continuous integration](docs/how-to/ci.md)                     | Every CI workflow and check, how to run them locally, branch protection setup                                           |
| [Running the container](docs/how-to/container.md)               | Start it, ports, certificates, what is stored where, and how it is locked down                                          |
| [The database](docs/how-to/database.md)                         | The socket, the shared columns, sessions, migrations and how to add a table                                             |
| [Accounts and sign-in](docs/how-to/accounts.md)                 | First-run setup, passwords, sessions, roles, lockout, CSRF and the audit trail                                          |
| [Secrets and the vault](docs/how-to/secrets.md)                 | How credentials are sealed, the app secret key, rotating it, and what logs never show                                   |
| [AI providers and spend](docs/how-to/ai-providers.md)           | Provider kinds, sealed keys, the address guard, test and fetch models, prompt caching, prices and budgets               |
| [Methodologies](docs/how-to/methodologies.md)                   | WSTG import, playbooks, adding a methodology as files, reviewed updates and the API                                     |
| [Pentests](docs/how-to/pentests.md)                             | What a pentest holds, how scope is written and compiled, clone, trash, export and the API                               |
| [The app shell](docs/how-to/app-shell.md)                       | The look, the menu, the command palette, effects, sign-in and account pages, users and the audit log                    |
| [Tools](docs/how-to/tools.md)                                   | Tool manifests, safe command lines, the registry, the core tool pack, parsers, the scope guard, permissions and the API |
| [Terms and warnings](docs/how-to/terms.md)                      | The terms of use screen, how acceptance is kept and enforced, and the legal files in the repository                     |
| [Platform plan](docs/PLAN.md)                                   | Architecture, agents, tools, security, UI, CI, the PR stack and open questions                                          |
| [Agent framework comparison](docs/research/agent-frameworks.md) | Why Pydantic AI, and what else was considered                                                                           |
| [How pentest agents are built](docs/research/pentest-agents.md) | What open-source projects do, and what Blindspot borrows                                                                |
| [WSTG tool map](docs/research/wstg-tool-map.md)                 | Every one of the 133 WSTG tests mapped to verified tools, plus the tools rejected as stale                              |
| [Models and pricing](docs/research/models-and-pricing.md)       | Verified model IDs, prices and caching rules for Anthropic, OpenAI and Ollama                                           |

How-to guides (quick start, running your first pentest, providers, operations) are added to `docs/` with the features they describe.

## Contributing

Every change starts with a Jira ticket on the BLI board. Branch names, commit subjects and PR titles start with the ticket key, for example `BLI-5-scaffold`, and commit messages are a single line such as `BLI-5 Scaffold backend and frontend`. The full rules, and what CI checks, are in [Contributing](docs/how-to/contributing.md).

## License

Blindspot is released under the [Apache License 2.0](LICENSE).
