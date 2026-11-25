# Tools

An agent never runs a command. It asks for a **tool** with some values; the app checks the values against the tool's **manifest** and builds the argument list. This page covers the manifest, how values become a command line, the registry, where each tool runs and the limits it runs under (the Tools page), the scope guard, permissions and the API. The runner that executes a call is a separate ticket (BLI-55).

## The manifest

A manifest is data, checked when it is loaded. Bundled manifests are YAML files in `backend/app/tools/bundled`; an administrator's own are stored in the database. A mistake is refused with the field and the reason, never ignored: unknown fields are errors.

```yaml
id: c.nmap # tier letter, a dot, a name: the ids methodologies use
name: Nmap
tier: core # builtin | core | pack | optional | custom
binary: nmap # a name on the PATH, or an absolute path
risk: active # passive | active | intrusive | destructive
capabilities: [NET_RAW] # the only ones a tool may ask for: NET_RAW, NET_ADMIN, NET_BIND_SERVICE
params:
  targets: { type: target, required: true, many: true }
  ports: { type: ports, default: top-1000 }
  scan: { type: enum, values: [connect, syn, version], default: connect }
  rate: { type: integer, minimum: 1, maximum: 1000 }
argv: # arguments after the binary
  - -oX
  - "-"
  - { when: scan, equals: syn, args: ["-sS"] }
  - { when: rate, args: ["--max-rate={rate}"] }
  - -p
  - "{ports}"
  - "{targets...}"
version: { args: ["--version"], pattern: "Nmap version ([0-9.]+)" }
timeout_s: 900
max_output_mb: 20
parsers: [nmap_xml]
explain: Looks for open network doors (ports) on a server and what listens behind them.
could_go_wrong: Active scanning can trigger alerts and, rarely, upset fragile devices.
```

`explain` and `could_go_wrong` are plain-language text for the Tools page. A tool written in Python inside the app has `execution: builtin` and a `handler` instead of a binary and arguments. `Manifest.model_json_schema()` is the JSON Schema.

### Parameter types

| Type      | A value is                                                                                          |
| --------- | --------------------------------------------------------------------------------------------------- |
| `string`  | Text up to `max_length` (200 by default), optionally matching `pattern` completely                  |
| `integer` | A whole number within `minimum` and `maximum`                                                       |
| `boolean` | `true` or `false`; only used in a `when`, never as text                                             |
| `enum`    | One of `values`                                                                                     |
| `ports`   | `80,443,8000-8100` or `top-1000`, every port from 1 to 65535                                        |
| `target`  | A web address, host name, address or address range. Never starts with a dash and holds no spaces    |
| `file`    | A relative path with no `..`, `.` or empty parts, resolved by the runner under the app's data files |

`many: true` makes a list (string, enum, target or file) with at most `max_items` entries. A parameter is `required`, has a `default`, or is optional and then only used inside its own `when`. Every value must have no control characters: no NUL and no new line.

## How a command line is built

The templates in `argv` are the only source of arguments:

- `{name}` is replaced by the value, inside **one** argument. A value is never split on spaces and never joined into a string for a shell.
- `{name...}` as a whole argument gives one argument for each value of a list.
- `{{` and `}}` are literal braces. Any other brace is a mistake and the manifest does not load.
- `{ when: name, equals: x, args: [...] }` adds arguments only when the parameter is set (and is `x`, when `equals` is given).
- A value at the start of an argument may not begin with a dash, so it cannot pose as an option (`--script=...`). A value after a literal such as `--rate=` can hold anything its type allows.
- The whole line is limited to 2,000 arguments, 128 KiB and 8 KiB per argument.

Checked when the manifest loads: every placeholder names a parameter that will have a value, every parameter is used, a boolean is only used in a `when`, a list is only spread, and the version check uses no parameters. A shell, or a program that starts other programs (`sh`, `bash`, `env`, `xargs`, `sudo`, `nsenter`, `find` and the like), can never be a tool's binary.

`build_call(manifest, values)` returns the argument list (starting with the binary), the checked values and `targets`, every value of every `target` parameter, which the scope guard checks before anything runs. Unknown values and missing required ones are errors, not ignored.

## Custom tools

An administrator can define a tool with the API (the Tools page shows custom tools and sets how they run, but it has no editor for their definition yet). A custom tool:

- has an id that starts with `x.`, so it can never replace a bundled tool, and the tier is always `custom` whatever the request says;
- runs a program that is not an interpreter (`python`, `perl`, `node`, `awk`, `sed` and the like are refused, because `-c` or `-e` would turn every value into code);
- asks for no capabilities;
- goes through exactly the same checks as a bundled manifest, and later through the same scope guard, permissions and audit as every other tool.

