<p align="center"><img src="assets/logo.svg" alt="Blindspot" width="420"></p>

# Blindspot: platform plan

_Status: **proposal, waiting for approval.** Nothing in this plan has been built. Written 2026-11-23. Facts about versions, models, prices and APIs were checked on that date against registries, vendor documentation and live API responses; anything I could not verify is marked **(unverified)** and listed in [section 21](#21-open-questions-and-things-i-could-not-verify)._

> **Use only on systems you own or have written permission to test.** Blindspot can launch real attacks. The authors accept no liability for misuse (see [section 12.7](#127-authorization-and-no-liability-warnings)).

## Contents

1. [What Blindspot is](#1-what-blindspot-is)
2. [Decisions at a glance](#2-decisions-at-a-glance)
3. [Architecture](#3-architecture)
4. [Technology stack](#4-technology-stack)
5. [The agent system](#5-the-agent-system)
6. [Pentest types and the new-pentest form](#6-pentest-types-and-the-new-pentest-form)
7. [Tools: execution, isolation and permissions](#7-tools-execution-isolation-and-permissions)
8. [Results anyone can understand](#8-results-anyone-can-understand)
9. [CVE, EPSS and KEV enrichment](#9-cve-epss-and-kev-enrichment)
10. [AI providers, models, caching and cost](#10-ai-providers-models-caching-and-cost)
11. [Methodologies are plugins](#11-methodologies-are-plugins)
12. [Security model](#12-security-model)
13. [Reliability: error handling and idempotent migrations](#13-reliability-error-handling-and-idempotent-migrations)
14. [UI and UX: the command center](#14-ui-and-ux-the-command-center)
15. [Pages](#15-pages)
16. [Data model](#16-data-model)
17. [Quality gates and CI](#17-quality-gates-and-ci)
18. [Repository layout and documentation plan](#18-repository-layout-and-documentation-plan)
19. [The PR stack](#19-the-pr-stack)
20. [Risks](#20-risks)
21. [Open questions and things I could not verify](#21-open-questions-and-things-i-could-not-verify)
22. [Sources](#22-sources)

---

## 1. What Blindspot is

Blindspot is a self-hosted platform where one person can run a complete web application penetration test, from scoping to a finished report, with a team of AI agents doing the legwork and a human holding the controls.

- **It follows a methodology, not a hunch.** OWASP WSTG ships first: 13 categories and 133 tests, imported from the official `checklist.json`. Other methodologies (PTES, OSSTMM, OWASP ASVS) plug in as data.
- **Agents mirror the methodology.** A Mission Commander runs one agent per category (`WSTG-INFO`, `WSTG-ATHN`, ...), and each category agent runs one sub-agent per test (`WSTG-INFO-01`, ...). Coverage is measured per test.
- **The name is the feature.** The central Mission Control view is a *blindspot radar*: every test is a segment; tested ones light up, untested ones glow amber. You always see what has **not** been looked at.
- **Safe by construction.** Scope, risk level, approvals and budgets are enforced by deterministic code the model cannot override. Nothing runs before a written-authorization attestation.
- **Understandable by default.** Every tool result has a plain-language view for anyone, a technical view, and the raw output for experts.
- **One container.** nginx with TLS, the API, PostgreSQL 18 (unix socket, no TCP) and the web app in one hardened image. Optional isolated tool containers for stronger sandboxing ([section 7](#7-tools-execution-isolation-and-permissions)).

### Who it is for

| Person | What they need |
| --- | --- |
| Solo pentester / consultant | Faster coverage, evidence collected automatically, a report that writes itself |
| Internal security team | Repeatable runs, retests, findings tracked to fixed |
| Developer or founder with no security background | Plain-language results, clear "what to do", guardrails that stop mistakes |

### Non-goals for v0.1

Multi-tenant SaaS, scheduled continuous scanning, non-web targets (network, mobile, cloud accounts), and autonomous destructive exploitation. These are listed so nobody is surprised; each can be a later epic.

---

## 2. Decisions at a glance

| Topic | Recommendation | Why (short) |
| --- | --- | --- |
| Agent framework | **Pydantic AI 2.x** with our own deterministic mission engine | Multi-provider, typed outputs, per-call cache/token usage, very active, Python 3.14 compatible. [Comparison](research/agent-frameworks.md) |
| UI library | **Vuetify 4** (Material Design 3) | You suggested it, AresGate already uses it, best-in-class data tables, theming and accessibility. Alternative: PrimeVue 5 (see [open questions](#21-open-questions-and-things-i-could-not-verify)) |
| Language versions | Python 3.14, **TypeScript 6.0.3**, Vue 3.5, Vite 8 | npm's current `latest` is TypeScript **7.0.2**; we pin 6 as requested and track 7 in a ticket |
| Database | PostgreSQL 18 over a **unix socket**, peer authentication, no TCP listener | No password to leak, nothing to attack over the network |
| Web server | nginx mainline, TLS 1.3, Let's Encrypt or bring-your-own | As requested |
| Secrets | AES-256-GCM sealing with HKDF per-purpose keys; Argon2id password hashes; passkeys | Passwords are hashed (one-way), API keys and credentials encrypted (reversible only with the app key) |
| Tool isolation | **Pluggable runner**: in-container sandbox by default, **optional Docker runner** through a restricted socket proxy | Keeps the "one container" promise while allowing real per-tool isolation. Needs your decision, see [7.2](#72-where-tools-run-the-single-container-question) |
| Tool run modes | Per tool, you choose **Local** (inside the Blindspot container) or **Docker** on a new **Tools settings** page, with a global default | You asked for control over how tools run. Decided: hybrid runner ([7.2](#72-where-tools-run-the-single-container-question)) |
| Tool images | Blindspot publishes signed, digest-pinned **tool-pack images** and **pulls them automatically** when a Docker-mode tool is first needed | No manual `docker pull`; pinned digests mean what runs is what was tested ([7.6](#76-docker-images-pulled-automatically-and-safely)) |
| WSTG coverage | All **133 tests** mapped to tools, test by test, with replacements for stale tools | [Tool map](research/wstg-tool-map.md), summary in [7.7](#77-complete-wstg-tool-coverage) |
| Roles | **Two only: admin and viewer** (viewer is read only), enforced on the API and the UI | As requested ([12.2](#122-accounts-passkeys-and-sessions)) |
| Dependencies | Latest stable of everything except TypeScript (6.x); no stale or unmaintained packages | [Policy and exceptions](#dependency-policy) |
| CVE data | NVD (records) + CISA KEV + EPSS + OSV, CIRCL as no-key fallback, all cached locally | Free, authoritative, rate-limit friendly |
| Quality | pytest and Vitest at 100% target (CI floor 95%); Playwright floor 80%, aiming 90%+; Sonar, CodeQL, zizmor, Trivy, bandit, ruff, hadolint, Prettier | As requested, modeled on the AresGate CI you referenced in BLI-1 |

---

## 3. Architecture

### 3.1 The container

```
                      https (443) / http redirect (80)
                      (inside: 8443 and 8080, so no capability is needed)
                                   │
 ┌─────────────────────────────────▼───────────────────────────────────────┐
 │ blindspot container  (Chainguard Wolfi, non-root, read-only rootfs)     │
 │                                                                         │
 │   s6 (supervision)                                                      │
 │    ├─ nginx (mainline)   TLS 1.3, security headers, rate limits,        │
 │    │                     serves the built Vue app, proxies /api + SSE   │
 │    ├─ api                FastAPI (uvicorn): REST + Server-Sent Events   │
 │    ├─ worker             mission engine: runs agents and tools          │
 │    └─ postgres 18        listen_addresses='' (unix socket only)         │
 │                                                                         │
 │   /run/postgresql  ◄── socket, group-restricted: api + worker only      │
 │   /data            ◄── volume: database, vault key, evidence, reports   │
 └──────────────┬─────────────────────────────────────────┬────────────────┘
                │ (default) in-container sandbox           │ (optional)
                ▼                                          ▼
      tool processes as `blindspot-tools`        docker-socket-proxy  ──►  ephemeral
      (caps dropped, rlimits, timeouts)          (allow-list of API calls)  tool containers
```

Processes (supervised by **s6**, which has no Python dependency; Wolfi's `supervisor` package pulls in a second Python, 3.13): **nginx** terminates TLS and serves the static web app. **api** handles requests and streams events to browsers. **worker** executes missions so a slow scan never blocks a request. **postgres** is the single source of truth. They talk through the database (`LISTEN/NOTIFY` for live events) and never through open network ports.

### 3.2 A test run, end to end

```
 user ──► New pentest (type, scope, access, RoE, authorization) ──► attestation stored
        ──► Deploy agents (profile, budget) ──► launch summary ──► confirm
 worker: Mission Commander plans ─► category agents (WSTG-INFO ...) in dependency order
          └─► test sub-agents (WSTG-INFO-01 ...), bounded parallelism
               ├─ policy check (scope guard + risk class + approval + budget)  ◄─ deterministic
               ├─ run tool (nmap, httpx, ffuf, nuclei, built-in Python tools ...)
               ├─ parser ► normalized result ► friendly / technical / raw views
               ├─ CVE enrichment (NVD, EPSS, KEV)
               └─ typed result: status, evidence, candidate findings, confidence
          └─► verifier agent replays evidence ► finding "confirmed" or "needs review"
 events ──► Postgres NOTIFY ──► SSE ──► Mission Control, Dashboard, Chat
 end    ──► findings + coverage ──► report (HTML, PDF, Markdown, JSON)
```

### 3.3 Why these choices

- **Server-Sent Events, not WebSockets.** One-way live data fits SSE, works through nginx without special upgrade handling, reconnects by itself, and is easy to test.
- **The worker is separate from the API** so a crash in a tool run cannot take down the web server, and so missions survive API restarts. Mission state lives in PostgreSQL, so a container restart resumes where it stopped.
- **Unix-socket PostgreSQL** is the pattern you already use in AresGate: `listen_addresses=''`, `local all all peer`, the API connects as its own OS user, so there is no database password at all. In Blindspot the socket directory is readable only by the `api` and `worker` users, so tool processes cannot reach the database even though they share the container.

---

## 4. Technology stack

Versions below were read from PyPI and npm on 2026-11-23. Each scaffold PR re-checks the registry before adding a dependency and never pins an old major from memory.

### Dependency policy

Your rule is: latest versions, nothing stale, nothing nobody uses, and TypeScript stays on 6 because 7 is not widely supported yet. This is how that is applied and enforced:

1. **Latest stable from the registry.** Every version in this plan was read from PyPI, npm, the Go module proxy or the Wolfi index, not from memory. The one deliberate exception is **TypeScript 6.0.3** (npm `latest` is 7.0.2), tracked in a ticket so the upgrade is a planned PR, not an accident.
2. **Maintenance.** A package needs a release in the last 12 months, or a documented exception. Libraries and tools whose newest release is older are rejected and replaced; the list is in the [tool map](research/wstg-tool-map.md#rejected-or-replaced-stale-unmaintained-or-not-redistributable).
3. **Adoption.** No near-zero-star or near-zero-download packages. Star counts need `api.deps.dev` and download counts need `api.npmjs.org` and `pypistats.org`, which are not on this session's allow-list yet. Until then adoption is recorded as *pending*, and the scaffold PR does not merge a dependency without that column filled in.
4. **Enforced in CI, not just once.** Dependabot (weekly), `pip-audit`, `npm audit`, OSV-Scanner and Trivy on every PR, and a small `dependency-freshness` check that fails when a pinned dependency has a newer stable release outside an allow-listed exception, or when its latest release is older than 12 months and it is not on the exception list.

Known exceptions, found while checking this list: `defusedxml` (last release 2021-03-08) is **dropped**; XML from tools is parsed with `lxml` 6.1.3 using a hardened parser (no entity resolution, no network, no DTD loading). `graphology` 0.26.0 (2025-01-26) is the current release and a required peer of sigma.js 4, so it stays, noted as a watch item. `argon2-cffi` 25.1.0 (2025-06-03) is the current release; the vault ticket checks whether the `cryptography` package's own Argon2 support makes it unnecessary. `httpx` is replaced by its maintained successor `httpx2` (see the note below).

### Backend

| Piece | Choice | Version |
| --- | --- | --- |
| Language | Python | 3.14 |
| API | FastAPI + uvicorn | 0.165.0 / 0.54.0 |
| Database access | SQLAlchemy (async) + psycopg 3 | 2.1.9 / 3.3.9 |
| Migrations | Alembic | 1.20.1 |
| Validation, settings | Pydantic, pydantic-settings | 2.14.4 / 2.16.3 |
| Agents | Pydantic AI (`pydantic-ai-slim` with Anthropic and OpenAI extras) | 2.71.0 |
| Provider SDKs | anthropic, openai | 2.12.0 / 3.57.0 |
| MCP client | mcp | 2.3.0 |
| Crypto | cryptography (AES-GCM, HKDF) / argon2-cffi | 50.0.2 / 25.1.0 |
| Passkeys | webauthn (py_webauthn) | 3.0.1 |
| Live events | sse-starlette | 3.7.1 |
| Logging | structlog | 26.1.0 |
| XML parsing (nmap etc.) | lxml with a hardened parser (replaces defusedxml, last released 2021) | 6.1.3 |
| Packaging | uv | 0.13.9 |
| Quality | pytest 9.2.0, pytest-asyncio 1.5.0, pytest-cov 7.1.0, pytest-recording 0.15.0 (vcrpy 9.4.2), ruff 0.17.6, pyright 1.1.414, bandit 1.9.4, pip-audit 2.10.1 | |

Note: `httpx` has had no release since 2024-12-06 (0.28.1). Its maintained successor **`httpx2`** (2.16.2, 2026-11-16, from the Pydantic team) is what Pydantic AI, the Anthropic and OpenAI SDKs, `mcp` and Starlette's `TestClient` now depend on, so the plain `httpx` risk no longer applies and our own outbound calls can use `httpx2`. The pentest HTTP client keeps `aiohttp` and `h2` because it needs raw request and response control.

### Frontend

| Piece | Choice | Version |
| --- | --- | --- |
| Framework | Vue (`<script setup lang="ts">`) | 3.5.46 |
| Language | TypeScript (pinned to 6.x as requested; latest on npm is 7.0.2) | 6.0.3 |
| Build | Vite + `@vitejs/plugin-vue` | 8.3.8 / 6.0.11 |
| UI | Vuetify (+ `vite-plugin-vuetify`) | 4.3.4 / 2.1.3 |
| State, routing | Pinia, Vue Router | 4.1.0 / 5.5.1 |
| Charts | ECharts + vue-echarts | 6.1.0 / 8.3.2 |
| Attack-surface graph | sigma.js (WebGL) + graphology | 4.0.6 / 0.26.0 |
| Agent hierarchy diagram | Vue Flow | 1.48.2 |
| Motion | motion-v (CSS and View Transitions first) | 2.13.0 |
| Optional 3D "cinematic mode" (lazy-loaded) | three | 0.187.0 |
| Raw output terminal | xterm.js | 6.0.0 |
| Code and JSON highlighting | shiki | 4.6.0 |
| Tests | Vitest 5.1.1, Vue Test Utils 2.6.0, Playwright 1.65.1, axe-core 4.14.1 + @axe-core/playwright 4.14.0 | |
| Lint, format, types | ESLint 10.15.0 (+ vuejs-accessibility 2.6.3, security 4.2.1), Prettier 3.10.1, vue-tsc 3.3.14 | |

Fonts (Inter and JetBrains Mono) are self-hosted: no CDN calls, so the strict CSP stays strict and the app works offline.

### Infrastructure

Chainguard Wolfi base image. Package names and versions read from the Wolfi x86_64 package index on 2026-11-23:

| Need | Wolfi package | Version |
| --- | --- | --- |
| Web server | `nginx-mainline` | 1.31.9 |
| Database | `postgresql-18` | 18.7 |
| Runtime | `python-3.14` | 3.14.10 |
| Frontend build stage | `nodejs-24` | 24.22.3 |
| Process supervisor | `s6` | 2.15.1.1 |
| Privilege dropping | `setpriv` | 2.42.4 |
| Tools available as packages | `nmap` 7.94, `nuclei` 3.11.1, `sqlmap` 1.10, `semgrep` 1.165.0, `gitleaks` 8.30.1, `osv-scanner` 2.7.1, `trivy` 0.70.0, `docker-cli` 29.10.0 | |
| **Not in Wolfi** | `ffuf`, `testssl.sh`, `lego` | see below |

`ffuf`, `testssl.sh` and `lego` are not packaged in Wolfi. Options, decided in the tool-pack ticket: download a pinned release with a checksum in a build stage (in-container runner), or use each project's official image through the Docker runner. Note `nmap` in Wolfi is 7.94, which is not the newest upstream release; the Docker runner can supply a newer one if needed. Certificate issuance can use a throwaway container for `lego` outside the app image (as `make cert` does in AresGate).

---
## 5. The agent system

### 5.1 Hierarchy: it mirrors the methodology

```
Mission Commander                                   one per mission
 ├─ Category agent  WSTG-INFO   Information Gathering          (9 tests)
 │    ├─ Test agent WSTG-INFO-01  Search engine reconnaissance
 │    ├─ Test agent WSTG-INFO-02  Fingerprint the web server
 │    └─ ...
 ├─ Category agent  WSTG-CONF   Configuration & Deployment     (14 tests)
 ├─ Category agent  WSTG-IDNT   Identity Management            (5)
 ├─ Category agent  WSTG-ATHN   Authentication                 (13)
 ├─ Category agent  WSTG-ATHZ   Authorization                  (5)
 ├─ Category agent  WSTG-SESS   Session Management             (11)
 ├─ Category agent  WSTG-INJT   Injection                      (27)
 ├─ Category agent  WSTG-ERRH   Error Handling                 (1)
 ├─ Category agent  WSTG-CRYP   Weak Cryptography              (4)
 ├─ Category agent  WSTG-BUSL   Business Logic                 (11)
 ├─ Category agent  WSTG-CLNT   Client-side                    (20)
 ├─ Category agent  WSTG-APIT   API Testing                    (10)
 └─ Category agent  WSTG-WASM   WebAssembly                    (3)
 Support roles: Verifier, Critic, Summarizer, Reporter, Chat assistant
```

The counts come from the real `checklist.json` (13 categories, 133 tests, read 2026-11-23). The hierarchy is **generated from whichever methodology is loaded**: a category in the data becomes a category agent, a test becomes a test sub-agent. Loading PTES or ASVS gives their own tree with no engine change.

A test sub-agent is not a separate hand-written program. It is created at run time from three things: the *agent role template* (shared behaviour), the *category settings* (tool grants, model profile, budgets) and the *test playbook* (objectives, evidence needed, preferred tools, what "not applicable" looks like). Hand-tuned playbooks are written for the highest-value tests first; the rest start from generated defaults that you can edit.

### 5.2 Responsibilities

| Role | Does | Does **not** |
| --- | --- | --- |
| Mission Commander | Reads scope, type and checklist; orders categories (recon first); splits budget; passes facts between categories; decides when the mission is done | Run tools itself |
| Category agent | Breaks its category into tests; schedules sub-agents with bounded parallelism; merges and de-duplicates results; writes the category summary and coverage | Exceed its budget or the pentest's risk class |
| Test sub-agent | Executes one test: plan, run tools, read results, decide next step, return a typed result | Touch anything outside scope; approve its own risky step |
| Verifier | Replays the evidence for each candidate finding independently; marks it confirmed, unconfirmed or false positive | Create findings |
| Critic | Reviews a test result for gaps ("did you try an authenticated request?") before it is closed | Run tools |
| Summarizer | Compresses long tool output into facts for other agents; writes the plain-language text shown to users | Decide severity |
| Reporter | Builds the report from confirmed findings | Invent evidence |
| Chat assistant | Answers questions about the live pentest; accepts extra information from the user | Launch tools without the same approvals |

### 5.3 State-of-the-art techniques, and where each is used

| Technique | How Blindspot uses it |
| --- | --- |
| **Plan, then act** | The methodology checklist is the plan (a "pentesting task tree"). Agents re-plan inside a test but cannot skip tests silently: every test ends in an explicit status |
| **Bounded parallelism** | Category and test agents run concurrently up to the pentest's concurrency and rate limits; recon blocks the categories that depend on it |
| **Shared memory: the target knowledge base** | Typed facts with provenance and confidence ("login is at /auth/login, session cookie `sid`, framework Express 4.18") in PostgreSQL. Agents read what others learned instead of re-discovering it. Full-text search first, `pgvector` later if measurements justify it |
| **Context compaction** | Long tool output is summarized into facts; raw output stays in storage and is cited by id |
| **Structured outputs everywhere** | Every step returns a Pydantic model; invalid output is retried a bounded number of times, then fails safe with a visible marker |
| **Self-verification** | A separate verifier replays evidence; "confirmed" means demonstrated, not suspected. This is the main false-positive control |
| **Reflection** | A critic pass before a test closes; capped to one round to bound cost |
| **Model routing** | Cheap fast model (for example Haiku 5.5 or `gpt-6-luna`) for parsing, triage and summaries; strong model (Sonnet 5.5, Opus 5.5, `gpt-6.2-sol`) for planning and exploitation reasoning; configurable per role |
| **Prompt caching** | Static prefix first (system prompt, playbook, tool definitions), then run context; cache read/write tokens tracked ([section 10](#10-ai-providers-models-caching-and-cost)) |
| **Adaptive thinking** | Anthropic adaptive thinking and effort per role; OpenAI reasoning level per role |
| **MCP tools** | External MCP servers can be attached as tool sources, under the same permission model |
| **Human in the loop** | Approval gates for active and intrusive steps; the user can pause, redirect, or answer an agent's question mid-run |
| **Durable execution** | Missions, tasks, steps and events are rows in PostgreSQL; the worker resumes after a restart without re-running finished tool calls (idempotency keys) |
| **Evaluation** | Recorded-LLM cassettes in CI, plus labelled runs against intentionally vulnerable apps (for example OWASP Juice Shop and DVWA): precision, recall and F1 reported. Prompts and thresholds change only with a measurement |

### 5.4 Deterministic safety owns the outcome

The model proposes; code decides. The policy engine checks every tool call:

1. **Scope guard**: the target resolves to something in the compiled allow-list (see [6.3](#63-the-scope-compiler)).
2. **Risk class**: the tool's class (passive, active, intrusive, destructive) is within the pentest's allowed class and the agent's grant.
3. **Approval mode**: auto, ask, or deny, per agent, tool and risk class.
4. **Budget**: steps, tokens, cost, wall-clock, request rate and concurrency are within limits.
5. **Kill switch**: global stop, per-pentest pause.

Model output can raise a finding's risk score. It can never lower a verdict that a rule set, and it can never widen scope, grant itself a tool, or skip an approval.

### 5.5 Lifecycle and states

`mission: draft → authorized → queued → running ⇄ paused → completing → complete | failed | cancelled`
`test: pending → running → (waiting_approval | blocked) → passed | failed | not_applicable | skipped | error`

Every transition is an event row (who, why, when). Retries are idempotent: a task has a stable key, and a duplicate key returns the existing task.

---

## 6. Pentest types and the new-pentest form

### 6.1 The three types, and what each needs

| | **Black box** | **Grey box** | **White box** |
| --- | --- | --- | --- |
| Tester starts with | Only the target address(es), like an outside attacker | Partial knowledge: test accounts and some documentation, like a customer or an insider | Everything: source code, configuration, architecture |
| Typical use | External exposure check, compliance-driven perimeter test | Most common for web apps: authenticated testing across roles | Deep review before release, or after a serious incident |
| Depth and cost | Lowest depth, least setup | Good depth for moderate setup | Deepest, most setup, finds logic and code flaws others miss |
| Blindspot adds | OSINT and recon-heavy agent profile, unauthenticated test paths | Per-role sessions, authorization (BOLA/IDOR) comparison across roles, API spec import | Repo import, static analysis, dependency (SBOM) scan, secret scan, code-assisted test planning |
| Main risk to handle | Limited coverage behind the login | Real accounts and real data | **Source code and secrets may be sent to an AI provider** |

(Definitions from vendor and training write-ups, see [sources](#22-sources); they agree on the gradient: black = nothing, grey = credentials or architecture but no code, white = code plus configuration.)

### 6.2 The new-pentest form (a guided wizard)

Required fields depend on the type. The server validates everything; the form guides.

**Step 1: Basics** (all types)
- Name; client or organization; **type** (black, grey, white); methodology and version (default WSTG); objectives (free text and checklist: "find auth flaws", "check OWASP Top 10", "pre-release review"); compliance driver (none, PCI DSS, SOC 2, ISO 27001, HIPAA, other); environment (production, staging, development); tags.

**Step 2: Targets and scope** (all types)
- In-scope: URLs, hostnames, wildcard domains, CIDR ranges, API base URLs; API description upload (OpenAPI, Postman collection, GraphQL schema).
- Out-of-scope: hosts, paths, functions to avoid (for example `/logout`, payment, "send email", "delete account").
- Third-party hosted components (CDN, identity provider, payment processor, cloud host): each needs an ownership/permission confirmation, because the target's owner cannot authorize testing someone else's service.
- The server shows **Blindspot's source IP** so the client can allow-list it in their WAF/IPS.

**Step 3: Access and knowledge** (changes by type)
- *Black box*: nothing required. Optional: known technology hints, whether to run OSINT.
- *Grey box*: **test accounts per role** (at least two roles recommended so authorization tests can compare), login URL and flow notes, how MFA is handled (test OTP seed, bypass token, or "out of scope"), session/token details, architecture notes, API documentation, data-sensitivity notes. Credentials are sealed in the vault the moment they are saved.
- *White box*: **source repository** (Git URL with a read-only deploy token, or an uploaded archive), branch or commit, languages and frameworks, build and run instructions, dependency manifests (or generate an SBOM), configuration files, architecture and data-flow diagrams, threat model if any. An explicit switch: **"Allow source code to be sent to the selected AI provider"** (off by default; if off, only local Ollama models read code).

**Step 4: Rules of engagement**
- Allowed risk class (passive, active, intrusive; destructive is off and needs an explicit extra confirmation).
- Technique switches: automated scanning, authenticated scanning, brute force and credential guessing (with attempt limits), file upload tests, denial-of-service testing (**off**, strongly discouraged), social engineering (**not supported**).
- Data handling: proof-of-access only (no bulk extraction), how to treat personal data found, whether to stop at first confirmation of a critical issue.
- Rate limits: requests per second per target, concurrency.
- **Testing window**: time zone, allowed hours and days, blackout dates (change freezes, peak periods), start/stop notification channel.
- Stop conditions: the events that pause everything (service degradation, unexpected data exposure, out-of-scope response, client request).

**Step 5: Authorization** (all types; required to launch)
- Authorizing party: name, title, organization, email; the date range the authorization covers.
- Upload the signed authorization or engagement letter (type and size limited).
- Backup confirmation for the target environment (checkbox plus system owner, as scoping checklists recommend).
- Attestation: the user types a confirmation sentence stating they hold written permission for **every** in-scope target. Stored with user, time, address and the text version, and printed on the report.

**Step 6: Contacts**
- Client technical contact; **24/7 emergency contact** (name, phone, email); tester lead; escalation path; who receives the report.

**Step 7: Agents and AI**
- Profile: *Passive recon only*, *Safe full assessment*, *Deep dive (asks before intrusive steps)*, or custom; model profile; budget caps (tokens, cost, time); the data-sharing consent for the chosen provider(s).

**Step 8: Review and launch**
- A plain-language summary of exactly what will run, against what, how hard, for how much; validation errors listed by step; **Launch** is disabled until authorization is complete.

### 6.3 The scope compiler

Turns the form into the allow-list the scope guard enforces: resolves names to addresses at compile time and re-resolves at call time (to catch DNS rebinding), normalizes IPv6 and punycode, rejects userinfo tricks (`https://good.example@evil.example`), follows redirects only inside scope, and always blocks the cloud metadata address, the container itself and loopback unless explicitly added. It is covered by adversarial unit tests.

### 6.4 CRUD

Pentests can be created, viewed, edited (scope changes after launch require a new attestation and are audited), archived, restored, cloned (credentials are not copied), and deleted (soft delete with a trash view and restore). Import and export as JSON (credentials excluded).

---

## 7. Tools: execution, isolation and permissions

### 7.1 One path for every tool

Agents never run commands. They request a **tool call**; the framework validates it, applies policy, runs it through a **runner**, stores raw output, parses it, and returns a normalized result.

A tool is described by a **manifest** (validated at load time):

```yaml
id: nmap
name: Nmap
risk: active                       # passive | active | intrusive | destructive
capabilities: [NET_RAW]            # only for SYN scans; otherwise none
image: ghcr.io/…/tool-nmap:<digest>   # Docker runner only; in-container uses the bundled binary
params:
  targets:   {type: scope_target[], required: true}
  ports:     {type: port_spec,  default: "top-1000"}
  scan:      {type: enum, values: [connect, syn, version], default: connect}
argv: ["nmap", "-oX", "-", "{scan_flag}", "-p", "{ports}", "{targets...}"]   # a list, never a shell string
timeout_s: 900
max_output_mb: 20
parsers: [nmap_xml]
explain: "Looks for open network doors (ports) on a server and what is listening behind them."
could_go_wrong: "Active scanning can trigger alerts and, rarely, upset fragile devices."
```

The complete tool set, with a verified version, source and risk class for each entry and a test-by-test assignment for all 133 WSTG tests, is in [research/wstg-tool-map.md](research/wstg-tool-map.md) (summary in [7.7](#77-complete-wstg-tool-coverage)). Tools come in four tiers: **built-in** Python tools with no external binary, **core** tools bundled in the app image, **pack** tools delivered as signed Docker images (or pinned installs), and **optional** tools you opt into.

**"Any and all tools":** administrators can add a custom tool from the UI (binary or image, argument template, parser: none, regex, JSON or XML). It passes through the same validation, scope guard, permissions and audit as built-in tools. External **MCP servers** can also be attached as tool sources.

### 7.2 Where tools run: the single-container question

You asked for a single container *and* for tools in Docker containers. These pull in opposite directions, so the runner is pluggable and I recommend a hybrid. **This needs your decision** (a decision card is attached to my reply).

| | A. In-container sandbox (default) | B. Docker runner (opt-in, recommended for production) | C. Docker-first only |
| --- | --- | --- | --- |
| How | Tool runs as an unprivileged user inside the one container: capabilities dropped with `setpriv`, `no-new-privileges`, rlimits, timeouts, cannot read the database socket | App talks to a **docker-socket-proxy** that allows only create/start/wait/logs/remove of containers from an allow-listed image set; each run is an ephemeral container: read-only rootfs, `cap_drop ALL` (+`NET_RAW` only for nmap SYN), CPU/memory/pids limits, dedicated network, no volumes except a scratch dir | Same as B but mandatory; no in-container tools |
| Single container? | **Yes** | App stays one container; tools are extra, short-lived containers | App plus socket proxy plus tool containers |
| Isolation | Good, shared kernel and filesystem namespace | **Best**: separate filesystem, network and process namespaces per run | Best |
| "Any tool" | Only what is in the image or `/data/tools` | **Any image**; image size of the app stays small | Any image |
| Setup | Zero | Needs Docker access; compose profile `tools` adds the proxy | Needs Docker access always |
| Main risk | A tool escape lands in the app container | Docker socket access is root-equivalent if the proxy is misconfigured; mitigated by the allow-list, a read-only proxy config, and tests that assert forbidden calls (privileged, host mounts, exec) are refused | As B, plus no zero-config mode |
| Works where Docker is unavailable | Yes | No | No |

**Recommendation: A + B behind one `Runner` interface.** Zero-config users get a safe, single-container product; people who want stronger isolation or arbitrary tools switch on the `tools` profile. The tool manifest, scope guard, permissions and parsers are identical in both, so there is one code path to test. Option C is available as a setting but not the default.

**Decided:** you chose the hybrid. One consequence worth stating: because Blindspot itself runs in a container, **"Local" means inside the Blindspot container** (bundled tools, or tools you install into the `/data/tools` volume), not programs installed on your host computer. Host-installed tools can be used through Docker mode (mount nothing, run the same image you would have installed) or, later, a small opt-in host agent. That is documented on the Tools page so nobody expects otherwise.

### 7.3 Permissions

A grant is the product of **agent role × tool × max risk class × scope × approval mode**.

| Risk class | Examples | Default approval |
| --- | --- | --- |
| Passive | DNS lookups, fetching public pages, header analysis | Auto |
| Active | Port scans, content discovery, nuclei templates | Ask once per mission (can be set to auto) |
| Intrusive | SQL injection exploitation, authentication brute force, file upload tests | **Always ask** |
| Destructive | Anything that modifies or deletes target data, denial of service | **Disabled**; needs a pentest-level opt-in and per-step approval |

The approval queue appears in Mission Control and as a notification; approvals show the exact command, target and reason. Every execution is audited (agent, exact argv, scope decision, approver, exit code, duration).

### 7.4 Resource safety

Wall-clock timeouts, output caps, process-group kill, CPU, memory and process limits, per-target request-rate limits, and a global **Emergency Stop** that cancels running tools within seconds.

### 7.5 The Tools settings page

Admins see a **Tools** settings page where they decide, per tool or globally, how each tool runs. Viewers can see it read-only.

| Control | Detail |
| --- | --- |
| **Global default** | Auto (use Local where bundled, else Docker), Prefer Local, Prefer Docker, or Docker only |
| **Per tool** | Enabled; mode Local or Docker; for Docker, the image reference and pinned digest (default from the release lock file, editable for advanced users); for Local, the binary path and detected version |
| **Status** | Ready, image missing, pulling (with progress), update available, verification failed, Docker unreachable, binary not found |
| **Test tool** | Runs the tool's version check through the chosen runner and shows the real command, output and timing |
| **Limits** | CPU, memory, timeout, output cap, per-target rate limit, maximum risk class, network (default: only the in-scope targets) |
| **Defaults** | Default arguments and wordlists, with per-pentest override |
| **Install and update** | Pull or update an image, import an image archive for air-gapped hosts, install a Local tool into `/data/tools` from a checksummed release |
| **Custom tools and MCP servers** | Add a tool manifest or an MCP server; same validation and permissions as built-in tools |

If a tool's chosen mode is unavailable (for example Docker is not reachable) the run is not silently switched: Blindspot shows what is wrong and offers the other mode as an explicit choice, and the pentest launch pre-flight lists every problem before an agent starts.

### 7.6 Docker images pulled automatically and safely

When a tool is set to Docker mode and its image is not present, Blindspot pulls it without you running `docker pull`.

- **Our own pack images.** The release pipeline builds tool packs on the Wolfi base from pinned upstream versions, as multi-arch images published to the project's container registry, each with a signature, an SBOM and a provenance attestation. A release ships a **lock file** (`tools/images.lock.json`) listing every image by **digest**. Blindspot pulls `repository@sha256:…`, never a floating tag, and refuses an image whose digest does not match the lock. Third-party images that are official (ZAP, Nikto) are pinned by digest in the same file, and are marked as third party in the UI.
- **When it pulls.** Pull on first use (default), pull all enabled tools at startup, or manual only. The pentest pre-flight shows "3 images to pull, about 1.2 GB" and lets you start the pulls immediately; a mission does not start with a missing image.
- **How it pulls.** Through the Docker Engine API (`POST /images/create` with the digest reference) behind the restricted socket proxy, which allows pulls only from allow-listed registries and only by digest. Progress streams to the page (layers, bytes). Failures are classified and shown: no network, registry unreachable, rate limited, unauthorized, not enough disk (checked before the pull), digest mismatch, signature invalid. Retries use backoff with jitter; a half-pulled image is never marked ready.
- **Registry settings.** Registry mirror, proxy and credentials for private registries (credentials stored sealed), and an offline mode that imports a tarball (`docker save` output) after verifying it against the lock file.
- **Updates.** New releases bring a new lock file. The page shows "update available" with the changelog; updating is a click, and an old image is garbage-collected after the new one is verified. Nothing updates itself in the middle of a mission.
- **What the proxy refuses.** Privileged containers, host mounts, host networking, exec into other containers, image build, and any image not in the lock file or the admin's explicit allow-list entry (which shows a warning and is audited).

### 7.7 Complete WSTG tool coverage

Every one of the 133 WSTG tests has an assigned tool set. The full table, with versions and sources, is [research/wstg-tool-map.md](research/wstg-tool-map.md); the shape of it:

| Tier | Count | Examples |
| --- | --- | --- |
| Built-in Python | 29 | Scoped HTTP client, instrumented Playwright browser, session/JWT/SAML/OIDC/WebAuthn analyzers, race-condition engine, HTTP desync prober, cache prober, injection probe set, WebAssembly analyzer, OAST listener |
| Core (bundled, Wolfi) | 11 | Nmap, Nuclei, sqlmap, gobuster, Amass, Hydra, grpcurl, WABT/wasm-tools/Binaryen/Wasmtime, Semgrep + Gitleaks + OSV-Scanner + Trivy + Syft + Grype, TruffleHog |
| Pack images | 16 | ProjectDiscovery recon suite, ffuf, Dalfox 3, testssl.sh, wafw00f, commix, SSTImap, Retire.js, GraphQL tools, Schemathesis, OSINT tools, ysoserial, Checkov, Wapiti, OWASP ZAP |
| Optional | 4 | Nikto (not redistributable, you pull the official image), WhatWeb, SearXNG, custom/MCP |

Findings that shaped the design: several popular tools are stale (for example `jwt_tool`, `Corsy`, `smuggler`, `regexploit`, `kiterunner`, `dnsReaper`) and are replaced by built-ins; techniques that exist only as Burp extensions (HTTP Request Smuggler, Param Miner, DOM Invader) are rebuilt as built-ins; some PyPI packages for live projects are years out of date (commix, theHarvester, S3Scanner), so packs install from pinned git tags; and Nikto's database files may only be distributed with the official package, so we do not bundle it. Business-logic tests are marked as agent-driven with human review rather than pretending a scanner covers them.

---

## 8. Results anyone can understand

Each tool result is parsed into one **normalized schema** (hosts, ports and services, HTTP responses, technologies, TLS findings, issues with severity and confidence, discovered credentials (sealed), artifacts) and shown in three views:

| View | Audience | Shows |
| --- | --- | --- |
| **Friendly** (default) | Anyone | Plain-language cards: "3 doors are open on this server: SSH (remote login), HTTPS (the website), and 8080 (an admin panel that should not be public)". Severity chips, **what this means / why it matters / what to do**, glossary tooltips, visuals (port map, TLS grade, header scorecard) |
| **Technical** | Practitioners | Structured tables from the schema: sortable, filterable, exportable |
| **Raw** | Experts | Verbatim output exactly as the tool printed it, the exact command line, exit code and duration; searchable, syntax-highlighted, copy and download |

Friendly text comes from **templates tested per parser**, so it is deterministic and free. An optional "Explain this simply" action asks the AI for a rewrite; it is opt-in because the data goes to the chosen provider, and cached. Sensitive values are sealed and masked until revealed (the reveal is audited).

**CRUD on results:** list and filter per pentest, create manual results (notes, imported Nmap/ZAP/Burp output), annotate and tag, promote to a finding, delete with restore.

---

## 9. CVE, EPSS and KEV enrichment

Findings are linked to public vulnerability records and prioritized by how likely they are to be exploited.

| Source | Gives us | Access (verified 2026-11-23) | Notes |
| --- | --- | --- | --- |
| **NVD CVE API 2.0** | Official CVE records, CVSS (v3.1 and v2 present in the sample record; v4.0 when scored), CWE, CPE configurations, and the CISA KEV fields on listed CVEs (`cisaExploitAdd`, `cisaActionDue`, `cisaRequiredAction`) | `GET https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=…` answered live (`format: NVD_CVE`, `version: 2.0`). Limits: **5 requests per rolling 30 seconds without a key, 50 with a free key**, key in the `apiKey` header (from NVD's developer pages as returned by search; the NVD site itself is a JavaScript app and returned 403 to my fetches) | Primary record source. Limits are per application, so all users of one install share them |
| **CISA KEV catalog** | "Known exploited in the wild" flag, due dates, ransomware use | JSON catalog, no key. The CISA feed and the `cisagov/kev-data` mirror returned identical files: `catalogVersion` 2026.11.20, `count` 1790; entries have `cveID`, `vendorProject`, `product`, `vulnerabilityName`, `dateAdded`, `shortDescription`, `requiredAction`, `dueDate`, `knownRansomwareCampaignUse`, `forensicTriage`, `notes`, `cwes` | Download daily, cache; the mirror is the fallback when the CISA host is unreachable |
| **FIRST EPSS** | Probability of exploitation in the next 30 days, and percentile | `GET https://api.first.org/data/v1/epss?cve=CVE-…` answered live: `{"version":"1.0","data":[{"cve","epss","percentile","date"}]}`; **values are strings** (for example `"0.999990000"`) | Parse as decimals; bulk daily file as a fallback |
| **OSV.dev** | Vulnerabilities for **package versions** (npm, PyPI, Maven, Go, ...) with ranges | `POST /v1/query`, `POST /v1/querybatch`, `GET /v1/vulns/{id}` (OSV docs); a record fetch answered live. **"Currently there are no limits on the API"**; responses over 32 MiB on HTTP/1.1 (no limit on HTTP/2) | Best source for white-box dependency scans |
| **CIRCL vulnerability-lookup** | Aggregated records from many sources, no key | `GET https://vulnerability.circl.lu/api/vulnerability/{id}` answered live with a CVE JSON 5 record (`dataType`, `cveMetadata`, `containers`) | Fallback and cross-check. Rate limits not documented in what I read; treat politely |

CVE ids are validated with `CVE-\d{4}-\d{4,}` (the live KEV data already contains six-digit sequence numbers).

**How a finding gets CVEs**

1. *Explicit*: a tool already names the CVE (nuclei, nmap NSE scripts): link it directly.
2. *By technology and version*: fingerprinting finds "nginx 1.18.0"; the product and version become a CPE-style query; matches are attached as **candidates** with confidence "version match" (not "exploited"). The verifier agent still has to demonstrate impact.
3. *By dependency* (white box): manifests go to OSV, results are matched to the code that imports them where possible.

Each CVE chip shows the id, CVSS, EPSS percentage, a **KEV** badge (with due date and ransomware flag), and a link out. A **priority score** combines severity, EPSS and KEV so that "known exploited and likely" rises to the top.

**Rate limits and caching.** A local cache in PostgreSQL (records 24 h, EPSS and KEV daily bulk refresh, with conditional requests), a token-bucket limiter per provider that honors NVD's window, and retry with backoff and jitter. The app still works offline from cache, and says when data is stale.

**Privacy.** Only public identifiers leave the machine: CVE ids, product names and versions. Never target hostnames, URLs or evidence. A setting turns external enrichment off completely (needs your sign-off, see [open questions](#21-open-questions-and-things-i-could-not-verify)).

---

## 10. AI providers, models, caching and cost

One `ModelProvider` interface; adding a provider is adding one module. Full tables with sources are in [research/models-and-pricing.md](research/models-and-pricing.md).

| Provider | Models | Notes |
| --- | --- | --- |
| **Anthropic** | `claude-opus-5-5` ($4 / $20 per MTok), `claude-sonnet-5-5` ($2 / $10), `claude-haiku-5-5` ($0.10 / $0.50, higher tier over 100K tokens); optional `claude-fable-5-2` ($8 / $40) | Cache reads cost 5% (Opus, Sonnet) or 10% (Haiku) of input. 1M context. Adaptive thinking, effort setting |
| **OpenAI** | `gpt-6-luna` ($0.10 / $0.50), `gpt-6.1-terra` ($1 / $5), `gpt-6.2-sol` ($2 / $10), `gpt-6.2-astra` ($8 / $40), plus `gpt-5.4-mini` | **Luna and Sol exist**, but the version number is part of the ID. The model list is fetched from the API, not hard-coded |
| **Ollama local** | Whatever you have pulled | **Fetch models** calls `GET {base}/api/tags` (`models[].name`, `size`, `digest`, `details`) and then `POST {base}/api/show` per model for `capabilities` (for example completion, thinking, vision) and `<arch>.context_length` in `model_info`. No authentication on the local API |
| **Ollama cloud** | Cloud-hosted models | Direct API at `https://ollama.com/api` and `https://ollama.com/v1`; key created at ollama.com/settings/keys and sent as `Authorization: Bearer`; model names come from `GET https://ollama.com/api/tags` (use that name, such as `gemma4:31b`; the `:cloud` names are for a signed-in *local* Ollama). **Cloud does not enforce JSON-schema output**, so cloud agents use tool-call or prompted output instead (Pydantic AI's `ToolOutput` or `PromptedOutput`) |

**Caching (verified in the vendors' docs).** Static prefix first (system prompt, playbook, tool definitions), then run context.

- **Anthropic**: minimum cacheable prompt is **512 tokens** for Opus 5.5, Sonnet 5.5, Haiku 5.5 and Fable 5.2; shorter prompts are silently not cached, so the usage page reports the cache result per call. Pydantic AI exposes a unified `cache` setting, `anthropic_cache` (automatic), `anthropic_cache_instructions`, `anthropic_cache_tool_definitions`, `anthropic_cache_messages` and `CachePoint` markers, with a maximum of four cache points per request (it trims extras), 5-minute or 1-hour lifetimes, and `usage.cache_read_tokens`, `cache_write_tokens`, `cache_write_1h_tokens` and `cache_hit_ratio`. Our default: cache instructions and tool definitions with `1h`, the rolling message prefix with `5m`.
- **OpenAI (GPT-5.6 and later, so the GPT-6 family)**: minimum **1,024 tokens**; implicit mode (OpenAI picks breakpoints) or explicit mode (`prompt_cache_options.mode`, `prompt_cache_breakpoint` on content blocks, up to four cache writes); a stable `prompt_cache_key` per mission. **Cache writes now cost extra**: 1.25x input for the default 30-minute lifetime, 2.5x for a 12-hour lifetime (Responses API); reads cost 0.1x, or 0.05x on GPT-6.2 Astra, GPT-6.2 Sol, GPT-6.1 Sol and GPT-6.1 Terra. `cached_tokens` is reported in multiples of 128. The cost model therefore charges writes, not only reads.
- **Ollama**: responses report `prompt_eval_count`, `prompt_eval_cached_count` and `eval_count` (final streaming chunk), so local cache reuse is visible; whether it passes through Pydantic AI's OpenAI-compatible path is checked in the provider ticket.

Every call stores input, output, cache-read, cache-write and thinking tokens, and the cost, so the usage page can show what caching saved.

**Cost control.** Per-agent, per-run and per-provider budgets with a hard stop; a catalog file of prices with a verified-on date and user overrides; unknown models show tokens with cost "unknown" rather than a guess. Ollama local is free; Ollama cloud is plan-based and shown as tokens.

**The settings page.** Add a provider, paste the key (stored sealed, shown as the last four characters), press **Test**, press **Fetch models** where relevant, choose defaults per agent role. Clear help text explains each step.

---

## 11. Methodologies are plugins

```
Methodology ─┬─ id, name, version, source, license
             └─ Category ─┬─ id (WSTG-INFO), name
                          └─ Test ─┬─ id (WSTG-INFO-01), name, reference URL, objectives[]
                                   └─ playbook: instructions, preferred tools, risk split,
                                      evidence required, "not applicable" rules
```

WSTG is imported from `checklists/checklist.json` (structure verified: `categories` → `{id, tests[{id, name, reference, objectives, cre_ids}]}`); the import is idempotent, snapshots are versioned, and updates show a diff before they apply. Other methodologies are files in `/data/methodologies` validated by a JSON Schema. A second sample methodology is loaded in tests to prove the abstraction.

**Adding a methodology** (PTES, OSSTMM, ASVS and others later) never touches core code. A methodology pack is a folder with:

| File | Purpose |
| --- | --- |
| `methodology.yaml` | id, name, version, source and license, categories and tests (validated by JSON Schema) |
| `tools.yaml` | the test-to-tool map, in the same format as the [WSTG map](research/wstg-tool-map.md); every test must list tools or a `manual-review` marker, enforced at import |
| `playbooks/` | optional hand-written playbooks per test; tests without one get generated defaults |
| `reporting.yaml` | how its categories appear in reports and the coverage radar |

The **tool registry** is separate and shared: a methodology only references tool ids, so adding a methodology that reuses nmap or Nuclei needs no new tool work, and adding a new tool makes it available to every methodology. ASVS requirement levels and PTES phases are modeled as categories and tags, so the agent hierarchy (Commander, one agent per category, one sub-agent per test) is generated from whichever methodology the pentest uses. Admins import packs from the Methodologies page; imports are idempotent and show a diff before applying.

---
## 12. Security model

### 12.1 Secrets: passwords are hashed, credentials are encrypted

| What | Protection | Reversible? |
| --- | --- | --- |
| User passwords | **Argon2id** (RFC 9106 low-memory profile), then keyed with an HMAC derived from the app secret (a pepper) | No (hash) |
| AI provider API keys, test-account credentials for targets, discovered credentials, tokens, evidence marked sensitive | **AES-256-GCM** with a random 96-bit nonce per value, versioned envelope (`v1:key-id:nonce:ciphertext`), **HKDF-SHA256** subkeys per purpose (providers, target credentials, discovered credentials, evidence) | Only with the app secret |
| Passkeys | Public keys only; private keys never leave the user's device | n/a |
| Session tokens | Random, stored hashed; cookies `HttpOnly`, `SameSite=Strict`, `Secure` | n/a |

- The **app secret key** is supplied through an environment variable, a file or a Docker secret, or generated on first start into `/data`. The generated option is convenient but sits next to the data, so the docs recommend supplying it and keeping a copy apart from backups.
- `make rotate-secret-key` re-seals every row in one transaction; `make secret-key` prints the key for safekeeping.
- Special column types (`SealedString`, `SealedJSON`) make it impossible to write a secret column in plaintext by accident.
- A test plants known secrets, then scans a full database dump, the logs, API responses and exports for them. A log and error redaction filter catches anything secret-shaped.
- Secrets are shown once as "last four characters". Revealing a stored credential is an explicit, audited action.

### 12.2 Accounts, passkeys and sessions

- **First run**: a setup page guarded by a one-time code printed in the container log. No default credentials, ever.
- **Sign in** with a password or a **passkey (WebAuthn)**. User verification is required, discoverable credentials and conditional-UI autofill are supported, challenges are single-use and expire in minutes, the relying-party id comes from the configured server name, sign-count regressions raise a warning (synced passkeys that report zero are tolerated). Adding or removing a passkey needs a recent re-authentication; up to 20 per account. Passkeys belong to the server name, so changing it invalidates them (documented).
- Lockout and rate limits per account and per address, constant-time comparisons, generic error messages (no user enumeration), optional TOTP second step.
- **Roles: exactly two.** **Admin** can do everything (create and run pentests, approve tool actions, change settings, manage users and secrets). **Viewer** is strictly read only: it can read pentests, results, findings, reports and usage, but cannot create, change, delete, launch, approve or export secrets, and sees credentials and API keys only as masked values. Enforcement is on the server for every route: each route declares a policy (`admin` or `viewer-ok`), a test fails the build if a route has none, and a test calls every non-GET route as a viewer and asserts 403. Mutating UI controls are hidden or disabled for viewers, but the server never relies on that. The chatbot and agents act with the permissions of the person who started them, so a viewer's chat cannot trigger tools or write to the knowledge base.
- **CSRF**: `Origin` and `Sec-Fetch-Site` checks on state-changing requests.
- **Audit log** of sign-ins, secret operations, setting and scope changes, approvals, tool executions and agent launches, with a filterable page.

### 12.3 Database over a unix socket

`listen_addresses = ''`, `unix_socket_directories = '/run/postgresql'` (mode 0770, group readable only by `api` and `worker`), `pg_hba.conf` contains only `local all all peer`, and each service connects as its own OS user with a matching database role. There is no password and no TCP port. A CI check asserts that nothing is listening on TCP. Because the connection string has no password, SonarQube's hard-coded-credential rule for the config file is addressed in `sonar-project.properties` with a documented ignore, as AresGate does.

### 12.4 TLS and web hardening

nginx mainline with TLS 1.3, HTTP redirects to HTTPS, a strict Content-Security-Policy (no inline scripts, no `unsafe-eval`; styles by per-request nonce, plus inline style _attributes_ only, which Vuetify sets and which cannot run script), `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, rate limits on `/api`, request-size limits, HSTS as an opt-in setting (it covers the whole host). Certificates: self-signed on first start; `make cert` and `make cert-renew` for Let's Encrypt (HTTP-01, or DNS-01 through a provider plugin); drop your own `fullchain.pem` and `privkey.pem` into `./certs`; a renewed certificate reloads without a restart; an expired one makes the container unhealthy.

### 12.5 Outbound safety (SSRF and data leaving the machine)

- Provider base URLs are validated; the local-Ollama private-address allowance is a provider-settings exception, never available to agent tools.
- Agent tools only reach what the scope guard allows.
- Only the minimum goes to an AI provider: no identities in prompts unless the design needs them; the white-box "send source to the AI" switch is off by default; a per-pentest data-sharing summary shows what each provider will see.
- Model output is untrusted input: parsed against a schema, length-bounded, malformed replies handled. No `eval`, no shell strings, subprocess arguments always a list.

### 12.6 Supply chain and CI security

**Chainguard (you have `CHAINGUARD_PULL_USERNAME` and `CHAINGUARD_PULL_PASSWORD` set as repository secrets).** The plan uses them in two places, and never prints or commits them:

1. **Base image.** Chainguard Wolfi (`cgr.dev/chainguard/wolfi-base`), as AresGate does. The CI reference passes the pull credentials only to a `docker/login-action` step for `cgr.dev` and skips the login when the secret is absent (fork PRs), because the base image is public.
2. **Python packages.** Chainguard Libraries for Python is an index at `https://libraries.cgr.dev/python/simple/` authenticated with a *pull token*; `uv` can read credentials from `UV_INDEX_<NAME>_USERNAME` and `UV_INDEX_<NAME>_PASSWORD` for an index named `<name>`. This is per Chainguard's documentation as returned by search; **I could not open Chainguard's docs from my environment (blocked hosts: `cgr.dev`, `libraries.cgr.dev`, `edu.chainguard.dev`, `www.chainguard.dev`, `support.chainguard.dev`)**, so these details are unverified. Open points: whether your existing pull credentials are entitled to the Python Libraries index (docs say a Python-specific pull token is created with `chainctl`), which of our dependencies Chainguard actually builds, and how the committed `uv.lock` behaves for contributors without credentials. See [open question 8](#21-open-questions-and-things-i-could-not-verify).

Everything else here: third-party GitHub Actions pinned to full commit SHAs, `permissions:` read-only by default, secrets only exposed to the steps that need them and never to fork PRs, no `pull_request_target` on untrusted code, zizmor on every workflow, Dependabot, dependency review, `pip-audit` and `npm audit`, Trivy on source and image, SBOM and signed provenance on releases.


### 12.7 Authorization and no-liability warnings

Shown where they matter, not buried:

- **First run**: terms screen (acceptable use, written-permission requirement, no warranty and no liability) that must be accepted; re-prompted when the text version changes.
- **New pentest**: banner at the top and in the Authorization step; launch is impossible without the attestation.
- **Launch dialog**: lists exactly what will run and against what, with the attestation.
- **Scope editor, tool settings, Agents deploy, chatbot, report export**: a short reminder.
- **README, docs, `LICENSE`, `DISCLAIMER.md`, `ACCEPTABLE_USE.md`, `SECURITY.md`.**

I am not a lawyer. The disclaimer wording and the license choice (I suggest Apache-2.0 for its explicit patent grant and warranty disclaimer) should be reviewed by Brian, ideally with counsel.

---

## 13. Reliability: error handling and idempotent migrations

### 13.1 Error handling

- **One error taxonomy.** Domain exceptions (`ValidationFailed`, `NotFound`, `Conflict`, `Forbidden`, `ScopeViolation`, `ApprovalRequired`, `BudgetExceeded`, `ProviderUnavailable`, `ToolFailed`, `Timeout`) each carry a stable machine code.
- **Clients get a generic, helpful message** in RFC 9457 `application/problem+json` form with a code and a request id. **Servers log the detail** (structured JSON with correlation ids across API, worker, tool and agent step). No stack trace ever reaches a client.
- **Every outside call has a timeout, bounded retries with exponential backoff and jitter, and a fallback**: providers, CVE APIs, Ollama, certificate renewal, repository fetches. A circuit breaker stops hammering a failing provider, and Mission Control says so.
- **Idempotency keys** on mission, task and tool-call creation, so retries and double clicks do not duplicate work.
- **Missions fail small.** A tool failure marks one test `error` with a reason and moves on; a provider outage pauses affected agents and offers a fallback model rather than killing the mission. Budget overruns stop work cleanly with a summary.
- **Graceful shutdown.** On stop, the worker finishes or checkpoints running steps, kills tool process groups, and records state; on start, it recovers abandoned steps (lease expiry) and resumes.
- **Background pollers** may swallow a transient failure but must log it; no silent catches in user-visible paths.
- **Frontend**: a request token on every fetch triggered by a prop, filter or route change (stale responses are dropped, loading flags cannot stick), error boundaries per page, designed loading/empty/error/success states, SSE with automatic reconnect and a visible "reconnecting" indicator, nothing polls while off screen.
- **Edges**: every JSON body is checked to be the expected shape, sizes and lists are bounded, NUL bytes are rejected before reaching PostgreSQL, numbers are range-checked.

### 13.2 Migrations that are safe to run twice

Rules every migration follows:

1. **Idempotent by construction.** Use `IF NOT EXISTS` / `IF EXISTS` or inspector checks via shared helpers (`ensure_table`, `ensure_column`, `ensure_index`, `ensure_constraint`), so re-running a migration on a database that already has its changes does nothing.
2. **One runner at a time.** Migrations run on container start under a PostgreSQL advisory lock, so two processes cannot migrate concurrently.
3. **Transactional DDL.** PostgreSQL supports it; each migration is all or nothing.
4. **Every new column needs a migration**, never only a model change (a `CREATE TABLE IF NOT EXISTS` change does nothing for existing installs).
5. **Expand, then contract.** Add new structures first, backfill in batches (resumable), switch readers, and drop old structures only in a later release. Never remove or rename a config option or narrow an enum.
6. **Seed data uses upserts** (`INSERT … ON CONFLICT DO UPDATE`), so importing the WSTG checklist twice is harmless.
7. **Backup before upgrading.** The container takes a `pg_dump` into `/data/backups` before applying a pending migration, keeps the last few, and prints how to restore.
8. **Never edit a shipped migration.** Fix forward.

Checks in CI (adapted from AresGate's CI):

- `alembic upgrade head`, then `alembic check` (fails if the models changed without a migration), then `downgrade base` and `upgrade head` again.
- **Re-apply the newest migration** to a database that already has it (stamp to its parent, upgrade, check): it must change nothing.
- **Upgrade from the previous release's schema** with data in it: old rows survive and every new read path works. A mutation test removes one migration line and confirms a test fails.
- Fresh install and upgrade jobs for the container; startup logs which migrations ran.

---

## 14. UI and UX: the command center

The goal is an interface that feels like a film-set operations room but behaves like well-made software: fast, readable, keyboard-friendly, and kind to people who are not security experts. Visual direction needs your approval: the app-shell PR starts with **two or three mock directions** and builds only the chosen one.

### 14.1 Design language

- **Dark "Midnight" (default) and light "Daylight"** themes built on the same tokens, plus system and high-contrast options. Surface near-black navy, accent **cyan to indigo** (the logo ring), **amber** reserved for blind spots and warnings, red for critical, green for passed.
- Type: Inter for text, JetBrains Mono for data, both self-hosted; a clear type scale and an 8-point spacing scale.
- Ambient detail with purpose: a faint radar grid, a slow sweep on the radar, glow on live items, number tickers, subtle scan-line transitions between pages (View Transitions API). Every effect obeys `prefers-reduced-motion` and a **Reduce effects** switch, costs nothing when off-screen, and is lazy-loaded.
- Motion budget: 150 to 250 ms, with a reason. No animation that hides information.
- Optional **Cinematic mode** (off by default, lazy-loaded): a WebGL view of the agent constellation and attack surface for demos and big screens. Everything it shows is also available in the plain 2D views.
- Optional audio cues: off by default.

### 14.1a Movie-grade, and easy to use

The look is a command system from a film; the behavior is a product anyone can drive. Both are requirements, and where they conflict, clarity wins.

- **Easy first.** A first-run tour, a launch wizard that explains each choice in plain language, sensible defaults, and a **Simple / Expert** switch: Simple shows the friendly views and one big "Launch" path; Expert exposes raw output, argv, per-agent settings and the event stream.
- **One visual language.** Glass panels on a faint radar grid, cyan-to-indigo energy for live things, amber only for blind spots and warnings, restrained motion that always means something (a ticking number, a sweep, a pulse on a new event).
- **Signature moments.** Boot sequence on launch, agents "coming online" in the hierarchy, the radar filling in as tests complete, an evidence reveal for each confirmed finding, a replay scrubber that plays a mission back like footage.
- **Craft checks in CI.** Axe on every route in both themes, visual-regression screenshots at 320, 390, 768, 1280 and 1920 px, performance budgets, and keyboard-only paths, so beauty cannot regress accessibility or speed.
- **Directions to choose from.** The app-shell PR brings two or three mock directions; nothing is built into the final look until you pick one.

### 14.2 Mission Control (the hero page)

```
┌ Mission: Acme storefront · GREY BOX · WSTG ──── ▶ RUNNING 00:42:17 ──── $3.41 / $10 ── [ ⏸ ] [ ■ EMERGENCY STOP ]┐
│ AGENTS (live tree)      │  BLINDSPOT RADAR                 │ LIVE EVENTS                            │
│ ▾ Commander   ●         │      ╭─ INFO ─╮                  │ 11:03:12 INFO-02  httpx → 200 nginx    │
│   ▾ INFO  9/9  ✔        │   CLNT ╱ rings = tests ╲ CONF    │ 11:03:14 ATHN-03  asks: run hydra?  [A][D]
│   ▾ ATHN  6/13 ●        │   sectors = categories   │       │ 11:03:20 INJT-05  nuclei started …     │
│     ATHN-03 ⏳ approval │   ▓ tested  ▒ running  ░ AMBER   │ ▸ finding: CORS wildcard on /api (M)   │
│   ▸ INJT  0/27 ○        │   = blind spot (not tested yet)  ├────────────────────────────────────────┤
│                         │   red = finding                  │ APPROVALS (1)  FINDINGS (4)  ERRORS (0)│
├─────────────────────────┴──────────────────────────────────┴────────────────────────────────────────┤
│ ATTACK SURFACE GRAPH (hosts · endpoints · tech · findings)   │ TOOL RUNS  nmap ✔ ffuf ● nuclei ●     │
│ TOKENS/min ▁▂▅▇▆▃  CACHE HIT 78%  COST/AGENT ▇▅▃▂           │ [view output: Friendly | Technical | Raw]
└──────────────────────────────────────────────────────────────┴───────────────────────────────────────┘
```

Panels: live agent tree with per-test status; **blindspot radar** (13 sectors, one ring per test position); **attack-surface graph** (sigma.js, WebGL) that grows as agents discover things; live event stream; approval queue with the exact command and reason; findings ticker; tool-run list with a streaming output drawer (friendly, technical, raw); token burn, cache hit rate and cost per agent; a **timeline scrubber** to replay the mission; pause, resume, and a big Emergency Stop. On phones the panels become tabs with the radar first.

### 14.3 Other signature touches

- **Command palette** (Ctrl/Cmd+K): jump to any page, pentest, finding or agent; run actions.
- **Collapsible navigation** rail (remembered, keyboard shortcut, tooltips when collapsed); bottom navigation and a sheet menu on phones.
- **Guided empty states** that say what to do next; skeleton loaders where the layout is known; celebratory but restrained success states (first confirmed finding, mission complete).
- **Glossary tooltips** on every security term in friendly views.

### 14.4 Accessibility, responsiveness, performance

- WCAG AA at minimum: 4.5:1 text contrast, 3:1 UI contrast, visible focus rings, every action from the keyboard, accessible names on icon buttons, never colour alone (the radar also uses patterns and an accessible table view).
- Container-query layouts; verified at 320, 360, 390, 600, 768, 1024 and 1280 px in both themes with no horizontal scroll; 16 px side gutters on phones.
- axe runs on every page in CI, diffed against the previous run; geometry is asserted with `getBoundingClientRect`.
- Routes are lazy-loaded, lists paginated, heavy visuals loaded on demand; a bundle-size budget is checked when dependencies are added. A view that is not on screen does no polling and holds no open stream.

---

## 15. Pages

| Page | Purpose | Highlights |
| --- | --- | --- |
| **Dashboard** | State of everything at a glance | Active missions, open findings by severity, coverage radar summary, spend today and this month, recent activity, "needs your attention" queue |
| **Pentests** | CRUD for engagements | Wizard from [section 6](#6-pentest-types-and-the-new-pentest-form), type-aware, trash and restore, clone |
| **Mission Control** | Run and watch a mission | See [14.2](#142-mission-control-the-hero-page) |
| **Agents** | See and deploy the hierarchy | Tree and grid, deploy flow with launch summary and estimated cost, presets |
| **Agent settings** | Tune each role, category or test | Model, effort, budgets, tool grants, approval mode, prompt versions with diff and history |
| **Tools** (settings) | Registry, run modes and permissions | Local or Docker per tool, image status and automatic pulls, test button, risk class, grants, limits, custom tools, MCP servers ([7.5](#75-the-tools-settings-page)) |
| **Results** | Everything the tools produced | Friendly / Technical / Raw toggle, full CRUD, promote to finding |
| **Findings** | The product of the test | CVSS 4.0 and 3.1 calculator, CWE and OWASP mapping, linked CVEs with EPSS and KEV, evidence, status workflow, retest, merge duplicates |
| **Checklist** | Methodology coverage | Every WSTG test with status and evidence links |
| **Targets & assets** | What was found | Hosts, endpoints, technologies, accounts |
| **Reports** | Deliverables | Templates (executive summary, technical, retest), HTML, PDF, Markdown and JSON export, attestation and scope printed |
| **AI usage** | Tokens and cost | Per provider, model, agent and run; cache savings; budgets and alerts; export |
| **Chatbot** | Talk to the pentest | See [15.1](#151-the-chatbot) |
| **AI providers** | Settings | Add keys, test, fetch Ollama models, defaults per role |
| **Settings, users, audit log, methodologies, about** | Administration | Two roles (admin, viewer), passkeys, sessions, certificates, secret key rotation, methodology packs, terms |

### 15.1 The chatbot

Fully integrated with the current pentest and the agents: it can read the mission, findings, results and knowledge base; explain a finding in plain language; and take **extra information from you** ("the admin panel is at /manage, ignore the staging subdomain") that is written to the knowledge base and passed to the right agents. It cannot run tools without the same approvals as any agent, and it shows what data it used. Answers cite the result or finding they came from.

---

## 16. Data model

Core entities (all with UUIDv7 ids, UTC timestamps, soft delete, created-by):

`user`, `session`, `passkey`, `audit_event` · `provider`, `model`, `usage_ledger` · `methodology`, `category`, `test`, `playbook` · `pentest`, `target`, `scope_rule`, `access_profile` (accounts, repo), `authorization_attestation`, `contact` · `mission`, `task`, `step`, `event`, `approval`, `agent_definition`, `prompt_version` · `tool`, `tool_setting` (mode, image digest, limits), `tool_image` (digest, status, pulled-at), `tool_grant`, `tool_run`, `result`, `knowledge_fact` · `finding`, `evidence`, `cve_record`, `finding_cve` · `report`.

---
## 17. Quality gates and CI

BLI-1 points at AresGate's workflows as a reference. I read `ci.yml`, `release.yml` and `zizmor.yml` from that repository and will tune them for Blindspot rather than copy them. Every job maps to a `make` target, so anything that fails in CI can be reproduced locally.

### 17.1 Workflows

| Workflow | Triggers | What it does |
| --- | --- | --- |
| `ci.yml` | every PR, push to `master`, manual | Jobs below; `concurrency` cancels superseded PR runs; `permissions: contents: read` by default; actions pinned to commit SHAs |
| `codeql.yml` | PR, push, weekly | CodeQL for Python, JavaScript/TypeScript and GitHub Actions |
| `zizmor.yml` | PR, push | Audits workflow files; results to code scanning; fails on findings |
| `release.yml` | GitHub release published | Validates the tag is on `master`; builds amd64 and arm64 natively; scans and smoke-tests each; pushes a multi-arch image to GHCR; signed provenance and SBOM |
| `pr-hygiene.yml` | PR | Fails unless the branch name, **every commit subject (one line)** and the PR title start with a `BLI-n` key |
| Dependabot, dependency review | schedule, PR | Updates for pip, npm, Docker, Actions; blocks risky new dependencies |

### 17.2 Jobs in `ci.yml`

| Job | Checks |
| --- | --- |
| **Backend** (Postgres 18 service) | `ruff check`, `ruff format --check`, `pyright`, `bandit`, `pip-audit`; migration checks ([13.2](#132-migrations-that-are-safe-to-run-twice)); `pytest` with branch coverage, **floor 95%, target 100%**; coverage XML uploaded for Sonar |
| **Frontend** | ESLint (`--max-warnings=0`, with security and accessibility rules), Prettier check, `vue-tsc`, **Vitest floor 95%, target 100%**, `npm audit` (fail on critical) |
| **Container** | hadolint, ShellCheck, actionlint; Trivy on source (vulnerabilities, secrets, misconfiguration) and on the built image, results to code scanning; start the stack with compose; smoke test; first-run setup and sign-in test; **restart on existing data**; secret-key tests (supplied key, short key refused); certificate tests (serve, renew, wrong, expired); **assert PostgreSQL has no TCP listener**; tool-sandbox test (capabilities dropped) |
| **End-to-end in the container** (3 shards) | Playwright against the built container, V8 coverage |
| **End-to-end on the runner** (3 shards) | Same specs without the container; a failure in only one points at nginx, TLS or the image |
| **End-to-end coverage** | Merges every shard's coverage; **fails below 80%, warns below 90%** (target 90%+) |
| **Dependency freshness** | Fails on a pinned dependency with a newer stable release (except TypeScript 6 and listed exceptions), or whose latest release is over 12 months old and not on the exception list; checks the tool lock file the same way ([policy](#dependency-policy)) |
| **Tool images** | Verifies every image in `images.lock.json` by digest and signature, and that each Docker-mode tool starts and prints its version |
| **Role policy** | Every route declares `admin` or `viewer-ok`; every non-GET route returns 403 for a viewer |
| **Accessibility** | axe on every page, both themes, four widths, diffed against the previous run |
| **SonarQube** | Needs backend and frontend jobs; scan with `-Dsonar.qualitygate.wait=true`; on failure **prints the list of open issues and hotspots** (as BLI-1 asks); fails the PR on any open issue in new code |
| **Upgrade** (planned once a release exists) | Start the previous release's image on data, upgrade, verify |
| **Timezone matrix** | Time-sensitive suites under two or three time zones |

### 17.3 SonarQube (BLI-2)

`sonar-project.properties` with `sonar.organization=brianbaggs35`, `sonar.projectKey=brianbaggs35_blindspot`; Python and TypeScript sources and tests declared separately; coverage reports `backend/coverage.xml` and `frontend/coverage/lcov.info`; migrations and CI scripts excluded from coverage (as AresGate does, because the migrations are exercised by the migration jobs). `SONAR_TOKEN` already exists as a secret. Automatic Analysis must be switched off in SonarQube Cloud because CI sends the analysis. Every finding is fixed; a `NOSONAR` or ignore rule needs your approval, a reason beside it and nothing else hidden by it.

### 17.4 Definition of done for every PR

Green CI, CodeQL and Sonar clean (quality gate passes, no open issues), duplication under 3%, **every GitHub Advanced Security thread fixed and resolved** after its alert closes, coverage thresholds met and changed lines covered, docs and README updated, branch and commit names carry the ticket key, one-line commit messages, linear history (rebase or squash; no merge commits).

### 17.5 Testing approach

Test through the real entry point (real route, real pipeline, real component); fake only the network boundary (recorded HTTP cassettes for provider calls). Reproduce a bug first and prove each regression test fails without the fix. Parametrize repeated cases. Never wait on fixed sleeps. No two test runs share one database. Route coverage: every registered route has a handler and a test, and every mounted component has a mounting test.

### 17.6 CI improvements worth raising

Path filters so docs-only PRs skip heavy jobs; Playwright browser caching; branch protection with required checks and no merge commits; `act` for fast local workflow checks (it does not replace a real hosted run).

---

## 18. Repository layout and documentation plan

```
blindspot/
├─ backend/            FastAPI app, worker, tools, agents, migrations, tests
├─ frontend/           Vue app, tests, e2e
├─ docker/             Dockerfile helpers, nginx, s6 services, entrypoint scripts
├─ methodologies/      bundled methodology packs (WSTG snapshot)
├─ tools/              tool manifests and parser fixtures
├─ .github/            workflows, scripts, dependabot, templates
├─ docs/               plan, research, how-to guides
├─ sonar-project.properties, docker-compose.yml, Makefile, LICENSE, DISCLAIMER.md, SECURITY.md, ACCEPTABLE_USE.md
└─ README.md
```

**docs/** grows with the code, each page linked from the README: quick start (install, certificates, ports, updates), running your first pentest, pentest types and the new-pentest form, agents and permissions, tools and the Docker runner, reading results, CVE enrichment, AI providers (keys, Ollama local and cloud), security and hardening, operations (backups, restore, key rotation, logs), development (running tests), releasing, methodologies (writing a pack), troubleshooting, FAQ. Docs change in the same PR as the behaviour they describe.

---

## 19. The PR stack

Every PR has a Jira ticket first, a branch named `BLI-n-short-name`, a **one-line** commit message starting with the key, and a title starting with the key. PRs are stacked: each is based on the branch beneath it, so you can merge them bottom-up once CI is green. Only the first PR (this plan) is open now; the rest wait for your approval.

Jira: [BLI board](https://brianbaggs.atlassian.net/jira/software/projects/BLI/boards/38). Epic: **BLI-3**. Tickets marked _to create_ are created when you approve, so the board is not cluttered with work we may reshape.

| # | Ticket | PR | Contents |
| --- | --- | --- | --- |
| 1 | BLI-4 | Plan, research, logo, README | This PR. Docs only |
| 2 | BLI-1 | CI pipeline (first build PR) | `ci.yml`, CodeQL, zizmor, actionlint, hadolint, release, Dependabot, PR hygiene, dependency-freshness check, Makefile targets. Path-aware: jobs for code that does not exist yet report "nothing to check" and a single required `ci-gate` job summarizes them, so this PR is green by itself and every PR after it runs the full pipeline |
| 3 | BLI-5 | Scaffold backend and frontend | uv, FastAPI health, Vue/Vuetify/TS 6 shell, ruff, pyright, bandit, ESLint, Prettier, vue-tsc, pytest and Vitest at 100%. First PR to run through the full CI |
| 4 | BLI-2 | SonarQube | `sonar-project.properties`, Sonar job with issue list |
| 5 | BLI-6 | Single container | Wolfi image, nginx TLS, s6, PostgreSQL 18 on a unix socket, compose hardening, hadolint, Trivy |
| 6 | BLI-7 | Playwright harness | Container and host modes, sharding, coverage merge, axe |
| 7 | BLI-8 | Database layer | SQLAlchemy, Alembic, idempotent migration helpers, advisory lock, pre-upgrade backup, migration CI checks |
| 8 | BLI-9 | Secrets vault | AES-256-GCM, HKDF, sealed column types, key rotation |
| 9 | BLI-10 | Sign-in | First-run setup, Argon2id, sessions, **admin and viewer roles** with route-policy tests, lockout, audit log |
| 10 | BLI-11 | Passkeys | WebAuthn registration and sign-in |
| 11 | BLI-12 | App shell | Design system, collapsible nav, themes, mobile, command palette, logo assets (after direction approval) |
| 12 | BLI-13 | AI providers | Anthropic, OpenAI, Ollama local and cloud, fetch models, pricing catalog, usage ledger, settings page |
| 13 | BLI-14 | Methodology engine | Pack format (`methodology.yaml`, `tools.yaml`, playbooks), WSTG import (133 tests), checklist pages |
| 14 | BLI-15 | Pentests | CRUD, black/grey/white wizard, scope compiler, authorization attestation |
| 15 | BLI-16 | Warnings and terms | Terms acceptance, banners, disclaimer files |
| 16 | BLI-17 | Tool framework | Manifests, tool registry, runner interface, Local in-container runner, scope guard, permissions, custom tools, MCP |
| 17 | _to create_ | Docker runner and automatic image pulls | Restricted socket proxy, ephemeral tool containers, digest-pinned lock file, pull with progress, signature check, offline import, forbidden-call tests |
| 18 | _to create_ | Tools settings page | Local or Docker per tool and globally, status, test button, limits, custom tools |
| 19 | BLI-18 | Core tool pack | Nmap, Nuclei, sqlmap, gobuster, Amass, Hydra and the other bundled tools, with parsers |
| 20 | _to create_ | Built-in analyzers, part 1 | Scoped HTTP client, instrumented browser, headers/cookies/CSP/CORS, TLS, DNS and takeover, crawler, parameter discovery |
| 21 | _to create_ | Built-in analyzers, part 2 | Session, JWT, SAML, OIDC, WebAuthn, CSRF, race engine, desync prober, cache prober, injection probe set, upload, GraphQL, gRPC, WebSocket, ReDoS, WebAssembly, OAST |
| 22 | _to create_ | Tool pack images and release pipeline | Pack Dockerfiles on Wolfi (recon, web, OSINT, ysoserial, Checkov), multi-arch build, cosign signatures, SBOM, `images.lock.json` |
| 23 | _to create_ | Optional engines | OWASP ZAP, Wapiti, Nikto (user pulls the official image), WhatWeb, SearXNG |
| 24 | _to create_ | White-box analysis pack | Repo import, Semgrep, Gitleaks, TruffleHog, OSV-Scanner, Trivy, Syft/Grype, Checkov, "send code to AI" gating |
| 25 | BLI-19 | Results pages | Friendly / Technical / Raw, full CRUD |
| 26 | BLI-20 | Agent runtime | Commander, category agents, per-test sub-agents, memory, verifier, evals |
| 27 | BLI-21 | Agents page and settings | Deploy, per-role settings, prompt versions |
| 28 | BLI-22 | Findings | CRUD, CVSS, evidence, verification, status workflow |
| 29 | _to create_ | CVE enrichment | NVD, KEV, EPSS, OSV, cache and rate limiting |
| 30 | _to create_ | Mission Control | Radar, graph, live events, approvals, replay |
| 31 | _to create_ | AI usage page | Tokens and cost by provider, agent, run |
| 32 | _to create_ | Dashboard | Overview and attention queue |
| 33 | _to create_ | Chatbot | Integrated chat with knowledge-base write-back |
| 34 | _to create_ | Reports | Templates and exports |
| 35 | _to create_ | Docs and README finish | How-to guides, screenshots, final links |

Order notes: **BLI-1 (CI) is the first build PR**, as you asked, so the scaffold and everything after it runs through the full pipeline before it is merged. Because the CI PR has no application code to check yet, its jobs are path-aware and report "nothing to check" until code exists; its own content (workflows, Dockerfile lint, docs formatting) is still checked by actionlint, zizmor, hadolint and Prettier. The tool work is split into reviewable slices (framework, Docker runner and pulls, settings page, built-ins, pack images, optional engines) instead of one giant tool PR. Mission Control is built after the runtime, findings and CVE enrichment so it shows real data.
---

## 20. Risks

| Risk | Mitigation |
| --- | --- |
| Misuse against systems you do not own | Attestation gate, scope guard, risk classes, audit log, terms, no destructive mode by default |
| An agent goes out of scope or too far | Deterministic policy engine, approvals, budgets, kill switch, tests that out-of-scope is denied at every layer |
| False positives erode trust | Verifier agent, "confirmed means demonstrated", evaluation on labelled targets |
| Source code or secrets sent to a third-party model | Off by default, per-pentest consent, local Ollama option, minimum-data rule, redaction |
| Cost surprises | Budgets with hard stops, estimates before launch, per-agent and per-run ledger |
| Docker socket access is powerful | Optional, behind a restricted proxy with an allow-list and tests; default is the in-container sandbox |
| Third-party APIs change or rate-limit | Local cache, token buckets, provider fallbacks, stale-data banner |
| Model and price churn | Catalog file with dates and user overrides; model lists fetched from APIs |
| Scope creep: 36 PRs is a lot | Strict vertical slices; each PR runs on its own; the early foundation PRs make later ones small |
| `httpx` has had no release since 2024-12-06 | Resolved: the ecosystem moved to its successor `httpx2` (verified in the dependency metadata of pydantic-ai-slim, anthropic, openai, mcp), which the scaffold uses |
| Tool images pulled automatically could be tampered with or fail midway | Digest-pinned lock file, signature check, allow-listed registries, classified errors, no half-pulled image marked ready |
| Stale or unmaintained security tools | Version and last-release check in CI, replacement list in the [tool map](research/wstg-tool-map.md), built-ins instead of abandoned tools |
| Star and download counts not yet verified | Hosts requested; the scaffold PR is blocked on filling the adoption column |
| Cinematic visuals hurt performance or accessibility | Budgets, lazy loading, Reduce effects, 2D equivalents, axe in CI |

---

## 21. Open questions and things I could not verify

### Decisions I need from you

1. ~~**Tool isolation.**~~ **Decided: hybrid** (you chose it on 2026-11-23), with a Tools settings page to pick Local or Docker per tool ([7.5](#75-the-tools-settings-page)).
2. **UI library.** I recommend Vuetify 4 (you suggested it, and AresGate uses it). Your coding standards name PrimeVue for Vue projects; say so if you would rather follow that.
3. **License.** Apache-2.0 suggested. Your call.
4. **CVE enrichment privacy.** External lookups send only CVE ids, product names and versions. Default on or off?
5. ~~**CI order.**~~ **Decided: CI first.** BLI-1 is the first build PR, then the scaffold ([section 19](#19-the-pr-stack)).
6. **Coverage threshold.** Your message says about 95%, the project instructions say about 90%. I used 95% for pytest and Vitest and 80% for Playwright.
7. **Visual direction.** The app-shell PR will bring two or three mock directions for you to pick from.
8. **Chainguard Python packages.** Use Chainguard Libraries for Python for runtime dependencies, with PyPI as a fallback? It reduces CVEs but ties installs to credentials (contributors and fork PRs would use PyPI). Recommended: Wolfi base image from day one; try the Python index in the scaffold PR once I can confirm your credentials are entitled to it.

### Checked since the first draft

After you allowed the hosts I read the sources directly: Ollama's `/api/tags`, `/api/show`, authentication, cloud and usage pages; Pydantic AI's Anthropic and Ollama pages; Anthropic's and OpenAI's prompt-caching pages; the Wolfi package index, and live responses from NVD, EPSS, CISA KEV (and its GitHub mirror), OSV and CIRCL. Findings that changed the plan: Ollama Cloud does not enforce JSON-schema output; OpenAI now charges for cache writes; Anthropic's minimum cacheable length is 512 tokens on the current models; EPSS values are strings.

### Added after your review (2026-11-23)

Tool set researched for every WSTG test ([tool map](research/wstg-tool-map.md)); Docker image pulls, Tools settings page, two roles, dependency policy and CI-first stack order added. Newly verified: Wolfi has nuclei 3.11.1, gobuster 3.8.2, amass 5.1.3, hydra 26.2.0, grpcurl 1.9.4, WABT, wasm-tools, Binaryen, Wasmtime, Syft and Grype, but not ffuf, httpx, katana, subfinder, dalfox, testssl.sh, Nikto, wafw00f, sslyze or ZAP; the official ZAP image has `stable`, `weekly` and `latest` tags on GHCR; Dalfox 3 is a Rust rewrite (tag v3.3.0); Nikto's database files may be distributed only with the official package.

### Still unverified

- **Chainguard** registry and package-index details and entitlement: `cgr.dev`, `libraries.cgr.dev`, `edu.chainguard.dev`, `www.chainguard.dev` and `support.chainguard.dev` are still blocked for me. Please add them if you want this verified.
- **NVD's own rate-limit page** (`nvd.nist.gov` returned 403 and is a JavaScript app); the 5 and 50 requests per 30 seconds come from search results quoting it. The API itself answers on `services.nvd.nist.gov`.
- `pypistats.org` (download counts) is unreachable; agent-framework star counts are one third-party snapshot. **Star counts and download counts for the dependency policy** need `api.deps.dev`, `api.npmjs.org`, `pypistats.org` and `api.securityscorecards.dev`, which I have asked you to allow; the GitHub API is limited to this repository, so I read releases, tags and last-commit dates through the Go proxy, PyPI, npm, Docker Hub and `git ls-remote` instead. Versions and release counts were read from PyPI directly.
- `go-acme.github.io` returned 404 (lego docs); the lego version and flags are checked in the container ticket. `lego` is not a Wolfi package.
- Whether Ollama's cached-token count survives Pydantic AI's OpenAI-compatible path; OpenAI Chat Completions support for the GPT-6 models (the Responses API is confirmed).
- The black, grey and white box definitions come from vendor and training write-ups, not a standard; the pre-engagement field list comes from public scoping and rules-of-engagement templates, not from PTES itself.

---

## 22. Sources

Checked 2026-11-23.

- Anthropic: [pricing](https://platform.claude.com/docs/en/about-claude/pricing), [models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- OpenAI: [pricing](https://developers.openai.com/api/docs/pricing), [models](https://developers.openai.com/api/docs/models), [deprecations](https://developers.openai.com/api/docs/deprecations)
- Registry data: PyPI JSON API and `npm view` for every version in section 4
- OWASP WSTG checklist: [checklist.json](https://github.com/OWASP/wstg/blob/master/checklists/checklist.json) (13 categories, 133 tests)
- Reference CI: AresGate `ci.yml`, `release.yml`, `zizmor.yml`, `Dockerfile`, `sonar-project.properties` and `DOCS/security.md` in the AresGate repository
- Agent frameworks and pentest agents: [research/agent-frameworks.md](research/agent-frameworks.md), [research/pentest-agents.md](research/pentest-agents.md)
- Models and pricing: [research/models-and-pricing.md](research/models-and-pricing.md)
- Tools: [research/wstg-tool-map.md](research/wstg-tool-map.md); versions from the Go module proxy, PyPI, npm, the Wolfi index, Docker Hub and GHCR tag lists, and `git ls-remote` plus shallow clones for last-commit dates; Nikto licensing from its `COPYING` file
- CVE data: [NVD developers](https://nvd.nist.gov/developers/start-here) and [API key announcement](https://nvd.nist.gov/general/news/API-Key-Announcement) (limits, as returned by search); live responses from the NVD, FIRST EPSS, CIRCL and OSV APIs; [OSV API docs](https://google.github.io/osv.dev/api/); [cisagov/kev-data](https://github.com/cisagov/kev-data) and the CISA KEV JSON feed
- Ollama: [authentication](https://docs.ollama.com/api/authentication), [cloud](https://docs.ollama.com/cloud), [cloud API keys](https://docs.ollama.com/cloud/api), [cloud models](https://docs.ollama.com/cloud/models), [list models](https://docs.ollama.com/api/tags), [show model details](https://docs.ollama.com/api-reference/show-model-details), [usage metrics](https://docs.ollama.com/api/usage)
- Pydantic AI: [Anthropic models and caching](https://pydantic.dev/docs/ai/models/anthropic/), [Ollama models](https://pydantic.dev/docs/ai/models/ollama/)
- Prompt caching: [Anthropic](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [OpenAI](https://developers.openai.com/api/docs/guides/prompt-caching)
- Chainguard (not verified, search results only): [Chainguard Libraries for Python configuration](https://edu.chainguard.dev/chainguard/libraries/python/build-configuration/), [Catalog Starter](https://edu.chainguard.dev/chainguard/containers/about/catalog-starter/)
- Pentest types and scoping: [Invicti](https://www.invicti.com/blog/web-security/types-of-penetration-tests), [Snyk gray box](https://snyk.io/articles/application-security/testing/gray-box-testing/), [OffSec white box](https://www.offsec.com/blog/white-box-testing-web-applications/), [NetSPI source-assisted tests](https://www.netspi.com/blog/executive/penetration-testing/consider-a-source-code-assisted-pentest/), [rules of engagement template](https://www.securityscientist.net/blog/penetration-testing-rules-of-engagement-template/), [scoping checklist](https://nhimg.org/penetration-test-scoping-checklist-guide)
