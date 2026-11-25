# Results

Everything a pentest finds out is kept as a **result**: the output of a tool run, tool output imported from somewhere else, or a note a person writes by hand. This page covers what a result holds, the three ways to read one, what is kept secret, and the API.

## What a result holds

| Part        | What it is                                                                                           |
| ----------- | ---------------------------------------------------------------------------------------------------- |
| Source      | `tool` (a run), `import` (pasted or loaded output), or `manual` (a note)                             |
| Normalized  | The tool's output as the one result shape (issues, hosts and services, web responses, TLS checks…)   |
| Raw output  | What the tool printed, exactly, with the command as it ran, the exit code and how long it took       |
| Annotations | A title, notes, tags and the checklist test it belongs to. These are the only parts a person changes |
| Credentials | Secrets a tool found, kept sealed apart from everything else (see below)                             |

The output itself never changes after it is recorded, so a result is evidence. Deleting a result moves it to the trash, where it can be restored.

## Reading a result

The result page has three views and remembers the one each person picked.

- **Friendly** explains the result in plain words: a headline, what each issue means, why it matters and what to do. Technical words have a tooltip. A port map, a TLS grade (A to F) and a header scorecard appear when the result has them. The text comes from templates and never repeats what a tool printed, so a hostile server cannot put words in it.
- **Technical** shows the normalized tables, each column sortable.
- **Raw** shows the command, how it ended, and the output with colour, a search that counts matches, copy and download. Only the first 2,000 lines are drawn; copy and download carry all of it.

## Secrets in results

A credential a tool finds is stored sealed with its own purpose in the vault and is masked in every API answer and every view. An administrator can show one with the **Show** button; each reveal is a separate request and is written to the audit log (`result.reveal`). Raw output is sealed too.

## Importing

**Import output** takes the output of Nmap (XML), Nuclei and httpx (JSON Lines), ffuf, testssl.sh, WhatWeb and wafw00f (JSON) or Nikto (CSV), pasted or from a file, up to 8 MiB. It is read by the same parsers as a run's output; output that cannot be read is refused with the reason. ZAP and Burp reports are not read yet.

## API

All routes are under `/api/pentests/{id}`. Everyone signed in may read; changing needs an administrator, and an archived or trashed pentest cannot be changed.

| Route                                        | What it does                                                                                                                |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `GET /results`                               | List with `view` (live, trash), `tool`, `agent`, `test`, `severity`, `since`, `until`, `q`, `limit` (200 at most), `offset` |
| `POST /results`                              | Write a note                                                                                                                |
| `POST /results/import`                       | Import tool output with a `parser`                                                                                          |
| `POST /results/bulk`                         | Delete, restore, tag or untag up to 100 results                                                                             |
| `GET /results/{rid}`                         | One result with its friendly and technical views                                                                            |
| `GET /results/{rid}/raw`                     | The raw output (the first 2 MiB)                                                                                            |
| `PATCH /results/{rid}`                       | Change the title, notes, tags or checklist test                                                                             |
| `DELETE /results/{rid}`, `POST …/restore`    | Move to the trash and bring back                                                                                            |
| `POST /results/{rid}/credentials/{n}/reveal` | Show one credential (audited)                                                                                               |

A pentest holds at most 5,000 results.

## Not yet

Turning a result into a finding comes with the findings ticket, a button to have an agent explain a result comes with the agent runtime, and the runner (which records the results of runs) is a separate ticket.
