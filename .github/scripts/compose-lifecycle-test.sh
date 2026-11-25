#!/usr/bin/env bash
# Tests `make up`, `make down` and `make delete` on an image that is already built: the data a
# first start made survives `down` and `up`, and `delete` removes the container, the volume and
# the image. The image is run through compose.yaml, the way people run it, on ports 8443 and 8080.
# Usage: compose-lifecycle-test.sh <image>
set -euo pipefail

image="${1:?image}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here/../.."

export BLINDSPOT_HTTPS_PORT=8443 BLINDSPOT_HTTP_PORT=8080
# compose.yaml names the image it runs; give it the one that was built.
compose_image="$(docker compose config --images)"
docker tag "$image" "$compose_image"

container() { docker compose ps --quiet blindspot; }

echo "make up"
make up COMPOSE_UP_FLAGS=
"$here/smoke-test.sh" "$(container)" 8443
docker compose exec -T blindspot sh -c 'echo kept > /data/lifecycle-marker'

echo "make down keeps the data"
make down
if [[ -n "$(docker compose ps --all --quiet)" ]]; then
  echo "::error::make down left a container behind."
  exit 1
fi
docker volume inspect blindspot_data >/dev/null

echo "make up again finds the data"
make up COMPOSE_UP_FLAGS=
kept="$(docker compose exec -T blindspot cat /data/lifecycle-marker)"
if [[ "$kept" != "kept" ]]; then
  echo "::error::The data written before make down is gone."
  exit 1
fi
"$here/smoke-test.sh" "$(container)" 8443

echo "make delete removes everything"
make delete CONFIRM=yes
if docker volume inspect blindspot_data >/dev/null 2>&1; then
  echo "::error::make delete left the data volume."
  exit 1
fi
if docker image inspect "$compose_image" >/dev/null 2>&1; then
  echo "::error::make delete left the image."
  exit 1
fi
echo "The lifecycle works."
