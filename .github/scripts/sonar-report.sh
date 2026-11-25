#!/usr/bin/env bash
# Prints what SonarQube Cloud found, so it can be fixed without opening SonarQube, and fails a
# pull request that has any open issue. Reads SONAR_TOKEN, PULL_REQUEST (empty on a push to
# master) and BRANCH, and the project key from sonar-project.properties. On a pull request it lists
# the pull request's own issues, then every issue still open on master; on master it lists them all.
# SONAR_API (default https://sonarcloud.io/api) can point at a test server.
set -euo pipefail

api="${SONAR_API:-https://sonarcloud.io/api}"
token="${SONAR_TOKEN:?SONAR_TOKEN is not set}"
pull_request="${PULL_REQUEST:-}"
branch="${BRANCH:-}"
properties="${SONAR_PROPERTIES:-sonar-project.properties}"

project="$(sed -n 's/^sonar\.projectKey=//p' "$properties")"
# All of a pull request is new code. On master, every open issue is listed, old ones included,
# so that none is forgotten.
if [[ -n "$pull_request" ]]; then
  scope="pullRequest=$pull_request"
  issues_heading="Open issues in new code:"
  hotspots_heading="Security hotspots to review:"
else
  scope="branch=$branch"
  issues_heading="Open issues on $branch:"
  hotspots_heading="Security hotspots to review on $branch:"
fi

sonar() {
  local endpoint="$1"
  curl --silent --show-error --fail-with-body -H "Authorization: Bearer $token" "$api/$endpoint&$scope"
}

# Prints the heading and the lines piped in, or nothing when there are none.
section() {
  local heading="$1" lines
  lines="$(cat)"
  if [[ -n "$lines" ]]; then
    printf '%s\n%s\n\n' "$heading" "$lines"
  fi
}

# One line per issue: where it is, its rule and what to change.
list_issues() {
  jq -r '
    (.errors[]? | "  \(.msg)"),
    (.issues[]? | "  \(.component | sub("^[^:]*:"; "")):\(.line // "-")  \(.rule)  \(.message)")'
}

sonar "qualitygates/project_status?projectKey=$project" | jq -r '
  def grade: ["A", "B", "C", "D", "E"][tonumber - 1];
  (.errors[]? | "  \(.msg)"),
  (.projectStatus.conditions[]? | select(.status == "ERROR") |
    if (.metricKey | endswith("_rating"))
    then "  \(.metricKey) is \(.actualValue | grade), needs \(.errorThreshold | grade)"
    else "  \(.metricKey) is \(.actualValue), needs \(if .comparator == "GT" then "at most" else "at least" end) \(.errorThreshold)"
    end)' | section "Quality gate conditions not met:"

issues="$(sonar "issues/search?componentKeys=$project&issueStatuses=OPEN,CONFIRMED&ps=500")"
list_issues <<<"$issues" | section "$issues_heading"

sonar "hotspots/search?projectKey=$project&status=TO_REVIEW&ps=500" | jq -r '
  (.errors[]? | "  \(.msg)"),
  (.hotspots[]? | "  \(.component | sub("^[^:]*:"; "")):\(.line // "-")  \(.ruleKey)  \(.message)")' |
  section "$hotspots_heading"

# A pull request's analysis only has issues in its own changes, so the ones already open on
# master are listed too, for fixing along the way. Asking without a branch gives the main branch,
# the only one SonarQube Cloud lists issues for, so this works for a pull request stacked on
# another pull request's branch as well.
if [[ -n "$pull_request" ]]; then
  curl --silent --show-error --fail-with-body -H "Authorization: Bearer $token" \
    "$api/issues/search?componentKeys=$project&issueStatuses=OPEN,CONFIRMED&ps=500" |
    list_issues | section "Open issues already on master:"
fi

# Marking an issue accepted or a false positive in SonarQube Cloud takes it off the list.
open_issues="$(jq '.paging.total // .total // 0' <<<"$issues")"
if [[ -n "$pull_request" && "$open_issues" -gt 0 ]]; then
  echo "::error::SonarQube found $open_issues open issues in this pull request. Fix them, or mark them accepted in SonarQube Cloud, before merging."
  exit 1
fi
echo "SonarQube: no open issues in new code."
