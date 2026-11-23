# Continuous integration

Every pull request and every push to `master` runs the checks below. Each one maps to a `make` command, so a failure in CI can be reproduced on your computer.

## The workflows

| Workflow                                                   | What it does                                                                                                                                                                       | Run it locally                                             |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| [`ci.yml`](../../.github/workflows/ci.yml)                 | Formatting, linters for workflows, scripts and Dockerfiles, tests of the CI scripts, Trivy, and (once they exist) the backend and the web app                                      | `make lint`, `make test`, `make audit`, `make scan-source` |
| [`codeql.yml`](../../.github/workflows/codeql.yml)         | CodeQL with the `security-extended` queries for GitHub Actions, and for Python and JavaScript/TypeScript once they exist. Also runs every Monday                                   | Results appear under Security > Code scanning              |
| [`zizmor.yml`](../../.github/workflows/zizmor.yml)         | Audits the workflow files for injection, over-broad tokens and unpinned actions                                                                                                    | `make audit-workflows`                                     |
| [`pr-hygiene.yml`](../../.github/workflows/pr-hygiene.yml) | Ticket key in the title and branch, one-line commit messages                                                                                                                       | `.github/scripts/pr-hygiene.sh` (see its header)           |
| [`release.yml`](../../.github/workflows/release.yml)       | When a release is published: builds, scans and smoke-tests the container image for amd64 and arm64, then publishes a multi-platform image to GHCR with signed provenance and SBOMs | Needs the container image, added in BLI-6                  |
| `dependabot.yml`                                           | Weekly dependency update pull requests                                                                                                                                             | n/a                                                        |

## The checks in `ci.yml`

| Job                                      | Checks                                                                                                                                                 |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **What to check**                        | Finds out whether the backend and the web app exist, so jobs for code that is not there yet are skipped                                                |
| **Formatting of docs and configuration** | Prettier over every Markdown, YAML and JSON file                                                                                                       |
| **Workflows, scripts and Dockerfiles**   | actionlint, ShellCheck and hadolint from images pinned by digest, and the tests of the scripts in `.github/scripts`                                    |
| **Trivy**                                | Vulnerable dependencies, leaked secrets and Dockerfile mistakes; high and critical findings with a fix fail the job                                    |
| **Backend**                              | ruff, ruff format, pyright, bandit, pip-audit, migrations on PostgreSQL 18 (checked twice, with the newest migration re-applied), pytest with coverage |
| **Frontend**                             | ESLint, Prettier, vue-tsc, Vitest with coverage, npm audit                                                                                             |
| **CI gate**                              | Passes only when every job that ran passed. A job skipped because its code does not exist yet counts as passed                                         |

Later tickets add the SonarQube job with its issue list (BLI-2), the container job (BLI-6) and the Playwright jobs with merged coverage (BLI-7).

## Branch protection (one-time setup)

In the repository settings, protect `master` and require these checks: **CI gate**, **CodeQL gate**, **zizmor**, **Ticket key, branch and commit messages**. Turn off GitHub's "default setup" for CodeQL, because `codeql.yml` is the advanced setup and the two cannot both upload.

## Secrets

| Secret                                                 | Used for                                                      | Without it                                                                                   |
| ------------------------------------------------------ | ------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `CHAINGUARD_PULL_USERNAME`, `CHAINGUARD_PULL_PASSWORD` | Higher pull limits on `cgr.dev` for the Chainguard base image | The base image is public, so builds work; this is also the case for pull requests from forks |
| `SONAR_TOKEN`                                          | SonarQube analysis (added with BLI-2)                         | The Sonar job is skipped on forks                                                            |

Secret values are never printed. Workflows use them only through `secrets.*` and never write them to logs or artifacts.

## Why the actions are pinned to commit SHAs

A tag such as `v4` can be moved to different code. Every third-party action is pinned to the full commit SHA with the version in a comment, and Dependabot proposes updates, so what runs in CI only changes when someone reviews it. `zizmor` fails the build for an unpinned action.
