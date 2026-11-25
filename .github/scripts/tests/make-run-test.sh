#!/usr/bin/env bash
# Tests the Makefile's up, down and delete commands by what `make --dry-run` says they would run.
# The real lifecycle (containers and volumes) is tested in CI by ../compose-lifecycle-test.sh.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$here/lib.sh"
cd "$here/../../.." || exit 1

dry() { make --dry-run --no-print-directory "$@" 2>&1; }

echo "make up, down and delete"
expect_pass "up builds and waits until the container is healthy" dry up
assert_contains "builds" "up --detach --wait --wait-timeout 180 --build"
expect_pass "up can start the image that exists" dry up COMPOSE_UP_FLAGS=
if [[ "$LAST_OUTPUT" == *"--build"* ]]; then fail "up without flags must not build"; else pass "up without flags must not build"; fi
expect_pass "down removes the container only" dry down
assert_contains "plain down" "docker compose down --remove-orphans"
if [[ "$LAST_OUTPUT" == *"--volumes"* || "$LAST_OUTPUT" == *"--rmi"* ]]; then fail "down must keep volumes and images"; else pass "down must keep volumes and images"; fi
expect_pass "delete with the confirmation given" dry delete CONFIRM=yes
assert_contains "removes the volumes" "docker compose down --volumes --rmi all --remove-orphans"
assert_contains "removes the Trivy cache" "docker volume rm --force blindspot-trivy-cache"
assert_contains "removes the build cache" "docker builder prune --all --force"
expect_fail "delete without the confirmation stops when it is not typed" bash -c 'echo no | make delete'
assert_contains "says nothing was deleted" "Nothing was deleted."
expect_pass "help lists the three" bash -c 'make help | grep -E "^ +.*(up|down|delete)"'
finish
