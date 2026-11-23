# Contributing

These rules apply to everyone, including the AI agents that help build Blindspot. The CI checks enforce them, so a pull request that breaks them cannot merge.

## Tickets, branches, commits and pull requests

Every change starts with a ticket on the [BLI board](https://brianbaggs.atlassian.net/jira/software/projects/BLI/boards/38).

| What                     | Rule                                                               | Example                                |
| ------------------------ | ------------------------------------------------------------------ | -------------------------------------- |
| Branch                   | The ticket key, then lower-case words joined by hyphens            | `BLI-12-app-shell`                     |
| Commit message           | **One line** that starts with the ticket key. No body, no trailers | `BLI-12 Add the app shell`             |
| Pull request title       | Starts with the same ticket key                                    | `BLI-12 Add the app shell`             |
| Pull request description | Starts with the attribution comment from the template              | see `.github/pull_request_template.md` |

Pull requests are **stacked**: each one is based on the branch below it, so the whole stack can be merged bottom-up once CI is green. The first PR of a stack is based on `master`.

The `PR hygiene` workflow checks the title, the branch and every commit message. Dependency update pull requests from Dependabot use the dependency ticket (BLI-23).

## What must pass before a pull request merges

- The `CI gate` check, which summarizes every job in [CI](ci.md).
- The `CodeQL gate` check and the `Workflow security` check.
- SonarQube's quality gate with no open issues (added with the SonarQube ticket, BLI-2).
- Every comment from GitHub Advanced Security resolved.

Coverage rules: pytest and Vitest stay at 100% (the build fails below 95%); Playwright must stay above 80%, aiming for 90% and more.

## Before you push

```sh
make lint   # every linter and type checker
make test   # every test
make audit  # known-vulnerable dependencies
```

`make` on its own lists every command. Most commands skip a part of the project that does not exist yet, so they work from the first commit.