At most 100 custom tools can exist. Creating, changing and removing one is in the audit trail (`tool.custom.create`, `tool.custom.update`, `tool.custom.delete`), with the risk class and binary but never any value.

## The registry

`load_registry` merges the bundled manifests with the stored custom ones on every request, so a change shows up without a restart. Each tool carries its `origin` and a `fingerprint` (a short hash of the manifest) so a run can record exactly which definition it used. A stored manifest that no longer validates (the rules became stricter) is skipped and logged, not allowed to break the list.

## The core tool pack

Fourteen tools ship with the app as YAML manifests in `backend/app/tools/bundled`. The letter of the id is the tier: `c` core, `p` pack, `o` optional, `b` built in.

| Id            | Tool                          | Risk      | Output parser   | In the image |
| ------------- | ----------------------------- | --------- | --------------- | ------------ |
| `c.nmap`      | Nmap, ports and services      | active    | `nmap_xml`      | yes          |
| `c.sqlmap`    | sqlmap, SQL injection         | intrusive | none (raw text) | yes          |
| `c.nuclei`    | Nuclei, template checks       | active    | `nuclei_jsonl`  | no           |
| `p.ffuf`      | ffuf, hidden paths            | active    | `ffuf_json`     | no           |
| `p.testssl`   | testssl.sh, TLS               | active    | `testssl_json`  | no           |
| `p.waf`       | wafw00f, firewall detection   | active    | `wafw00f_json`  | no           |
| `p.pd`        | httpx, one plain request      | passive   | `httpx_jsonl`   | no           |
| `o.whatweb`   | WhatWeb, software recognition | active    | `whatweb_json`  | no           |
| `o.nikto`     | Nikto, old web scanner        | active    | `nikto_csv`     | no           |
| `b.headers`   | Headers, cookies, CORS, CSP   | passive   | built in        | built in     |
| `b.jwt`       | Token inspector               | passive   | built in        | built in     |
| `b.wellknown` | robots, sitemap, security.txt | passive   | built in        | built in     |
| `b.spider`    | Forms and parameters          | active    | built in        | built in     |
| `b.entropy`   | Session token strength        | active    | built in        | built in     |

Only the small tools are in the image: nmap (27 MB), sqlmap (11 MB), `dig` and `whois`. The rest are installed by the Docker runner (BLI-24) or the administrator, because Nuclei alone is 151 MB; a tool that is not installed shows as missing on the Tools page (BLI-25) instead of failing a run. Nothing here is destructive: sqlmap runs at risk level 1 with no stacked queries, Nuclei always leaves out its denial-of-service, fuzzing and brute-force templates, and Nikto is told to skip its denial-of-service group.

### One result shape

Every tool, parsed or built in, ends as a `ToolResult` (`app/tools/parsers/schema.py`): hosts with services, web responses, technologies, TLS findings, issues (a title, a severity, how sure the check is, a target, evidence and a reference such as a template id), credentials, artifacts, a list of warnings and a `truncated` flag. Agents, the results pages and the findings code read only this, never a tool's own format. `summarize(result)` makes the plain-words lines shown first on a results page.

A parser is a function from bytes to a `ToolResult` and is listed in `PARSERS`. The rules every parser follows:

- Output is data, never trusted: it may be malformed, hostile or enormous. A parser raises only `ParseError`, with a message that is safe to show, and the raw output is kept for a person to read.
- XML is read with a hardened parser (no entity is expanded, no DTD is loaded, nothing is fetched); a document that declares an entity is refused. JSON that is nested more than 40 levels is refused. Output over 64 MiB is refused.
- Every list stops at 5,000 items and the result says it was cut short. A line or an entry that cannot be read is left out and counted in a warning, not a crash.
- Bytes that are not UTF-8 are replaced.
- A secret a tool finds is a `SecretStr`, so it is never printed or dumped to JSON by accident.

Real captured output for each tool is in `backend/tests/fixtures/tools` (see its README for how each file was made), with the result each parser makes of it in `golden/`. After changing a parser on purpose, run `BLINDSPOT_UPDATE_GOLDEN=1 uv run pytest tests/test_tools_parsers.py` and read the diff. The Nuclei and httpx fixtures are written from the documented formats and will be replaced with captured output once the Docker runner can run those tools.

### Built-in tools

A built-in tool is Python inside the app (`app/tools/analyzers`). It never opens a connection: it is given a `Fetcher`, which the runner builds so that every request, and every redirect it follows, is checked with the scope guard first. A test gives it canned pages instead.

