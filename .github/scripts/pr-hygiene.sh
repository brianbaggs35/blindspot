#!/usr/bin/env bash
# Checks a pull request follows the project's rules (CONTRIBUTING in docs/how-to/contributing.md):
#   - the title starts with a Jira ticket key:        BLI-12 Add the app shell
#   - the branch starts with the same key:            BLI-12-app-shell
#   - every commit message is ONE line starting with the key:  BLI-12 Add the app shell
# Reads PR_TITLE, PR_BRANCH, PR_BODY, PR_ACTOR, BASE_SHA and HEAD_SHA from the environment.
# Dependency update bots are exempt, their pull requests are named by .github/dependabot.yml.
set -euo pipefail

title="${PR_TITLE:?PR_TITLE is not set}"
branch="${PR_BRANCH:?PR_BRANCH is not set}"
body="${PR_BODY:-}"
actor="${PR_ACTOR:-}"
base="${BASE_SHA:?BASE_SHA is not set}"
head="${HEAD_SHA:?HEAD_SHA is not set}"

if [[ "$actor" == "dependabot[bot]" ]]; then
  echo "Dependency update by Dependabot: the ticket rules are not checked."
  exit 0
fi

failed=0
fail() {
  echo "::error::$1"
  failed=1
}

key_pattern='BLI-[0-9]+'

if [[ ! "$title" =~ ^($key_pattern)\ [^[:space:]] ]]; then
  fail "The pull request title must start with a Jira ticket key and a space, like 'BLI-12 Add the app shell'. It is: '$title'"
  title_key=""
else
  title_key="${BASH_REMATCH[1]}"
fi

if [[ ! "$branch" =~ ^($key_pattern)-[a-z0-9][a-z0-9-]*$ ]]; then
  fail "The branch name must start with the ticket key, then lower-case words joined by hyphens, like 'BLI-12-app-shell'. It is: '$branch'"
  branch_key=""
else
  branch_key="${BASH_REMATCH[1]}"
fi

if [[ -n "$title_key" && -n "$branch_key" && "$title_key" != "$branch_key" ]]; then
  fail "The title uses $title_key but the branch uses $branch_key. They must be the same ticket."
fi

# Merge commits (from merging the base branch into this one) are exempt: GitHub writes them.
checked=0
while read -r commit parents; do
  [[ -z "$commit" ]] && continue
  if [[ "$parents" == *" "* ]]; then
    continue
  fi
  checked=$((checked + 1))
  subject="$(git log -1 --format=%s "$commit")"
  rest="$(git log -1 --format=%b "$commit")"
  short="${commit:0:7}"
  if [[ ! "$subject" =~ ^$key_pattern\ [^[:space:]] ]]; then
    fail "Commit $short must start with a ticket key and a space, like 'BLI-12 Add the app shell'. It is: '$subject'"
  fi
  if [[ -n "${rest//[[:space:]]/}" ]]; then
    fail "Commit $short must be a single line, but it has more text after the subject."
  fi
  if [[ -n "$title_key" && "$subject" =~ ^($key_pattern)\  && "${BASH_REMATCH[1]}" != "$title_key" ]]; then
    fail "Commit $short uses ${BASH_REMATCH[1]} but the pull request uses $title_key."
  fi
done < <(git rev-list --parents "$base..$head")

if [[ "$checked" -eq 0 ]]; then
  echo "::notice::No commits of its own to check (only merge commits)."
fi

if [[ "$body" != "<!-- claude-projects-attribution:"* ]]; then
  echo "::notice::The pull request description doesn't start with the project attribution comment (see .github/pull_request_template.md)."
fi

if [[ "$failed" -ne 0 ]]; then
  exit 1
fi
echo "The title, branch and $checked commit message(s) follow the rules."
