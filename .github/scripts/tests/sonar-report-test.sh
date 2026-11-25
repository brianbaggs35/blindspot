#!/usr/bin/env bash
# Tests for ../sonar-report.sh, with a stand-in curl that answers from files.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$here/lib.sh"
script="$here/../sonar-report.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/bin"

# The stand-in curl prints the file named after the API it was asked for, and fails (as
# curl --fail-with-body does) when there is none.
cat > "$tmp/bin/curl" <<'CURL'
#!/usr/bin/env bash
url="${*: -1}"
case "$url" in
  *qualitygates/project_status*) file=gate ;;
  *hotspots/search*) file=hotspots ;;
  *pullRequest=*issues/search*|*issues/search*pullRequest=*) file=issues ;;
  *branch=*issues/search*|*issues/search*branch=*) file=issues ;;
  *issues/search*) file=base ;;
  *) exit 22 ;;
esac
cat "$SONAR_FAKE/$file.json" || exit 22
CURL
chmod +x "$tmp/bin/curl"
printf 'sonar.projectKey=org_project\n' > "$tmp/sonar.properties"

fake() { # fake <gate> <issues> <hotspots> <base issues>
  mkdir -p "$tmp/fake"
  echo "$1" > "$tmp/fake/gate.json"
  echo "$2" > "$tmp/fake/issues.json"
  echo "$3" > "$tmp/fake/hotspots.json"
  echo "$4" > "$tmp/fake/base.json"
}
run() { # run <pull request number or empty>
  PATH="$tmp/bin:$PATH" SONAR_FAKE="$tmp/fake" SONAR_TOKEN=token SONAR_PROPERTIES="$tmp/sonar.properties" \
    PULL_REQUEST="$1" BRANCH=master "$script"
}

ok_gate='{"projectStatus":{"status":"OK","conditions":[]}}'
none='{"paging":{"total":0},"issues":[],"hotspots":[]}'
issue='{"paging":{"total":1},"issues":[{"component":"org_project:backend/app/x.py","line":7,"rule":"python:S1192","message":"Define a constant."}]}'

echo "sonar-report.sh"
fake "$ok_gate" "$none" "$none" "$none"
expect_pass "a clean pull request passes" run 12
assert_contains "says there is nothing" "no open issues"

fake "$ok_gate" "$issue" "$none" "$none"
expect_fail "an open issue fails a pull request" run 12
assert_contains "names the file, line and rule" "backend/app/x.py:7  python:S1192  Define a constant."
assert_contains "counts them" "1 open issues"
expect_pass "an open issue on master is only listed" run ""
assert_contains "lists every open issue on master" "Open issues on master:"

fake '{"projectStatus":{"status":"ERROR","conditions":[{"status":"ERROR","metricKey":"new_coverage","comparator":"LT","errorThreshold":"80","actualValue":"61.5"},{"status":"ERROR","metricKey":"new_security_rating","errorThreshold":"1","actualValue":"3"}]}}' "$none" "$none" "$none"
expect_pass "the gate itself is the scan step's job" run 12
assert_contains "explains a coverage condition" "new_coverage is 61.5, needs at least 80"
assert_contains "explains a rating condition" "new_security_rating is C, needs A"

fake "$ok_gate" "$none" '{"hotspots":[{"component":"org_project:frontend/src/a.ts","line":3,"ruleKey":"typescript:S5332","message":"Use https."}]}' "$issue"
expect_pass "hotspots are listed" run 12
assert_contains "names the hotspot" "frontend/src/a.ts:3  typescript:S5332  Use https."
assert_contains "lists what is already open on master" "Open issues already on master:"
assert_contains "names those issues" "backend/app/x.py:7  python:S1192  Define a constant."

fake "$ok_gate" "$none" "$none" "$issue"
expect_pass "master's issues don't fail a pull request without its own" run 12
assert_contains "still lists master's issues" "Open issues already on master:"

rm "$tmp/fake/base.json"
expect_fail "master's issues failing to load fails loudly" run 12

rm "$tmp/fake/gate.json"
expect_fail "an API failure fails loudly" run 12
finish
