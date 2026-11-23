#!/usr/bin/env bash
# Tests for ../trivy-report.sh
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$here/lib.sh"
script="$here/../trivy-report.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo '{"runs":[{"results":[]}]}' > "$tmp/clean.sarif"
echo '{"runs":[{"results":[{"ruleId":"CVE-1"},{"ruleId":"CVE-2"}]}]}' > "$tmp/findings.sarif"
: > "$tmp/empty.sarif"

echo "trivy-report.sh"
expect_pass "success passes" "$script" image success "$tmp/clean.sarif"
expect_fail "failure with findings fails" "$script" image failure "$tmp/findings.sarif"
assert_contains "says how many" "found 2 high or critical"
expect_fail "failure without findings means the scan crashed" "$script" image failure "$tmp/clean.sarif"
assert_contains "explains the crash" "did not run to the end"
expect_fail "failure without a report" "$script" image failure "$tmp/empty.sarif"
expect_fail "failure with a missing report" "$script" image failure "$tmp/missing.sarif"
expect_fail "skipped scan fails" "$script" source skipped "$tmp/clean.sarif"
expect_fail "cancelled scan fails" "$script" source cancelled "$tmp/clean.sarif"
finish
