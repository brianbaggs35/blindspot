#!/usr/bin/env bash
# Starts a Blindspot image the way compose.yaml does: read-only file system, every capability
# dropped except the five the entrypoint needs, no new privileges, and the app published on
# loopback only. CI and the release use it, so what is tested is what people run.
# Usage: run-container.sh <image> <container-name> <https-port> [extra docker run args...]
set -euo pipefail

image="${1:?image}"
name="${2:?container name}"
port="${3:?https port}"
shift 3

docker run --detach --name "$name" \
  --read-only \
  --tmpfs /run:rw,noexec,nosuid,nodev,size=64m \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
  --cap-drop ALL \
  --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER --cap-add SETUID --cap-add SETGID \
  --security-opt no-new-privileges:true \
  --pids-limit 512 \
  --volume "$name-data:/data" \
  --env "BLINDSPOT_PUBLIC_HTTPS_PORT=$port" \
  --publish "127.0.0.1:$port:8443" \
  "$@" \
  "$image"
