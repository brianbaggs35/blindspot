# Agents and missions

A **mission** is one run of the agents over a pentest. This page covers how a mission is planned, what each agent does, what no agent can change, how a person steers and approves, and the API. The agents page and settings in the app come with a later ticket (BLI-21); this ticket builds the part that runs.

## Who does what

| Agent             | What it does                                                                                                                             | Decided by       |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ---------------- |
| Mission Commander | Plans which tests run, in what order, and why some do not. Categories that only observe go first, then active ones, then intrusive ones. | Code             |
| Category agents   | Run their tests side by side (up to the mission's `concurrency`) and summarize what the tests found.                                     | Code             |
| Test agents       | Work one test: ask for a tool, read what came back, ask again or finish with a verdict, findings and facts.                              | A model          |
| Verifier          | Replays the request behind a finding and checks the result before the finding counts.                                                    | A model and code |

The model for test agents and the verifier is the one set for the **test-agent** role in the AI provider settings. If none is set, the mission stops with a clear message and carries on when one is chosen and the mission is resumed.

## What a model can and cannot do

A model answers with one of two typed shapes: a tool request (`tool`, `values`, `why`) or a finish (`status`, `summary`, `findings`, `facts`). The shapes have no field for permission, scope or risk, and unknown fields are refused. The engine does the rest, on every request, whatever the model said:

1. The tool must be one the test's playbook names and one that is installed. Values must fit the tool's manifest (types, ranges, no unknown parameters).
2. The scope guard looks up every target address by address, and the permission policy decides `auto`, `ask` or `deny` for this role, tool and pentest. A kill switch and a pentest that is not running stop everything. A model's words never change these.
3. Only then does the step run, once. A step is written before it runs. A step that was running when the server stopped is marked **interrupted** on the next start and is never run again by the engine; the agent can ask for it again, visibly.
4. Tool output reaches the model only as a short account of the result (counts and titles), wrapped and escaped as data. The instructions tell the model to treat it as data, and nothing depends on it doing so.
5. A model may **raise** a test's verdict (a confirmed finding makes the test a finding even if the model said passed) but never lower one the evidence set. A finding at or above `verify_from` (medium by default) is replayed by the verifier; a finding the replay does not confirm is not counted. A test a person already settled on the checklist keeps the person's verdict; the agent's outcome is kept on the mission.

## Caps

Every cap is checked by code before each step, from the database, and can be raised when resuming:

| Cap                | Default | What happens at the cap                                  |
| ------------------ | ------- | -------------------------------------------------------- |
| `steps`            | 300     | The mission stops (resume with a higher cap to carry on) |
| `tokens`           | 2M      | The mission stops                                        |
| `cost_usd`         | 25      | The mission stops                                        |
| `seconds`          | 6 hours | The mission stops                                        |
| `steps_per_test`   | 12      | The test finishes as blocked and the others carry on     |
| `tokens_per_test`  | 120,000 | The test finishes as blocked                             |
| `seconds_per_test` | 900     | The test finishes as blocked                             |
| `concurrency`      | 2       | Tests of a category run this many at a time              |

A refused request still costs a step, so an agent cannot loop on refusals.

## Approval

A step the policy answers `ask` for (active and intrusive tools by default) waits. The test shows as **waiting**, the other tests carry on, and when nothing else can run the mission pauses with "Waiting for a person to approve a step." An administrator approves or denies the step. An approved step is checked again right before it runs, so the scope, the kill switch and the policy still apply. A denied step is shown to the agent, which chooses something else. A replay for a finding never waits for approval and is not run when it would need one.

## Pause, resume, cancel, restart

- **Pause** takes effect before the next turn; the step in progress finishes. **Resume** carries on with the same plan and, if you give one, new caps.
- **Cancel** ends the mission. What has not run is marked cancelled; what has run stays in the results.
- After a restart, missions that were running carry on from the database. Nothing is repeated.

## Where the tools run

The engine hands each checked call to an **executor**. The runner that executes tools (a separate ticket) is the executor; until one is connected to the server, `POST /missions` answers `409 no_runner` and nothing can start. The engine itself is tested with a recording executor.

## What is kept

Every task (commander, categories, tests), step (request, verdict, result, note), event and fact is in the database. Each tool run is also an ordinary result of the pentest, with the agent role and the test on it. Facts are shared between tests: a test is shown the facts that match its subject (PostgreSQL full-text search), best first.

## API

Routes are under `/api/pentests/{id}/missions`. Everyone signed in may read; steering needs an administrator.

| Route                                                   | What it does                                                                                              |
| ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `POST /missions`                                        | Plan and start a mission (the pentest must be running; one live mission at a time) with optional `budget` |
| `GET /missions`                                         | The pentest's missions, newest first                                                                      |
| `GET /missions/{mid}`                                   | One mission with its tree of tasks                                                                        |
| `GET /missions/{mid}/steps`                             | Steps, filtered by `task` or `status` (`awaiting_approval` lists what waits for a person)                 |
| `GET /missions/{mid}/events`                            | The log after a cursor (`after`, `limit`); ask again with `next_after` to follow it live                  |
| `POST /missions/{mid}/pause`                            | Pause                                                                                                     |
| `POST /missions/{mid}/resume`                           | Resume, with optional new `budget`                                                                        |
| `POST /missions/{mid}/cancel`                           | Cancel                                                                                                    |
| `POST /missions/{mid}/steps/{sid}/approve` and `…/deny` | Answer a step that waits                                                                                  |

Starting, pausing, resuming, cancelling and every approval are written to the audit log (`mission.*`).

## Not yet

Live streaming of the event log (the cursor API above serves the page), the agents page and settings (BLI-21), and a vector index of facts and evaluation of agent quality on a set of known targets are later work.
