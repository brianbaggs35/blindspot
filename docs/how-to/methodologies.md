# Methodologies

A methodology is data: categories of tests, and for each test a **playbook** that tells an agent
what to do and what to bring back. WSTG ships with Blindspot. Another methodology (PTES, OSSTMM,
ASVS, your own) is a folder of YAML files, so adding one never touches the engine. The agent
hierarchy (a Commander, one agent per category, one sub-agent per test) is built from whichever
methodology a pentest uses.

## What ships

**WSTG**, the OWASP Web Security Testing Guide: 13 categories and 133 tests, imported from the
upstream `checklists/checklist.json` (licence CC BY-SA 4.0). A snapshot of that file is bundled, so
Blindspot needs no network to start.

- Every test has its objectives and reference link from upstream.
- Every test is mapped to the tools that can do it, from the
  [WSTG tool map](../research/wstg-tool-map.md). A test nobody has mapped is _manual review_
  until somebody does: the agent gathers the evidence and a person checks it.
- Ten high-value tests have hand-written playbooks (server fingerprinting, lock-out, object-level
  authorisation, cookie attributes, JWTs, reflected XSS, SQL injection, SSRF, TLS and API object
  access). Every other test gets a playbook generated from its category's template, the test's
  objectives and its tools. A generated playbook never lists a step above the test's risk class.
- Some tests only apply when the target shows a feature (`requires`): SAML, passkeys, OpenID
  Connect, uploads, WebSockets, GraphQL, gRPC, WebAssembly and so on.

## Risk classes

| Class       | Meaning                                                              |
| ----------- | -------------------------------------------------------------------- |
| `safe`      | Only observes: reads pages, headers, public sources, configuration   |
| `active`    | Sends requests the application was not built to expect               |
| `intrusive` | Can change data or disturb the service. Always needs approval to run |

A test's class is the most intrusive thing it may do: the highest class of its tools or of the
steps its playbook lists, whichever is higher.

## Snapshots, updates and overrides

- Each methodology is stored as **versioned snapshots**. Snapshots are only added, so a pentest can
  say exactly which tests it ran against. The newest is in use.
- A snapshot is identified by a SHA-256 of its content. Importing the same content again changes
  nothing.
- **Updates are never silent.** On the Methodologies page, an administrator asks for an update and
  sees the diff first: tests added, removed and changed (and which fields), categories added or
  removed, and details that changed. Applying names the exact content that was reviewed; if what is
  on offer has changed since, nothing is applied and the diff is shown again.
  - WSTG has two sources: the copy shipped with the app, and the upstream checklist
    (`raw.githubusercontent.com`, fixed in the code, no redirects followed, 2 MB at most).
  - A pack folder has one source: the folder.
- An administrator can **replace a test's playbook**. The original stays in the snapshot and comes
  back if the change is removed, and a change survives updates.
- A methodology can be turned off so it cannot be chosen for a new pentest.

## Adding a methodology

Create a folder under `<data directory>/methodologies` (`/data/methodologies` in the container),
named after the methodology's id, then press **Read packs folder** on the Methodologies page (or
`POST /api/methodologies/reload`). A new pack is added; a pack that changed is reported as an
update waiting for review. A pack whose id is one that ships with Blindspot is refused. A broken
pack is listed with the reason and does not stop the others.

```
ptes/
  methodology.yaml     id, name, version, source and licence, categories and tests
  tools.yaml           which tools can do each test, or manual review
  playbooks/           optional hand-written playbooks, any number of *.yaml files
  reporting.yaml       optional short names for the categories in reports
```

### methodology.yaml

```yaml
id: ptes # lowercase letters, digits and hyphens; must be the folder's name
name: Penetration Testing Execution Standard
version: "1.0"
source_url: https://www.pentest-standard.org/
license: Public
categories:
  - id: PTES-RECON # upper case, hyphen-separated
    name: Intelligence gathering
    tests:
      - id: PTES-RECON-01 # must start with the category's id and a hyphen
        name: Passive reconnaissance
        reference: https://www.pentest-standard.org/index.php/Intelligence_Gathering
        objectives: [Learn what is public about the target]
        tags: [recon]
        risk_class: safe # optional; otherwise taken from tools.yaml
        requires: [] # what the target must show for the test to apply
```

### tools.yaml

