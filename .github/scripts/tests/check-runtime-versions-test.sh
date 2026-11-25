#!/usr/bin/env bash
# Tests for ../check-runtime-versions.sh, run against a throwaway tree and a pretend `docker`.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$here/lib.sh"
script="$here/../check-runtime-versions.sh"
root="$(mktemp -d)"
bin="$(mktemp -d)"
trap 'rm -rf "$root" "$bin"' EXIT

# write_tree <python> <postgres>: a Dockerfile asking for 3.14.10 and 18.7, and a workflow using the given ones.
write_tree() {
  mkdir -p "$root/.github/workflows"
  printf 'ARG PYTHON_VERSION=3.14.10\nARG NGINX_VERSION=1.31.10\nARG POSTGRES_VERSION=18.7\n' >"$root/Dockerfile"
  printf 'jobs:\n  a:\n    services:\n      postgres:\n        image: postgres:%s\n    steps:\n      - with:\n          python-version: "%s"\n' "$2" "$1" >"$root/.github/workflows/ci.yml"
}

# A pretend docker that answers with the versions in PY, NGINX and PG.
cat >"$bin/docker" <<'STUB'
#!/usr/bin/env bash
case "$*" in
  *platform.python_version*) echo "$PY" ;;
  *"nginx -v"*) echo "nginx version: nginx/$NGINX" >&2 ;;
  *server_version*) echo "$PG (Debian)" ;;
esac
STUB
chmod +x "$bin/docker"
check() { ROOT="$root" PATH="$bin:$PATH" PY="${PY:-3.14.10}" NGINX="${NGINX:-1.31.10}" PG="${PG:-18.7}" "$script" "$@"; }

echo "check-runtime-versions.sh"
write_tree 3.14.10 18.7
expect_pass "the files agree" check
assert_contains "says so" "Python 3.14.10, nginx 1.31.10, PostgreSQL 18.7"
expect_pass "a container with the wanted versions" check box
expect_pass "a container with newer versions" env PY=3.14.11 NGINX=1.31.11 PG=18.8 ROOT="$root" PATH="$bin:$PATH" "$script" box
expect_fail "an older Python in the container" env PY=3.14.9 ROOT="$root" PATH="$bin:$PATH" NGINX=1.31.10 PG=18.7 "$script" box
assert_contains "names the Python" "runs Python 3.14.9, older than 3.14.10"
expect_fail "an older nginx in the container" env PY=3.14.10 NGINX=1.30.1 PG=18.7 ROOT="$root" PATH="$bin:$PATH" "$script" box
assert_contains "names the nginx" "nginx 1.30.1, older than 1.31.10"
expect_fail "an older PostgreSQL in the container" env PY=3.14.10 NGINX=1.31.10 PG=18.6 ROOT="$root" PATH="$bin:$PATH" "$script" box
assert_contains "names the PostgreSQL" "PostgreSQL 18.6, older than 18.7"

write_tree 3.14 18.7
expect_fail "a workflow with another Python" check
assert_contains "names the workflow" "ci.yml uses Python '3.14'"
write_tree 3.14.10 18
expect_fail "a workflow with another PostgreSQL" check
assert_contains "names the PostgreSQL image" "ci.yml runs PostgreSQL '18'"
printf 'FROM scratch\n' >"$root/Dockerfile"
expect_fail "a Dockerfile without the versions" check
assert_contains "says which one is missing" "no usable ARG for the python version"
finish
