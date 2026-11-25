# Tools

An agent never runs a command. It asks for a **tool** with some values; the app checks the values against the tool's **manifest** and builds the argument list. This page covers the manifest, how values become a command line, the registry and the API. Where a tool runs (the runner) and whether an agent may use it (the scope guard and permissions) are separate tickets and have their own pages as they land.

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

An administrator can define a tool with the API (the Tools page arrives with BLI-25). A custom tool:

- has an id that starts with `x.`, so it can never replace a bundled tool, and the tier is always `custom` whatever the request says;
- runs a program that is not an interpreter (`python`, `perl`, `node`, `awk`, `sed` and the like are refused, because `-c` or `-e` would turn every value into code);
- asks for no capabilities;
- goes through exactly the same checks as a bundled manifest, and later through the same scope guard, permissions and audit as every other tool.

At most 100 custom tools can exist. Creating, changing and removing one is in the audit trail (`tool.custom.create`, `tool.custom.update`, `tool.custom.delete`), with the risk class and binary but never any value.

## The registry

`load_registry` merges the bundled manifests with the stored custom ones on every request, so a change shows up without a restart. Each tool carries its `origin` and a `fingerprint` (a short hash of the manifest) so a run can record exactly which definition it used. A stored manifest that no longer validates (the rules became stricter) is skipped and logged, not allowed to break the list.

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
