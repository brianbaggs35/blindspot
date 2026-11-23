#!/usr/bin/env bash
# Checks a running Blindspot container answers. It is given the container's name and the HTTPS
# port it is published on (the container's 8443). The app's own health endpoint is /api/health (added with the scaffold);
# the web app is served at /. The container's certificate is self-signed in CI, so it is not verified.
# Usage: smoke-test.sh <container-name> <https-port>
set -euo pipefail

container="${1:?container name}"
port="${2:?https port}"
base="https://127.0.0.1:$port"

echo "Waiting for the container to report healthy..."
for _ in $(seq 1 90); do
  state="$(docker inspect --format '{{.State.Health.Status}}' "$container" 2>/dev/null || echo missing)"
  [[ "$state" == "healthy" ]] && break
  sleep 2
done
if [[ "${state:-}" != "healthy" ]]; then
  echo "::error::The container is '${state:-unknown}', not healthy."
  docker logs --tail 200 "$container" || true
  exit 1
fi

check() {
  local path="$1" want="$2" got
  got="$(curl --silent --show-error --insecure --max-time 10 --output /dev/null --write-out '%{http_code}' "$base$path")"
  if [[ "$got" != "$want" ]]; then
    echo "::error::GET $path returned $got, expected $want."
    exit 1
  fi
  echo "GET $path -> $got"
}

check /api/health 200
check / 200
check /api/does-not-exist 404

# Nothing may listen on TCP except nginx: the API and the database use unix sockets.
listening="$(docker exec "$container" cat /proc/net/tcp /proc/net/tcp6 | while read -r _ local _ state _; do
  [[ "$state" == "0A" ]] && echo "$((16#${local##*:}))"
done | sort -un | tr '\n' ' ')"
if [[ "$listening" != "8080 8443 " ]]; then
  echo "::error::The container listens on TCP ports: ${listening:-none}. Only 8080 and 8443 may."
  exit 1
fi
echo "TCP ports: $listening"

# The server must not announce itself.
if curl --silent --insecure --max-time 10 --head "$base/" | grep -qi '^server:.*[0-9]'; then
  echo "::error::The Server header reveals a version number."
  exit 1
fi
echo "Smoke test passed."
