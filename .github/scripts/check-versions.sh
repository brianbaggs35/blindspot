#!/usr/bin/env bash
# Checks that every place that holds the app's version agrees, and that the changelog has an entry
# for it. The version lives in backend/pyproject.toml, backend/uv.lock, frontend/package.json and
# frontend/package-lock.json; the changelog's newest released heading must be the same version.
# Reads ROOT (the repository, default: two folders above this script) and EXPECTED (optional: the
# version a release tag asks for, without the v).
set -euo pipefail

root="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
expected="${EXPECTED:-}"
failed=0
fail() {
  echo "::error::$1"
  failed=1
}

pyproject="$(sed -n 's/^version = "\(.*\)"$/\1/p' "$root/backend/pyproject.toml" | head -n 1)"
uv_lock="$(awk '/^name = "blindspot"$/ { getline; print; exit }' "$root/backend/uv.lock" | sed -n 's/^version = "\(.*\)"$/\1/p')"
package="$(jq -r '.version // empty' "$root/frontend/package.json")"
lock_top="$(jq -r '.version // empty' "$root/frontend/package-lock.json")"
lock_root="$(jq -r '.packages[""].version // empty' "$root/frontend/package-lock.json")"
changelog="$(sed -n 's/^## \[\([0-9][^]]*\)\] - [0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}$/\1/p' "$root/CHANGELOG.md" | head -n 1)"

version="$pyproject"
if [[ -z "$version" ]]; then
  fail "backend/pyproject.toml has no version."
  exit 1
fi
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
  fail "The version '$version' in backend/pyproject.toml isn't like 1.2.3 or 1.2.3-rc.1."
fi

check() { # <where> <what it declares>
  local where="$1" declared="$2"
  if [[ "$declared" != "$version" ]]; then
    fail "$where says '${declared:-nothing}', but backend/pyproject.toml says '$version'."
  fi
}
check "backend/uv.lock" "$uv_lock"
check "frontend/package.json" "$package"
check "frontend/package-lock.json" "$lock_top"
check "frontend/package-lock.json (the root package)" "$lock_root"

if [[ "$changelog" != "$version" ]]; then
  fail "CHANGELOG.md's newest release is '${changelog:-missing}', not '$version'. Add a '## [$version] - YYYY-MM-DD' section."
fi
if [[ -n "$expected" && "$expected" != "$version" ]]; then
  fail "The release asks for version '$expected', but the files say '$version'. Bump the version in a pull request first."
fi

if [[ "$failed" -eq 0 ]]; then
  echo "Version $version is the same everywhere, and the changelog has it."
fi
exit "$failed"
