# Findings

A **finding** is something wrong that a pentest found, with how serious it is, the proof, and where it stands. Results are what tools and people recorded; findings are what the team stands behind and puts in a report. This page covers what a finding holds, how it is rated, the statuses, evidence and what is kept secret, merging, import and export, and the API.

## What a finding holds

| Part         | What it is                                                                                                        |
| ------------ | ----------------------------------------------------------------------------------------------------------------- |
| Number       | `F-1`, `F-2`… counted for each pentest, never reused                                                              |
| Description  | Title, what is wrong, the affected target, how to fix it and references (web addresses)                           |
| Classes      | The checklist tests it came from, CWE ids and the OWASP Top 10 (2021) category                                    |
| Rating       | A CVSS 4.0 and/or 3.1 vector with the score the server works out, the severity and a confidence                   |
| Source       | Written by hand, found by an agent, made from a result or imported                                                |
| Status       | New, confirmed, false positive, accepted risk, fixed or retest needed                                             |
| Verification | Not verified, verified or could not be reproduced, and by whom (an agent's replay or a person)                    |
| Evidence     | Notes, a request and its response, a screenshot or a link to a result of the pentest, each of which can be sealed |
| Timeline     | Every change, status move, comment and merge, with who did it and when                                            |

## How a finding is rated

Scores are always worked out on the server from the vector, with the FIRST reference algorithms (CVSS 3.1 and 4.0 base metrics). The page's calculator shows the score as the metrics are picked; a vector can also be pasted. The severity follows the best score (4.0 first) unless a person gives one, which then wins. A finding with neither a vector nor a severity is refused, and so is a vector that is not complete. Changing the vector re-rates the finding unless a severity is given with it.

Confidence is the reporter's, from tentative to firm to certain. An agent's low, medium and high map to those.

## Statuses

A status moves only along these lines; anything else is refused, and so is moving to the status a finding already has.

| From           | To                                                  |
| -------------- | --------------------------------------------------- |
| New            | Confirmed, false positive, accepted risk, fixed     |
| Confirmed      | Fixed, accepted risk, false positive, retest needed |
| Retest needed  | Confirmed, fixed, false positive, accepted risk     |
| Fixed          | Retest needed, confirmed                            |
| False positive | New, confirmed                                      |
| Accepted risk  | New, confirmed, fixed                               |

Every move is on the timeline with an optional note. **Ask for a retest** moves a finding to retest needed and links to the Agents page, where the dialog opens with the finding's tests chosen; the mission is still previewed and confirmed as always. Running one needs a tool runner, which is a separate ticket.

## Findings from agents

When a test agent reports findings, the verifier replays each one. A finding the replay confirms is made as confirmed and verified by an agent; one it does not confirm is made as new and unverified. A finding the same test already made (the same title) is not made twice: it is marked as seen again, and one that was fixed or waiting for a retest is confirmed again when the replay agrees. The steps an agent cites become result evidence on the finding.

## Evidence and secrets

Evidence is stored sealed in the vault. Anything that looks like a secret (a token, a key, a password in a request) is sealed automatically, and any piece can be sealed or unsealed by hand. A sealed piece is masked in lists, the finding, exports and the API; an administrator can reveal one with **Reveal**, and each reveal is written to the audit log (`finding.evidence_reveal`) without the content. Text that is not sealed still has known secret shapes masked. A screenshot is a PNG, JPEG or WebP of up to 2 MB, checked by its first bytes, and is shown only while it is not sealed. A finding holds at most 100 pieces of evidence.

## Merging and duplicates

A finding that looks like another one (the same title, or the same test and target) shows a warning with the likely duplicates. **Merge** moves the evidence, tests, CWEs and references to the finding that is kept and puts this one in the trash, pointing at it; a merged finding cannot be restored. Everything is on both timelines.

## Import and export

- **Export** as JSON (Blindspot's own shape, which can be imported again), CSV (cells that start like a formula are made safe for spreadsheets) or SARIF 2.1.0. Sealed evidence is masked in every format.
- **Import** reads a Blindspot JSON export or a scanner's SARIF report, up to 8 MiB. A finding with the same title and target as one already there is skipped, and so is an item that cannot be rated; the answer says how many were created and skipped.
- **Make findings** on a result page turns the issues the result holds into findings, each with the result as evidence. An issue that was already made into a finding is not made twice.

## API

Routes are under `/api`. Everyone signed in may read; changing needs an administrator, and an archived or trashed pentest cannot be changed.

| Route                                                        | What it does                                                                                                  |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| `GET /cvss/score?vector=`                                    | The score and severity of a CVSS 3.1 or 4.0 vector                                                            |
| `GET /findings/reference`                                    | The OWASP categories and the status transitions                                                               |
| `GET /pentests/{id}/findings`                                | List with `view`, `status`, `severity`, `test`, `target`, `q`, `sort`, `order`, `group_by`, `limit`, `offset` |
| `POST /pentests/{id}/findings`                               | Write a finding                                                                                               |
| `GET /pentests/{id}/findings/export?format=`                 | `json`, `csv` or `sarif`                                                                                      |
| `POST /pentests/{id}/findings/import`                        | Import `json` or `sarif`                                                                                      |
| `POST /pentests/{id}/findings/bulk`                          | Set the status of, delete or restore up to 100 findings                                                       |
| `POST /pentests/{id}/results/{rid}/promote`                  | Make findings from the issues of a result                                                                     |
| `GET`, `PATCH`, `DELETE /pentests/{id}/findings/{fid}`       | Read, change, or move to the trash                                                                            |
| `POST …/{fid}/restore`, `…/status`, `…/verification`         | Bring back, move to a status, record that a person verified it or could not                                   |
| `POST …/{fid}/retest`, `…/comments`, `…/merge`               | Ask for a retest, comment, merge into another finding                                                         |
| `POST`, `PATCH`, `DELETE …/{fid}/evidence[/{eid}]`           | Add, seal or unseal, and remove evidence                                                                      |
| `POST …/evidence/{eid}/reveal`, `GET …/evidence/{eid}/image` | Show sealed evidence (audited), and serve an unsealed screenshot                                              |

A pentest holds at most 5,000 findings.

## Not yet

Reading CSV, ZAP and Burp reports, the OWASP Top 10 2025 edition, enrichment from CVE and EPSS data, reports and an agent that explains a finding simply come with later tickets, and a retest only runs once the tool runner is connected.
