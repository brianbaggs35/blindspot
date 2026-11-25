#!/usr/bin/env bash
# Tests for ../check-versions.sh, run against a throwaway copy of the files it reads.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$here/lib.sh"
script="$here/../check-versions.sh"
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

# write_files <version>: every file at the same version, with a changelog entry for it.
write_files() {
  mkdir -p "$root/backend" "$root/frontend"
  printf '[project]\nname = "blindspot"\nversion = "%s"\n' "$1" >"$root/backend/pyproject.toml"
  printf 'version = 1\n\n[[package]]\nname = "alembic"\nversion = "1.0.0"\n\n[[package]]\nname = "blindspot"\nversion = "%s"\n' "$1" >"$root/backend/uv.lock"
  printf '{"name":"blindspot-frontend","version":"%s"}\n' "$1" >"$root/frontend/package.json"
  printf '{"name":"blindspot-frontend","version":"%s","packages":{"":{"version":"%s"}}}\n' "$1" "$1" >"$root/frontend/package-lock.json"
  printf '# Changelog\n\n## [Unreleased]\n\n## [%s] - 2026-11-25\n\n### Added\n\n- A thing.\n' "$1" >"$root/CHANGELOG.md"
}
check() { ROOT="$root" EXPECTED="${1:-}" "$script"; }

echo "check-versions.sh"
write_files 0.0.1
expect_pass "every file agrees" check
assert_contains "says so" "Version 0.0.1 is the same everywhere"
expect_pass "a release tag that matches" check 0.0.1
expect_fail "a release tag that does not match" check 0.0.2
assert_contains "names the tag's version" "The release asks for version '0.0.2'"

write_files 0.0.1
sed -i 's/"version":"0.0.1","packages"/"version":"0.0.2","packages"/' "$root/frontend/package-lock.json"
expect_fail "the lock file's own version differs" check
assert_contains "names the lock file" "frontend/package-lock.json says '0.0.2'"

write_files 0.0.1
sed -i 's/"packages":{"":{"version":"0.0.1"}}/"packages":{"":{"version":"0.0.3"}}/' "$root/frontend/package-lock.json"
expect_fail "the lock file's root package differs" check
assert_contains "names the root package" "the root package"

write_files 0.0.1
sed -i 's/^version = "0.0.1"$/version = "0.0.4"/' "$root/backend/uv.lock"
expect_fail "the Python lock file differs" check
assert_contains "names the Python lock file" "backend/uv.lock says '0.0.4'"

write_files 0.0.1
printf '{"name":"blindspot-frontend"}\n' >"$root/frontend/package.json"
expect_fail "package.json has no version" check
assert_contains "says nothing was declared" "frontend/package.json says 'nothing'"

write_files 0.0.1
printf '# Changelog\n\n## [Unreleased]\n' >"$root/CHANGELOG.md"
expect_fail "the changelog has no release" check
assert_contains "asks for a section" "CHANGELOG.md's newest release is 'missing'"

write_files 0.0.1
printf '# Changelog\n\n## [0.0.1]\n' >"$root/CHANGELOG.md"
expect_fail "the changelog heading has no date" check

write_files 0.0.1
printf '[project]\nname = "blindspot"\n' >"$root/backend/pyproject.toml"
expect_fail "pyproject.toml has no version" check
assert_contains "names the file" "backend/pyproject.toml has no version"

write_files not-a-version
expect_fail "a version that is not semantic" check
assert_contains "says what a version looks like" "isn't like 1.2.3"
finish