Every test must say how it is run: list tools, or set `manual_review: true`. A pack that leaves a
test out is refused, and so is a name that is not a test in the pack (a typo).

```yaml
tests:
  PTES-RECON-01:
    tools: [b.osint] # ids from the tool registry
    risk: safe
    approach: Search engines and public records
  PTES-EXPL-01:
    manual_review: true
    risk: intrusive
```

### playbooks/\*.yaml

A map from test id to playbook. A test without one gets a generated playbook.

```yaml
PTES-RECON-01:
  summary: Collect public facts. # what the sub-agent is asked to establish
  instructions: | # what it is told to do (Markdown)
    Use only public sources.
  tools: [b.osint] # or manual_review: true
  safe_steps: [Read the public records]
  active_steps: []
  intrusive_steps: []
  evidence: [The source of each fact] # what it must bring back (at least one)
  success: Everything public was found. # when to mark the test passed
  failure: Something private is public. # when there is a finding
  not_applicable: [The scope excludes it] # when to mark it not applicable
```

Every document is checked against a schema with no unknown fields, so a typo is an error, not a
silent default. The schema is `MethodologySpec.model_json_schema()` (and `Playbook`, `Draft` and
`ToolsFile` for the pieces) in `backend/app/methodology/`.

## The Methodologies page

`/methodologies` (Work menu) shows what each test checks and exactly what its agent is told to
do. Everyone signed in can read it. Only administrators see the buttons that change anything.

1. **Pick a methodology.** With more than one installed there is a tab for each. The card shows
   the counts, the version in use, the licence and where it comes from.
2. **Find a test.** Search by id, name or tool, and narrow by risk class (Safe, Active,
   Intrusive). Each category folds out to its tests, each with its risk and whether its playbook
   is generated, hand-written or changed here.
3. **Read a playbook.** Open a test to see its objectives, the instruction the agent is given,
   its tools, the steps by risk class, the evidence it must bring back, and when it passes,
   reports a finding or does not apply.
4. **Change a playbook (administrators).** _Edit the playbook_ replaces what the agent is told.
   The original is kept: _Put the original back_ returns it. Lists take one entry per line.
   A playbook that is not valid is refused with the reason, and what was typed stays.
5. **Turn a methodology on or off (administrators).** The switch decides whether it is offered
   for new pentests.
6. **Read the packs folder (administrators).** Picks up packs added to
   `<data dir>/methodologies` and reports packs it skipped, with the reason for each.
7. **Check for updates (administrators).** Shows what an update would change before anything
   changes. Applying names the exact update that was shown, so a different one is never applied;
   playbooks changed here stay as written and the old version is kept.

## API

Anyone signed in can read. Everything that changes anything needs an administrator.

| Method and path                                        | What it does                                  |
| ------------------------------------------------------ | --------------------------------------------- |
| `GET /api/methodologies`                               | Every methodology with its counts             |
| `GET /api/methodologies/{id}`                          | Categories and an outline of each test        |
| `GET /api/methodologies/{id}/tests/{test}`             | One test with its playbook as used now        |
| `PUT /api/methodologies/{id}/tests/{test}/playbook`    | Replace a playbook (administrator)            |
| `DELETE /api/methodologies/{id}/tests/{test}/playbook` | Put the original back (administrator)         |
| `PATCH /api/methodologies/{id}`                        | Turn on or off (administrator)                |
| `GET /api/methodologies/{id}/versions`                 | The snapshots                                 |
| `GET /api/methodologies/{id}/updates?source=`          | The diff an update would make (administrator) |
| `POST /api/methodologies/{id}/updates`                 | Apply a reviewed update (administrator)       |
| `POST /api/methodologies/reload`                       | Read the packs folder (administrator)         |

`source` is `origin` (the app's copy, or the pack folder) or `upstream` (WSTG only).

| Code                | Status | Meaning                                                             |
| ------------------- | ------ | ------------------------------------------------------------------- |
| `pack_invalid`      | 422    | The update is not a valid methodology; the title says what is wrong |
| `no_upstream`       | 422    | Only WSTG has an upstream                                           |
| `candidate_changed` | 409    | What is on offer changed since it was reviewed                      |
| `upstream_failed`   | 502    | The upstream could not be reached, or sent something unexpected     |

## Still to come

The per-pentest checklist (a status and evidence links for each test, plus notes and custom
tests) arrives with the pentests, and the tool ids are checked against the tool registry when it
exists.
