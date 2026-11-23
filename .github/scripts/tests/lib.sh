#!/usr/bin/env bash
# shellcheck disable=SC2001 # indenting every line of a captured output is clearer with sed
# A tiny test harness for the CI scripts: expect_pass, expect_fail, assert_contains.
set -uo pipefail

TESTS_RUN=0
TESTS_FAILED=0

pass() { TESTS_RUN=$((TESTS_RUN + 1)); echo "  ok   $1"; }
fail() { TESTS_RUN=$((TESTS_RUN + 1)); TESTS_FAILED=$((TESTS_FAILED + 1)); echo "  FAIL $1"; }

# expect_pass "name" command...  : the command must exit 0.
expect_pass() {
  local name="$1"; shift
  if LAST_OUTPUT="$("$@" 2>&1)"; then pass "$name"; else fail "$name"; echo "$LAST_OUTPUT" | sed 's/^/       /'; fi
}

# expect_fail "name" command...  : the command must exit non-zero.
expect_fail() {
  local name="$1"; shift
  if LAST_OUTPUT="$("$@" 2>&1)"; then fail "$name (it passed)"; echo "$LAST_OUTPUT" | sed 's/^/       /'; else pass "$name"; fi
}

# assert_contains "name" "text" : the last command's output must contain the text.
assert_contains() {
  if [[ "$LAST_OUTPUT" == *"$2"* ]]; then pass "$1"; else fail "$1 (missing: $2)"; echo "$LAST_OUTPUT" | sed 's/^/       /'; fi
}

finish() {
  echo "$TESTS_RUN checks, $TESTS_FAILED failed."
  [[ "$TESTS_FAILED" -eq 0 ]]
}
