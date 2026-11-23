#!/usr/bin/env bash
# Works out what to publish for a GitHub release: the version, the image name and its tags.
# Reads TAG, PRERELEASE and GITHUB_REPOSITORY; writes version, image and tags to GITHUB_OUTPUT.
# A stable release is tagged x.y.z, x.y, x and latest; a pre-release only gets its own version.
set -euo pipefail

tag="${TAG:?TAG is not set}"
prerelease="${PRERELEASE:-false}"
repository="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is not set}"
output="${GITHUB_OUTPUT:-/dev/stdout}"

version="${tag#v}"
if [[ ! "$version" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)(-[0-9A-Za-z.-]+)?$ ]]; then
  echo "::error::The release tag '$tag' isn't a version like v1.2.3 or v1.2.3-rc.1."
  exit 1
fi
major="${BASH_REMATCH[1]}"
minor="${BASH_REMATCH[2]}"
suffix="${BASH_REMATCH[4]}"

if [[ -n "$suffix" && "$prerelease" != "true" ]]; then
  echo "::error::'$tag' is a pre-release version, but the release isn't marked as a pre-release."
  exit 1
fi
if [[ -z "$suffix" && "$prerelease" == "true" ]]; then
  echo "::error::'$tag' is a stable version, but the release is marked as a pre-release."
  exit 1
fi

# Registry names are lower case; GitHub owner and repository names may not be.
image="ghcr.io/${repository,,}"

tags="$version"
if [[ -z "$suffix" ]]; then
  tags+=$'\n'"$major.$minor"$'\n'"$major"$'\n'"latest"
fi

{
  echo "version=$version"
  echo "image=$image"
  echo "tags<<EOF"
  echo "$tags"
  echo "EOF"
} >> "$output"
