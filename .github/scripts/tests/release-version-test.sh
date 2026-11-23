#!/usr/bin/env bash
# Tests for ../release-version.sh
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$here/lib.sh"
script="$here/../release-version.sh"

run() { # tag prerelease repository
  local out
  out="$(mktemp)"
  GITHUB_OUTPUT="$out" TAG="$1" PRERELEASE="$2" GITHUB_REPOSITORY="${3:-Owner/Blindspot}" "$script" >/dev/null && cat "$out"
}

echo "release-version.sh"
expect_pass "stable release gets all tags" run v1.2.3 false
assert_contains "version without v" "version=1.2.3"
assert_contains "image is lower case" "image=ghcr.io/owner/blindspot"
assert_contains "minor tag" $'1.2\n'
assert_contains "major tag" $'\n1\n'
assert_contains "latest tag" "latest"
expect_pass "tag without v is accepted" run 2.0.0 false
assert_contains "version kept" "version=2.0.0"
expect_pass "pre-release only gets its own tag" run v1.3.0-rc.1 true
assert_contains "pre-release version" "version=1.3.0-rc.1"
if [[ "$LAST_OUTPUT" == *latest* ]]; then fail "pre-release must not get latest"; else pass "pre-release must not get latest"; fi
expect_fail "not a version" run release-1 false
expect_fail "two-part version" run v1.2 false
expect_fail "pre-release version on a stable release" run v1.0.0-beta.1 false
expect_fail "stable version on a pre-release" run v1.0.0 true
finish
