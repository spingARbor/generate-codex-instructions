#!/bin/sh
set -eu

runner=${1:?usage: test-forward-eval-runner-guards.sh RUNNER}
test_root=$(mktemp -d /tmp/gci-forward-guard.XXXXXX)
trap 'chmod -R u+w "$test_root" 2>/dev/null || :; rm -rf "$test_root"' EXIT HUP INT TERM
chmod 0700 "$test_root"

fail() {
    printf '%s\n' "FAIL: forward eval guard self-test: $*" >&2
    exit 1
}

grep -F 'if stat.S_ISDIR(metadata.st_mode):' "$runner" >/dev/null || \
    fail "tracker subdirectory handling"
grep -F 'future executor to edit the selected owner/test' "$runner" >/dev/null || \
    fail "future executor authority prompt"
grep -F "profile-specific body cap" "$runner" >/dev/null || \
    fail "profile-specific body cap prompt"
grep -F '对应 profile 的正文上限' "$runner" >/dev/null || \
    fail "Chinese profile-specific body cap prompt"
grep -F 'git_status_raw != status_before' "$runner" >/dev/null || \
    fail "preexisting dirty status preservation"
grep -F 'duplicate passed evidence fingerprint' "$runner" >/dev/null || \
    fail "passed evidence fingerprint binding"
grep -F 'ordinary Gate receipt binding' "$runner" >/dev/null || \
    fail "ordinary implementation receipt binding"
grep -F 'Never substitute a capability/package helper as authority' "$runner" >/dev/null || \
    fail "closed ledger-role prompt"
grep -F 'Gate commands alone do not escalate docs/config work' "$runner" >/dev/null || \
    fail "profile-impact prompt"
grep -F 'open the fence only after the exact Open inventory line' "$runner" >/dev/null || \
    fail "preamble fence-boundary prompt"
grep -F '只能在精确 Open inventory 行之后打开 fence' "$runner" >/dev/null || \
    fail "Chinese preamble fence-boundary prompt"
grep -F "printf '%s\\n' '.project/' '.code-review-graph/'" "$runner" >/dev/null || \
    fail "evaluator graph status isolation"

new_run_root() {
    candidate=$test_root/$1
    mkdir "$candidate"
    chmod 0700 "$candidate"
    printf '%s\n' "$candidate"
}

root=$(new_run_root ownership)
sh "$runner" init "$root" >/dev/null 2>&1 || fail "snapshot initialization"
set +e
FORWARD_EVAL_GUARD_ONLY=1 sh "$runner" chinese-mixed-state-first-delivery "$root" >/dev/null 2>&1 &
first_pid=$!
FORWARD_EVAL_GUARD_ONLY=1 sh "$runner" chinese-mixed-state-first-delivery "$root" >/dev/null 2>&1 &
second_pid=$!
wait "$first_pid"
first_status=$?
wait "$second_pid"
second_status=$?
set -e
case $first_status:$second_status in
    0:2 | 2:0) ;;
    *) fail "same-case concurrent ownership" ;;
esac

root=$(new_run_root symlink)
outside=$test_root/outside
mkdir "$outside"
printf '%s\n' unchanged >"$outside/marker"
sh "$runner" init "$root" >/dev/null 2>&1 || fail "symlink snapshot initialization"
ln -s "$outside" "$root/cases/tracker-path-escape"
FORWARD_EVAL_GUARD_ONLY=1 sh "$runner" tracker-path-escape "$root" >/dev/null 2>&1 && \
    fail "symlink case target accepted"
[ "$(cat "$outside/marker")" = unchanged ] || fail "symlink target changed"

root=$(new_run_root symlink-race)
outside=$test_root/race-outside
mkdir "$outside"
printf '%s\n' unchanged >"$outside/marker"
sh "$runner" init "$root" >/dev/null 2>&1 || fail "symlink race snapshot initialization"
set +e
(
    attempt=0
    while [ "$attempt" -lt 100 ]
    do
        ln -s "$outside" "$root/cases/fence-safety" 2>/dev/null && exit 0
        [ ! -e "$root/cases/fence-safety" ] && [ ! -L "$root/cases/fence-safety" ] || exit 2
        attempt=$((attempt + 1))
    done
    exit 3
) &
link_pid=$!
FORWARD_EVAL_GUARD_ONLY=1 sh "$runner" fence-safety "$root" >/dev/null 2>&1
runner_status=$?
wait "$link_pid"
link_status=$?
set -e
case $runner_status:$link_status in
    0:2 | 2:0) ;;
    *) fail "symlink race ownership" ;;
esac
[ "$(cat "$outside/marker")" = unchanged ] || fail "symlink race target changed"

root=$(new_run_root special)
sh "$runner" init "$root" >/dev/null 2>&1 || fail "special snapshot initialization"
printf '%s\n' unchanged >"$root/hardlink-source"
ln "$root/hardlink-source" "$root/cases/complete-plan"
FORWARD_EVAL_GUARD_ONLY=1 sh "$runner" complete-plan "$root" >/dev/null 2>&1 && \
    fail "hardlinked case target accepted"
[ "$(cat "$root/hardlink-source")" = unchanged ] || fail "hardlink source changed"
mkfifo "$root/cases/generic-blocker"
FORWARD_EVAL_GUARD_ONLY=1 sh "$runner" generic-blocker "$root" >/dev/null 2>&1 && \
    fail "special case target accepted"

root=$(new_run_root tamper)
sh "$runner" init "$root" >/dev/null 2>&1 || fail "tamper snapshot initialization"
chmod 0600 "$root/snapshot/runner.sh"
printf '%s\n' '# tamper' >>"$root/snapshot/runner.sh"
FORWARD_EVAL_GUARD_ONLY=1 sh "$runner" complete-plan "$root" >/dev/null 2>&1 && \
    fail "tampered snapshot accepted"

root=$(new_run_root fingerprint-tamper)
sh "$runner" init "$root" >/dev/null 2>&1 || fail "fingerprint snapshot initialization"
chmod 0600 "$root/snapshot/status_fingerprint.py"
printf '%s\n' '# tamper' >>"$root/snapshot/status_fingerprint.py"
FORWARD_EVAL_GUARD_ONLY=1 sh "$runner" snapshot-double-drift "$root" >/dev/null 2>&1 && \
    fail "tampered fingerprint helper accepted"

root=$(new_run_root contract-tamper)
sh "$runner" init "$root" >/dev/null 2>&1 || fail "contract snapshot initialization"
chmod 0600 "$root/snapshot/execution_contract.py"
printf '%s\n' '# tamper' >>"$root/snapshot/execution_contract.py"
FORWARD_EVAL_GUARD_ONLY=1 sh "$runner" chinese-mixed-state-first-delivery "$root" >/dev/null 2>&1 && \
    fail "tampered execution-contract helper accepted"

root=$(new_run_root public)
chmod 0755 "$root"
sh "$runner" init "$root" >/dev/null 2>&1 && fail "public run root accepted"

printf '%s\n' 'PASS: forward eval runner ownership, containment, and snapshot guards'
