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
grep -F 'generate the next Codex development handoff for the current repository' "$runner" >/dev/null || \
    fail "natural English generation prompt"
grep -F '为当前仓库生成下一条 Codex 开发交接' "$runner" >/dev/null || \
    fail "natural Chinese generation prompt"
grep -F 'git_status_raw != status_before' "$runner" >/dev/null || \
    fail "preexisting dirty status preservation"
grep -F 'duplicate passed evidence fingerprint' "$runner" >/dev/null || \
    fail "passed evidence fingerprint binding"
grep -F 'ordinary Gate receipt binding' "$runner" >/dev/null || \
    fail "ordinary implementation receipt binding"
grep -F 'allowed_receipt_keys' "$runner" >/dev/null || \
    fail "ordinary receipt optional evidence fields"
grep -F 'if relative == "AGENTS.md" and case_id == "no-local-authority":' "$runner" >/dev/null || \
    fail "zero-authority fingerprint evidence"
grep -F 'src/AGENTS.md' "$runner" >/dev/null || \
    fail "nested authority fixture"
for leaked_answer in \
    'profile-specific body cap' \
    '对应 profile 的正文上限' \
    'Never substitute a capability/package helper as authority' \
    'Gate commands alone do not escalate docs/config work' \
    'open the fence only after the exact Open inventory line' \
    '只能在精确 Open inventory 行之后打开 fence'
do
    if grep -F "$leaked_answer" "$runner" >/dev/null; then
        fail "answer-bearing prompt leaked: $leaked_answer"
    fi
done
grep -F "printf '%s\\n' '.project/' '.code-review-graph/'" "$runner" >/dev/null || \
    fail "evaluator graph status isolation"
grep -F 'tool_access_evidence.py' "$runner" >/dev/null || \
    fail "skill-package access evidence guard"
grep -F 'HOST_PATH_PATTERN = re.compile(' "$runner" >/dev/null || \
    fail "host-path sanitizer pattern"
grep -F 'HOST_PATH_PATTERN.sub("<host-path>", text)' "$runner" >/dev/null || \
    fail "host-path sanitizer application"
grep -F '\`tracker: none\`' "$runner" >/dev/null || fail "tracker-none shell quoting"

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

fake_bin=$test_root/fake-bin
mkdir "$fake_bin"
cat >"$fake_bin/codex" <<'EOF'
#!/bin/sh
output=
while [ "$#" -gt 0 ]; do
    if [ "$1" = -o ]; then output=$2; shift 2; else shift; fi
done
[ -z "${FAKE_PROMPT_CAPTURE:-}" ] || cat >"$FAKE_PROMPT_CAPTURE"
[ -z "$output" ] || : >"$output"
printf '%s\n' "/usr/bin/zsh -lc 'sed -n 1,40p ../../../snapshot/skill/scripts/status_fingerprint.py' in /tmp/fixture"
EOF
chmod 0700 "$fake_bin/codex"
root=$(new_run_root helper-read)
sh "$runner" init "$root" >/dev/null 2>&1 || fail "helper-read snapshot initialization"
if PATH="$fake_bin:$PATH" sh "$runner" light-documentation "$root" >"$test_root/helper-read.log" 2>&1; then
    fail "helper source inspection accepted"
fi
grep -F 'generator inspected helper source or used an unsupported helper command' "$test_root/helper-read.log" >/dev/null || \
    fail "helper source inspection failed for another reason"

cat >"$fake_bin/codex" <<'EOF'
#!/bin/sh
output=
while [ "$#" -gt 0 ]; do
    if [ "$1" = -o ]; then output=$2; shift 2; else shift; fi
done
[ -z "${FAKE_PROMPT_CAPTURE:-}" ] || cat >"$FAKE_PROMPT_CAPTURE"
[ -z "$output" ] || : >"$output"
printf '%s\n' "/usr/bin/zsh -lc 'find ../../../snapshot/skill -maxdepth 2 -type f' in /tmp/fixture"
EOF
chmod 0700 "$fake_bin/codex"
root=$(new_run_root package-list)
sh "$runner" init "$root" >/dev/null 2>&1 || fail "package-list snapshot initialization"
if PATH="$fake_bin:$PATH" sh "$runner" light-documentation "$root" >"$test_root/package-list.log" 2>&1; then
    fail "skill package listing accepted"
fi
grep -F 'generator accessed an undeclared skill-package path' "$test_root/package-list.log" >/dev/null || \
    fail "skill package listing failed for another reason"

root=$(new_run_root tracker-none-shell)
sh "$runner" init "$root" >/dev/null 2>&1 || fail "tracker-none snapshot initialization"
FAKE_PROMPT_CAPTURE=$test_root/tracker-none.prompt PATH="$fake_bin:$PATH" \
    sh "$runner" tracker-none-projection "$root" >"$test_root/tracker-none.log" 2>&1 || :
grep -F '`tracker: none`' "$test_root/tracker-none.prompt" >/dev/null || fail "tracker-none prompt literal"
if grep -F 'tracker:: not found' "$test_root/tracker-none.log" >/dev/null; then
    fail "tracker-none prompt executed by shell"
fi

printf '%s\n' 'PASS: forward eval runner ownership, containment, and snapshot guards'
