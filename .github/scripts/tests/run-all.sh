#!/usr/bin/env bash
# Runs every test of the CI scripts. Used by `make test-ci-scripts` and the CI workflow.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
status=0
for test in "$here"/*-test.sh; do
  "$test" || status=1
  echo
done
exit "$status"
