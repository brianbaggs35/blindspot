#!/usr/bin/env bash
# Prints what SonarQube Cloud found, so it can be fixed without opening SonarQube, and fails a
# pull request that has any open issue. Reads SONAR_TOKEN, PULL_REQUEST (empty on a branch),
# BASE_BRANCH and BRANCH, and the project key from sonar-project.properties.
# SONAR_API (default https://sonarcloud.io/api) can point at a test server.
set -euo pipefail

api="${SONAR_API:-https://sonarcloud.io/api}"
token="${SONAR_TOKEN:?SONAR_TOKEN is not set}"
pull_request="${PULL_REQUEST:-}"
base_branch="${BASE_BRANCH:-}"
branch="${BRANCH:-}"
properties="${SONAR_PROPERTIES:-sonar-project.properties}"

project="$(sed -n 's/^sonar\.projectKey=//p' "$properties")"
# All of a pull request is new code; on master, only what changed lately is.
if [[ -n "$pull_request" ]]; then
  scope="pullRequest=$pull_request"
  new_code=""
else
  scope="branch=$branch"
  new_code="&inNewCodePeriod=true"
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

issues="$(sonar "issues/search?componentKeys=$project&issueStatuses=OPEN,CONFIRMED$new_code&ps=500")"
list_issues <<<"$issues" | section "Open issues in new code:"

sonar "hotspots/search?projectKey=$project&status=TO_REVIEW$new_code&ps=500" | jq -r '
  (.errors[]? | "  \(.msg)"),
  (.hotspots[]? | "  \(.component | sub("^[^:]*:"; "")):\(.line // "-")  \(.ruleKey)  \(.message)")' |
  section "Security hotspots to review:"

# A pull request's analysis only has issues in its own changes, so the ones already on the
# branch it merges into are listed too, for fixing along the way.
if [[ -n "$pull_request" && -n "$base_branch" ]]; then
  curl --silent --show-error --fail-with-body -H "Authorization: Bearer $token" \
    "$api/issues/search?componentKeys=$project&issueStatuses=OPEN,CONFIRMED&ps=500&branch=$base_branch" |
    list_issues | section "Open issues on $base_branch:"
fi

# Marking an issue accepted or a false positive in SonarQube Cloud takes it off the list.
open_issues="$(jq '.paging.total // .total // 0' <<<"$issues")"
if [[ -n "$pull_request" && "$open_issues" -gt 0 ]]; then
  echo "::error::SonarQube found $open_issues open issues in this pull request. Fix them, or mark them accepted in SonarQube Cloud, before merging."
  exit 1
fi
echo "SonarQube: no open issues in new code."