- **`b.headers`** reads one page twice (the second time with a made-up `Origin`) and reports missing or weak HSTS, `X-Content-Type-Options`, framing protection, `Referrer-Policy` and `Permissions-Policy`, version leaks in `Server` and `X-Powered-By`, cookie flags (`Secure`, `HttpOnly`, `SameSite`, the `__Host-` rules; values are never printed), CORS (any origin, the `null` origin, an origin that is repeated back, with or without credentials) and a Content-Security-Policy evaluation (no script limit, inline script and eval without a nonce or hash, wildcards, shared script hosts, no `object-src`, `base-uri` or `frame-ancestors`, report-only policies).
- **`b.jwt`** decodes a token and never verifies it or puts it in the result: no signature or `alg: none`, shared-secret signing, a header that names its own key (`jku`, `x5u`, `jwk`, `x5c`), a `kid` that looks like a path or a query, no expiry, an expiry more than a year away, and claims that look sensitive.
- **`b.wellknown`** reads `robots.txt` (paths, sensitive-looking paths, sitemaps), the sitemap (same site only, at most three) and `security.txt` (a contact, an expiry that has not passed).
- **`b.spider`** reads up to 20 pages of one site and lists forms and parameters. It flags a password sent without HTTPS, a form on an HTTPS page that posts to HTTP, forms that change data without an anti-forgery token and file uploads. It never submits a form and never runs script.
- **`b.entropy`** asks for a page several times with no cookie and checks the session ids it hands out: repeats, counters, a shared start and an estimate of the guessing work (at least 64 bits, 112 comfortable). It reports lengths and bit counts, never the ids.

The runner (BLI-55) calls `HANDLERS[manifest.handler](values, fetcher)`.

## The Tools page: where a tool runs, and its limits

**Tools** in the menu (under System) lists every tool with its risk class, where it runs now, what is wrong if it cannot run, the program or image, and the limits it runs under. Everyone signed in can read it; only an administrator can change anything.

### The default and each tool's own choice

The default for every tool is one of four settings:

| Setting           | What it does                                                                                      |
| ----------------- | ------------------------------------------------------------------------------------------------- |
| **Auto**          | Local for tools that come with Blindspot (built in, core, or with no image), Docker for the rest. |
| **Prefer Local**  | Local, and Docker when Local cannot run.                                                          |
| **Prefer Docker** | Docker, and Local when Docker cannot run.                                                         |
| **Docker only**   | Docker, and nothing else.                                                                         |

A tool can have its own choice (**Follow the default**, **Local** or **Docker**). **An own choice is never switched silently**: a tool set to Docker while Docker is not connected is stopped with the reason (`Docker not reachable`), not run Local. The page then says "It would run Local. Choose that in its settings if you want it." Only the two `Prefer` defaults fall back, and then the tool is shown as running "the other way, as the default allows". A built-in tool runs inside the app and has no mode.

Per tool an administrator can also set: whether the tool may be used at all (a tool switched off is refused by the authorization check whatever else is true), a **program path** (Local; no shell, no interpreter, no `..`), an **image with its digest** (Docker; a reference ending in `@sha256:` and 64 hex characters), the **timeout**, the **output cap**, **requests per second** for each target, **CPUs** and **memory** (Docker), and the **most the tool may do**. That last one can lower a tool's risk class (a tool whose manifest says `intrusive` can be held to `passive`) and never raise it. Empty fields are what the manifest says; **Reset** removes everything set for the tool.

### Test

**Test** runs the tool's version check (the arguments of its manifest, as a list, never through a shell, 10 seconds, a fixed environment, output cut at 4,000 characters) and shows the command, how it ended, how long it took, the version found and what was printed. It is offered where the tool runs Local. Running a tool in Docker, pulling images and showing an image's status come with the runner (BLI-55); until then a Docker setting is stored and checked, not run.

### The API for settings

