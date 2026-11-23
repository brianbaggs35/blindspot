#!/usr/bin/env bash
# Tests for ../pr-hygiene.sh, run against a throwaway git repository.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$here/lib.sh"
script="$here/../pr-hygiene.sh"
repo="$(mktemp -d)"
trap 'rm -rf "$repo"' EXIT

git -C "$repo" init -q -b master
git -C "$repo" config user.email test@example.com
git -C "$repo" config user.name Test
git -C "$repo" config commit.gpgsign false
git -C "$repo" commit -q --allow-empty -m "BLI-4 Start"
base="$(git -C "$repo" rev-parse HEAD)"

commit() { git -C "$repo" commit -q --allow-empty "$@"; }
head_sha() { git -C "$repo" rev-parse HEAD; }

# check <title> <branch> [body] [actor]: runs the script inside the repo.
check() {
  (cd "$repo" && PR_TITLE="$1" PR_BRANCH="$2" PR_BODY="${3:-}" PR_ACTOR="${4:-}" BASE_SHA="$base" HEAD_SHA="$(head_sha)" "$script")
}

echo "pr-hygiene.sh"
commit -m "BLI-12 Add the app shell"
expect_pass "a correct pull request" check "BLI-12 Add the app shell" "BLI-12-app-shell" "<!-- claude-projects-attribution: {} -->"
expect_fail "title without a key" check "Add the app shell" "BLI-12-app-shell"
assert_contains "names the title rule" "title must start with a Jira ticket key"
expect_fail "title with a key but no words" check "BLI-12" "BLI-12-app-shell"
expect_fail "branch without a key" check "BLI-12 Add the app shell" "app-shell"
expect_fail "branch with upper case" check "BLI-12 Add the app shell" "BLI-12-App-Shell"
expect_fail "title and branch with different tickets" check "BLI-12 Add the app shell" "BLI-13-app-shell"
assert_contains "names both tickets" "BLI-12 but the branch uses BLI-13"
expect_pass "a missing attribution comment is only a notice" check "BLI-12 Add the app shell" "BLI-12-app-shell" ""
assert_contains "the notice" "attribution comment"
expect_pass "Dependabot is exempt" check "Bump x from 1 to 2" "dependabot/npm_and_yarn/x-2" "" "dependabot[bot]"

commit -m "fix the thing"
expect_fail "a commit without a key" check "BLI-12 Add the app shell" "BLI-12-app-shell"
assert_contains "names the commit rule" "must start with a ticket key"
git -C "$repo" reset -q --hard "$base"
commit -m "BLI-12 Add the app shell" -m "A second paragraph"
expect_fail "a commit with a body" check "BLI-12 Add the app shell" "BLI-12-app-shell"
assert_contains "names the one-line rule" "must be a single line"
git -C "$repo" reset -q --hard "$base"
commit -m "BLI-13 Something else"
expect_fail "a commit for another ticket" check "BLI-12 Add the app shell" "BLI-12-app-shell"
git -C "$repo" reset -q --hard "$base"

# A merge of the base branch into the pull request is exempt from the message rules.
git -C "$repo" checkout -q -b topic
commit -m "BLI-12 Add the app shell"
git -C "$repo" checkout -q master
commit -m "BLI-4 More on master"
base="$(git -C "$repo" rev-parse HEAD)"   # the base branch's tip when the pull request is checked
git -C "$repo" checkout -q topic
git -C "$repo" merge -q --no-ff master -m "Merge branch 'master' into topic"
expect_pass "a merge commit is allowed" check "BLI-12 Add the app shell" "BLI-12-app-shell"
finish
