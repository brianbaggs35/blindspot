#!/usr/bin/env bash
# Checks the runtime versions the image is built with are the ones CI uses and the container runs
# (BLI-60). The Dockerfile's ARGs PYTHON_VERSION, NGINX_VERSION and POSTGRES_VERSION are the one
# source: every `python-version:` in the workflows must be that Python, and every `postgres:` service
# image must be that PostgreSQL. With a container name, the container must also run at least
# those versions of Python, nginx and PostgreSQL.
# Reads ROOT (the repository, default: two folders above this script).
# Usage: check-runtime-versions.sh [container]
set -euo pipefail

root="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
container="${1:-}"
failed=0
fail() {
  echo "::error::$1"
  failed=1
}

wanted() { sed -n "s/^ARG $1=\(.*\)\$/\1/p" "$root/Dockerfile" | head -n 1; }
python_wanted="$(wanted PYTHON_VERSION)"
nginx_wanted="$(wanted NGINX_VERSION)"
postgres_wanted="$(wanted POSTGRES_VERSION)"
for name in python nginx postgres; do
  value="${name}_wanted"
  if [[ ! "${!value}" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]]; then
    fail "The Dockerfile has no usable ARG for the $name version (found '${!value}')."
    exit 1
  fi
done

# at_least <found> <wanted>: true when found is the same version or newer.
at_least() { [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n 1)" == "$2" ]]; }

for workflow in "$root"/.github/workflows/*.yml; do
  name="$(basename "$workflow")"
  while IFS= read -r found; do
    [[ "$found" == "$python_wanted" ]] || fail "$name uses Python '$found', but the Dockerfile asks for '$python_wanted'."
  done < <(sed -n 's/^ *python-version: *"\{0,1\}\([^"# ]*\)"\{0,1\}.*$/\1/p' "$workflow")
  while IFS= read -r found; do
    [[ "$found" == "$postgres_wanted" ]] || fail "$name runs PostgreSQL '$found', but the Dockerfile asks for '$postgres_wanted'."
  done < <(sed -n 's/^ *image: *postgres:\([^ #]*\).*$/\1/p' "$workflow")
done

if [[ -n "$container" ]]; then
  python_have="$(docker exec "$container" /opt/venv/bin/python -c 'import platform; print(platform.python_version())')"
  nginx_have="$(docker exec "$container" nginx -v 2>&1 | sed -n 's|^nginx version: nginx/\(.*\)$|\1|p')"
  postgres_have="$(docker exec --user blindspot "$container" psql --host /run/postgresql --dbname blindspot \
    --no-psqlrc --tuples-only --no-align --command 'SHOW server_version' | sed 's/ .*//')"
  echo "Python $python_have, nginx $nginx_have, PostgreSQL $postgres_have"
  at_least "$python_have" "$python_wanted" || fail "The container runs Python $python_have, older than $python_wanted."
  at_least "$nginx_have" "$nginx_wanted" || fail "The container runs nginx $nginx_have, older than $nginx_wanted."
  at_least "$postgres_have" "$postgres_wanted" || fail "The container runs PostgreSQL $postgres_have, older than $postgres_wanted."
fi

if [[ "$failed" -eq 0 ]]; then
  echo "The runtime versions agree (Python $python_wanted, nginx $nginx_wanted, PostgreSQL $postgres_wanted)."
fi
exit "$failed"