| Route                                | Who   | What it does                                                                                             |
| ------------------------------------ | ----- | -------------------------------------------------------------------------------------------------------- |
| `GET /api/tools/settings`            | any   | The default, whether Docker is reachable, and every tool with its settings, limits and where it runs now |
| `PUT /api/tools/settings/default`    | admin | `{"mode": "auto" \| "prefer_local" \| "prefer_docker" \| "docker_only"}`                                 |
| `PUT /api/tools/settings/{id}`       | admin | Replace the settings of one tool (an empty field is the manifest's)                                      |
| `DELETE /api/tools/settings/{id}`    | admin | Back to the defaults                                                                                     |
| `POST /api/tools/settings/{id}/test` | admin | Run the version check                                                                                    |

Changes are audited (`tool.settings.default`, `tool.settings.update`, `tool.settings.reset`, `tool.settings.test`). Errors: `tool_not_found` (404), `builtin_tool` and `risk_above_manifest` (422), `cannot_test` (422, with what is wrong) and `no_version_check` (409). Removing a custom tool removes its settings.

Not yet: running in Docker and pulling images, MCP servers, an editor for custom tools, default arguments and wordlists, installing and updating tools, and a network setting for tools.

## The scope guard and the permission policy

Two checks stand between an agent and a tool. Both are plain code, and nothing a model writes can change them: a model picks a tool and gives values; the risk class comes from the manifest, the agent's role from the runtime and the rules from administrators.

`authorize(session, pentest, role, tool, call)` in `app/tools/authorize.py` is the one question the runner asks before it starts a tool. It answers with a `Verdict` (`auto`, `ask` or `deny`) and a reason in plain words, kept with the run. A call is denied when:

- it is for a different tool than the one that was checked;
- the kill switch is on, the pentest is paused, or it is not authorized or running;
- a rule denies it, or the tool is destructive (those are off and no rule can turn them on);
- a target is out of scope, cannot be looked up, or is an address that is never reachable;
- the tool is active or riskier and names no target, so it cannot be held to a scope.

### The scope guard

`app/tools/guard.py` reads every `target` value of a call as a web address, a host (with or without a port), an address or a range. A name is looked up, and every address it has must be allowed by `CompiledScope.allows`, so a name that points at one public and one private address is refused. Loopback (the app's own container), cloud metadata addresses and the other addresses that are never reachable are refused whatever the scope says. `check_url` is for the runner to ask again about every redirect a response sends.

A tool that scans a host or a range does more than a web request, so it needs the whole host or range in scope: every port and both web schemes, with no path limit. A scope line of `https://app.example.com/shop` allows requests to that address and not a port scan of the host; the refusal says so. A range is checked as a whole: it must sit inside one scope line, may not overlap anything out of scope, and may not hold an address that is never reachable.

### The permission policy

With no rule: passive tools run on their own, active tools ask a person, intrusive tools always ask and destructive tools are off. A rule (a grant) is for an agent role (or any), a tool (or any), up to a risk class, and for one pentest (or all). It can make a tool run on its own, ask first or be denied. It can never skip the ask for an intrusive tool or turn a destructive tool on. A deny rule beats every allow rule; among allow rules the most specific wins (a tool beats a role, which beats every pentest). The kill switch beats all of it.

| Route                                  | Who   | What it does                                                          |
| -------------------------------------- | ----- | --------------------------------------------------------------------- |
| `GET /api/tools/policy`                | any   | The kill switch, the defaults and every rule                          |
| `PUT /api/tools/policy/grants`         | admin | Make a rule, or change the one for the same role, tool and pentest    |
| `DELETE /api/tools/policy/grants/{id}` | admin | Remove a rule                                                         |
| `PUT /api/tools/policy/kill-switch`    | admin | `{"on": true}` stops every tool at once, `{"on": false}` lets them go |

Pausing a pentest is its status (`running` to `paused`): a paused pentest runs no tools. Every change is in the audit trail (`tool.policy.grant`, `tool.policy.revoke`, `tool.policy.kill_switch`). Errors: `grant_destructive` and `grant_needs_a_person` (422), `tool_not_found`, `pentest_not_found` and `grant_not_found` (404), `too_many_grants` (409).

## The API

| Route                           | Who   | What it does                                                       |
| ------------------------------- | ----- | ------------------------------------------------------------------ |
| `GET /api/tools`                | any   | Every tool: id, name, tier, origin, risk, capabilities, `explain`  |
| `GET /api/tools/{id}`           | any   | One tool with its whole manifest, fingerprint and target parameter |
| `POST /api/tools/{id}/preview`  | admin | `{"values": {...}}` → the exact `argv` and `targets`; runs nothing |
| `POST /api/tools/custom`        | admin | Define a custom tool (the body is the manifest, `tier` is ignored) |
| `PUT /api/tools/custom/{id}`    | admin | Replace a custom tool's definition (its id cannot change)          |
| `DELETE /api/tools/custom/{id}` | admin | Remove a custom tool                                               |

Errors use the usual problem format: `invalid_tool` (422, with what is wrong), `invalid_tool_input` (422), `tool_not_found` (404), `tool_exists` and `too_many_tools` (409).
