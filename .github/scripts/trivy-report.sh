#!/usr/bin/env bash
# Turns a Trivy step's outcome and SARIF report into a pass or a fail.
# Usage: trivy-report.sh <name> <outcome> <sarif-file>
# The scan steps run with continue-on-error so the findings can be shown and uploaded first;
# this is what then fails the job. A scan that crashed fails too, rather than passing silently.
set -euo pipefail

name="${1:?name}"
outcome="${2:?outcome}"
sarif="${3:?sarif file}"

case "$outcome" in
  success)
    echo "Trivy $name scan: no high or critical vulnerabilities with a fix."
    ;;
  failure)
    if [[ ! -s "$sarif" ]]; then
      echo "::error::The Trivy $name scan failed without writing a report, so it did not run to the end."
      exit 1
    fi
    count="$(jq '[.runs[].results[]?] | length' "$sarif")"
    if [[ "$count" -eq 0 ]]; then
      echo "::error::The Trivy $name scan failed but reported no findings, so it did not run to the end."
      exit 1
    fi
    echo "::error::The Trivy $name scan found $count high or critical issues with a fix. They are listed above and under Security > Code scanning."
    exit 1
    ;;
  *)
    echo "::error::The Trivy $name scan did not run (outcome: $outcome)."
    exit 1
    ;;
esac
